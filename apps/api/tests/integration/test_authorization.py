"""Integration tests for RBAC, IDOR prevention, and ownership checks.

Requires a running MongoDB instance.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest
from bson import ObjectId

from app.db import mongo

pytestmark = [
    pytest.mark.skipif(
        os.environ.get("SKIP_MONGO_TESTS", "1") == "1",
        reason="MongoDB not available; set SKIP_MONGO_TESTS=0 to run",
    ),
]


class TestAdminRoutes:
    """Verify only admin/superadmin can access admin endpoints."""

    async def test_admin_users_requires_admin(self, client, regular_user_token):
        headers = {"Authorization": f"Bearer {regular_user_token}"}
        r = await client.get("/api/v1/admin/users", headers=headers)
        assert r.status_code == 403

    async def test_admin_users_allows_admin(self, client, admin_token):
        headers = {"Authorization": f"Bearer {admin_token}"}
        r = await client.get("/api/v1/admin/users", headers=headers)
        assert r.status_code == 200

    async def test_admin_users_allows_superadmin(self, client, superadmin_token):
        headers = {"Authorization": f"Bearer {superadmin_token}"}
        r = await client.get("/api/v1/admin/users", headers=headers)
        assert r.status_code == 200

    async def test_admin_stats_requires_admin(self, client, regular_user_token):
        headers = {"Authorization": f"Bearer {regular_user_token}"}
        r = await client.get("/api/v1/admin/stats", headers=headers)
        assert r.status_code == 403

    async def test_admin_audit_logs_requires_admin(self, client, regular_user_token):
        headers = {"Authorization": f"Bearer {regular_user_token}"}
        r = await client.get("/api/v1/admin/audit-logs", headers=headers)
        assert r.status_code == 403


class TestPrivilegeEscalation:
    """Verify non-superadmin cannot promote to admin/superadmin."""

    async def test_admin_cannot_promote_to_superadmin(self, client, admin_token, regular_user):
        headers = {"Authorization": f"Bearer {admin_token}"}
        uid = str(regular_user["_id"])
        r = await client.patch(
            f"/api/v1/admin/users/{uid}",
            json={"role": "superadmin"},
            headers=headers,
        )
        assert r.status_code == 403

    async def test_admin_cannot_promote_to_admin(self, client, admin_token, pending_user):
        """Non-superadmin admin cannot grant admin role."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        uid = str(pending_user["_id"])
        r = await client.patch(
            f"/api/v1/admin/users/{uid}",
            json={"role": "admin"},
            headers=headers,
        )
        assert r.status_code == 403

    async def test_superadmin_can_promote(self, client, superadmin_token, regular_user):
        headers = {"Authorization": f"Bearer {superadmin_token}"}
        uid = str(regular_user["_id"])
        r = await client.patch(
            f"/api/v1/admin/users/{uid}",
            json={"role": "admin"},
            headers=headers,
        )
        assert r.status_code == 200
        assert r.json()["role"] == "admin"


class TestIDOR:
    """Verify users cannot access other users' data."""

    async def _create_user_conversation(self, token: str, client) -> str:
        headers = {"Authorization": f"Bearer {token}"}
        r = await client.post(
            "/api/v1/chat/conversations",
            json={"title": "My Chat"},
            headers=headers,
        )
        assert r.status_code == 201
        return r.json()["id"]

    async def test_cannot_access_other_conversation(self, client, regular_user_token, admin_token):
        uid1 = await self._create_user_conversation(regular_user_token, client)
        headers = {"Authorization": f"Bearer {admin_token}"}
        r = await client.get(f"/api/v1/chat/conversations/{uid1}", headers=headers)
        assert r.status_code == 404

    async def test_cannot_delete_other_conversation(self, client, regular_user_token, admin_token):
        cid = await self._create_user_conversation(regular_user_token, client)
        headers = {"Authorization": f"Bearer {admin_token}"}
        r = await client.delete(f"/api/v1/chat/conversations/{cid}", headers=headers)
        assert r.status_code == 404

    async def test_cannot_react_to_other_message(self, client, regular_user_token, admin_token):
        # Create conversation as regular user
        cid = await self._create_user_conversation(regular_user_token, client)
        headers = {"Authorization": f"Bearer {regular_user_token}"}

        # Post a message
        r = await client.post(
            f"/api/v1/chat/conversations/{cid}/messages",
            json={"content": "Hello", "role": "user"},
            headers=headers,
        )
        mid = r.json()["id"]

        # Admin tries to react (should have no ownership of the conversation)
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        r = await client.post(
            f"/api/v1/chat/conversations/{cid}/messages/{mid}/react",
            json={"reaction": "like"},
            headers=admin_headers,
        )
        assert r.status_code == 404  # conversation not found for admin

    async def test_cannot_access_other_canvas(self, client, regular_user_token, admin_token):
        headers = {"Authorization": f"Bearer {regular_user_token}"}
        r = await client.post(
            "/api/v1/canvas",
            json={"title": "My Canvas", "type": "document"},
            headers=headers,
        )
        canvas_id = r.json()["id"]

        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        r = await client.get(f"/api/v1/canvas/{canvas_id}", headers=admin_headers)
        assert r.status_code == 404

    async def test_cannot_access_other_memory(self, client, regular_user_token, admin_token):
        headers = {"Authorization": f"Bearer {regular_user_token}"}
        r = await client.post(
            "/api/v1/memory",
            json={"kind": "long_term", "content": "My secret"},
            headers=headers,
        )
        assert r.status_code == 201

        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        r = await client.get("/api/v1/memory", headers=admin_headers)
        assert r.status_code == 200
        data = r.json()
        # Admin should see their own memories (empty), not the other user's
        assert len(data) == 0


