"""Integration tests for removed admin/RBAC surfaces, IDOR prevention,
and ownership checks.

Requires a running MongoDB instance.
"""

from __future__ import annotations

import os

import pytest

pytestmark = [
    pytest.mark.skipif(
        os.environ.get("SKIP_MONGO_TESTS", "1") == "1",
        reason="MongoDB not available; set SKIP_MONGO_TESTS=0 to run",
    ),
]


class TestAdminRemoved:
    """The admin API no longer exists at all."""

    async def test_admin_users_route_gone(self, client, regular_user_token):
        headers = {"Authorization": f"Bearer {regular_user_token}"}
        r = await client.get("/api/v1/admin/users", headers=headers)
        assert r.status_code == 404

    async def test_admin_stats_route_gone(self, client, regular_user_token):
        headers = {"Authorization": f"Bearer {regular_user_token}"}
        r = await client.get("/api/v1/admin/stats", headers=headers)
        assert r.status_code == 404

    async def test_admin_audit_logs_route_gone(self, client, regular_user_token):
        headers = {"Authorization": f"Bearer {regular_user_token}"}
        r = await client.get("/api/v1/admin/audit-logs", headers=headers)
        assert r.status_code == 404

    async def test_prompts_routes_gone(self, client, regular_user_token):
        headers = {"Authorization": f"Bearer {regular_user_token}"}
        r = await client.get("/api/v1/system-prompts", headers=headers)
        assert r.status_code == 404

    async def test_me_has_no_role_field(self, client, regular_user_token):
        headers = {"Authorization": f"Bearer {regular_user_token}"}
        r = await client.get("/api/v1/auth/me", headers=headers)
        assert r.status_code == 200
        assert "role" not in r.json()


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

    async def test_cannot_access_other_conversation(self, client, regular_user_token, second_user_token):
        uid1 = await self._create_user_conversation(regular_user_token, client)
        headers = {"Authorization": f"Bearer {second_user_token}"}
        r = await client.get(f"/api/v1/chat/conversations/{uid1}", headers=headers)
        assert r.status_code == 404

    async def test_cannot_delete_other_conversation(self, client, regular_user_token, second_user_token):
        cid = await self._create_user_conversation(regular_user_token, client)
        headers = {"Authorization": f"Bearer {second_user_token}"}
        r = await client.delete(f"/api/v1/chat/conversations/{cid}", headers=headers)
        assert r.status_code == 404

    async def test_cannot_react_to_other_message(self, client, regular_user_token, second_user_token):
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

        # Another user tries to react (should have no ownership of the conversation)
        other_headers = {"Authorization": f"Bearer {second_user_token}"}
        r = await client.post(
            f"/api/v1/chat/conversations/{cid}/messages/{mid}/react",
            json={"reaction": "like"},
            headers=other_headers,
        )
        assert r.status_code == 404  # conversation not found for them

    async def test_cannot_access_other_canvas(self, client, regular_user_token, second_user_token):
        headers = {"Authorization": f"Bearer {regular_user_token}"}
        r = await client.post(
            "/api/v1/canvas",
            json={"title": "My Canvas", "type": "document"},
            headers=headers,
        )
        canvas_id = r.json()["id"]

        other_headers = {"Authorization": f"Bearer {second_user_token}"}
        r = await client.get(f"/api/v1/canvas/{canvas_id}", headers=other_headers)
        assert r.status_code == 404

    async def test_cannot_access_other_memory(self, client, regular_user_token, second_user_token):
        headers = {"Authorization": f"Bearer {regular_user_token}"}
        r = await client.post(
            "/api/v1/memory",
            json={"kind": "long_term", "content": "My secret"},
            headers=headers,
        )
        assert r.status_code == 201

        other_headers = {"Authorization": f"Bearer {second_user_token}"}
        r = await client.get("/api/v1/memory", headers=other_headers)
        assert r.status_code == 200
        data = r.json()
        # The other user should see their own memories (empty), not ours
        assert len(data) == 0


class TestModelAccess:
    """The static notrack model catalogue is read-only and credential-less."""

    async def test_models_list_is_static(self, client, regular_user_token):
        headers = {"Authorization": f"Bearer {regular_user_token}"}
        r = await client.get("/api/v1/models", headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 4
        for model in data:
            assert "apiKey" not in model
            assert "provider" not in model
            assert "hasApiKey" not in model

    async def test_model_create_removed(self, client, regular_user_token):
        headers = {"Authorization": f"Bearer {regular_user_token}"}
        r = await client.post(
            "/api/v1/models",
            json={"name": "test-model"},
            headers=headers,
        )
        assert r.status_code in (404, 405)

    async def test_developer_routes_removed(self, client, regular_user_token):
        headers = {"Authorization": f"Bearer {regular_user_token}"}
        r = await client.post(
            "/api/v1/developer/models/000000000000000000000000/reveal",
            headers=headers,
        )
        assert r.status_code == 404