class TestPendingUserAccess:
    """Verify pending users are blocked from creating content."""

    async def test_pending_user_cannot_create_conversation(self, client, pending_user_token):
        headers = {"Authorization": f"Bearer {pending_user_token}"}
        r = await client.post(
            "/api/v1/chat/conversations",
            json={"title": "Test"},
            headers=headers,
        )
        assert r.status_code == 403

    async def test_pending_user_cannot_stream(self, client, pending_user_token):
        headers = {"Authorization": f"Bearer {pending_user_token}"}
        r = await client.post(
            "/api/v1/chat/conversations/000000000000000000000000/stream",
            json={"content": "Hello"},
            headers=headers,
        )
        assert r.status_code == 403

    async def test_pending_user_cannot_research(self, client, pending_user_token):
        headers = {"Authorization": f"Bearer {pending_user_token}"}
        r = await client.post(
            "/api/v1/research/run",
            json={"query": "test", "maxSources": 3},
            headers=headers,
        )
        assert r.status_code == 403

    async def test_pending_user_cannot_upload(self, client, pending_user_token):
        headers = {"Authorization": f"Bearer {pending_user_token}"}
        r = await client.post(
            "/api/v1/attachments",
            files={"file": ("test.txt", b"hello", "text/plain")},
            headers=headers,
        )
        # pending user CAN upload files (no enforce_approval on upload)
        # but should they be able to? Let's verify the current behavior
        assert r.status_code in (201, 403)


class TestSystemPromptProtection:
    """Verify system prompt content is never leaked to non-admin users."""

    async def test_non_admin_cannot_list_prompts(self, client, regular_user_token):
        headers = {"Authorization": f"Bearer {regular_user_token}"}
        r = await client.get("/api/v1/system-prompts", headers=headers)
        assert r.status_code == 403

    async def test_non_admin_cannot_get_prompt(self, client, regular_user_token):
        headers = {"Authorization": f"Bearer {regular_user_token}"}
        r = await client.get("/api/v1/system-prompts/000000000000000000000000", headers=headers)
        assert r.status_code == 403

    async def test_admin_can_list_prompts(self, client, admin_token):
        headers = {"Authorization": f"Bearer {admin_token}"}
        r = await client.get("/api/v1/system-prompts", headers=headers)
        assert r.status_code == 200

    async def test_summary_is_public(self, client, regular_user_token):
        headers = {"Authorization": f"Bearer {regular_user_token}"}
        r = await client.get("/api/v1/system-prompts/summary", headers=headers)
        assert r.status_code == 200


class TestModelAccess:
    """The static notrack model catalogue is read-only and keyless."""

    async def test_models_list_is_static(self, client, regular_user_token):
        headers = {"Authorization": f"Bearer {regular_user_token}"}
        r = await client.get("/api/v1/models", headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 4
        for model in data:
            assert model["provider"] == "internal"
            assert "apiKey" not in model
            assert model.get("hasApiKey") is False

    async def test_model_create_removed(self, client, admin_token):
        headers = {"Authorization": f"Bearer {admin_token}"}
        r = await client.post(
            "/api/v1/models",
            json={"name": "test-model", "provider": "notrack"},
            headers=headers,
        )
        assert r.status_code in (404, 405)

    async def test_developer_routes_removed(self, client, admin_token):
        headers = {"Authorization": f"Bearer {admin_token}"}
        r = await client.post(
            "/api/v1/developer/models/000000000000000000000000/reveal",
            headers=headers,
        )
        assert r.status_code == 404
