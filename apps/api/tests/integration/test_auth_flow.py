"""Integration tests for authentication flows.

Requires a running MongoDB instance.
Marked with @pytest.mark.mongo which can be skipped.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest
import pytest_asyncio

from app.core.security import hash_password
from app.db import mongo

pytestmark = [
    pytest.mark.skipif(
        os.environ.get("SKIP_MONGO_TESTS", "1") == "1",
        reason="MongoDB not available; set SKIP_MONGO_TESTS=0 to run",
    ),
]


class TestRegister:
    async def test_register_success(self, client):
        payload = {
            "username": "newuser",
            "email": "new@test.local",
            "password": "StrongPass1!",
        }
        r = await client.post("/api/v1/auth/register", json=payload)
        assert r.status_code == 201
        data = r.json()
        assert "accessToken" in data
        assert "refreshToken" in data
        assert data["user"]["username"] == "newuser"
        assert data["user"]["status"] == "approved"
        assert "role" not in data["user"]

    async def test_register_duplicate_email(self, client, regular_user):
        payload = {
            "username": "another",
            "email": regular_user["email"],
            "password": "StrongPass1!",
        }
        r = await client.post("/api/v1/auth/register", json=payload)
        assert r.status_code == 409

    async def test_register_duplicate_username(self, client, regular_user):
        payload = {
            "username": regular_user["username"],
            "email": "other@test.local",
            "password": "StrongPass1!",
        }
        r = await client.post("/api/v1/auth/register", json=payload)
        assert r.status_code == 409

    async def test_register_weak_password(self, client):
        payload = {
            "username": "weakpass",
            "email": "weak@test.local",
            "password": "short",
        }
        r = await client.post("/api/v1/auth/register", json=payload)
        assert r.status_code == 422

    async def test_register_invalid_username(self, client):
        payload = {
            "username": "<script>alert(1)</script>",
            "email": "xss@test.local",
            "password": "StrongPass1!",
        }
        r = await client.post("/api/v1/auth/register", json=payload)
        assert r.status_code == 422

    async def test_register_invalid_email(self, client):
        payload = {
            "username": "validuser",
            "email": "not-an-email",
            "password": "StrongPass1!",
        }
        r = await client.post("/api/v1/auth/register", json=payload)
        assert r.status_code == 422


class TestLogin:
    async def test_login_success(self, client, regular_user):
        payload = {"email": regular_user["email"], "password": "TestPass123!"}
        r = await client.post("/api/v1/auth/login", json=payload)
        assert r.status_code == 200
        data = r.json()
        assert "accessToken" in data
        assert "refreshToken" in data

    async def test_login_wrong_password(self, client, regular_user):
        payload = {"email": regular_user["email"], "password": "WrongPass123!"}
        r = await client.post("/api/v1/auth/login", json=payload)
        assert r.status_code == 401

    async def test_login_nonexistent_user(self, client):
        payload = {"email": "noone@test.local", "password": "TestPass123!"}
        r = await client.post("/api/v1/auth/login", json=payload)
        assert r.status_code == 401

    async def test_account_lockout_after_8_failures(self, client, regular_user):
        email = regular_user["email"]
        for _ in range(8):
            r = await client.post("/api/v1/auth/login", json={"email": email, "password": "WrongPass123!"})
            assert r.status_code == 401
        # 9th attempt should be locked
        r = await client.post("/api/v1/auth/login", json={"email": email, "password": "WrongPass123!"})
        assert r.status_code == 423

    async def test_refresh_token_not_stored_on_login(self, client, regular_user, settings):
        """Verify refresh token is stored in DB after login (Fix #1)."""
        payload = {"email": regular_user["email"], "password": "TestPass123!"}
        r = await client.post("/api/v1/auth/login", json=payload)
        assert r.status_code == 200
        rt = r.json()["refreshToken"]
        # Check DB
        stored = await mongo.refresh_tokens().find_one({"token": rt})
        assert stored is not None
        assert stored["revoked"] is False


class TestRefresh:
    async def test_refresh_rotation(self, client, regular_user):
        """Verify old refresh token is revoked after refresh (Fix #1)."""
        payload = {"email": regular_user["email"], "password": "TestPass123!"}
        r = await client.post("/api/v1/auth/login", json=payload)
        assert r.status_code == 200
        old_rt = r.json()["refreshToken"]

        # Refresh
        r2 = await client.post("/api/v1/auth/refresh", json={"refreshToken": old_rt})
        assert r2.status_code == 200

        # Old token should be revoked
        stored = await mongo.refresh_tokens().find_one({"token": old_rt})
        assert stored is not None
        assert stored["revoked"] is True

    async def test_refresh_with_revoked_token_fails(self, client, regular_user):
        payload = {"email": regular_user["email"], "password": "TestPass123!"}
        r = await client.post("/api/v1/auth/login", json=payload)
        rt = r.json()["refreshToken"]

        # Refresh (consumes old token)
        await client.post("/api/v1/auth/refresh", json={"refreshToken": rt})

        # Try to reuse old token
        r2 = await client.post("/api/v1/auth/refresh", json={"refreshToken": rt})
        assert r2.status_code == 401

    async def test_refresh_expired_token_fails(self, client):
        import jwt as pyjwt
        from datetime import datetime, timedelta, timezone

        expired = pyjwt.encode(
            {
                "sub": "000000000000000000000001",
                "sid": "test",
                "exp": 0,
                "iat": 0,
                "type": "refresh",
                "jti": "dead",
            },
            "test-jwt-secret-for-testing-only",
            algorithm="HS256",
        )
        r = await client.post("/api/v1/auth/refresh", json={"refreshToken": expired})
        assert r.status_code == 401

    async def test_refresh_wrong_type_fails(self, client):
        from app.core.security import create_access_token

        access = create_access_token(sub="000000000000000000000001")
        r = await client.post("/api/v1/auth/refresh", json={"refreshToken": access})
        assert r.status_code == 401


class TestMe:
    async def test_me_authenticated(self, client, regular_user_token):
        headers = {"Authorization": f"Bearer {regular_user_token}"}
        r = await client.get("/api/v1/auth/me", headers=headers)
        assert r.status_code == 200

    async def test_me_unauthenticated(self, client):
        r = await client.get("/api/v1/auth/me")
        assert r.status_code == 401


class TestChangePassword:
    async def test_change_password(self, client, regular_user, regular_user_token):
        headers = {"Authorization": f"Bearer {regular_user_token}"}
        r = await client.post(
            "/api/v1/auth/change-password",
            json={"oldPassword": "TestPass123!", "newPassword": "NewPass123!!"},
            headers=headers,
        )
        assert r.status_code == 204

        # Login with new password
        r2 = await client.post("/api/v1/auth/login", json={
            "email": regular_user["email"], "password": "NewPass123!!",
        })
        assert r2.status_code == 200

    async def test_change_password_wrong_old(self, client, regular_user_token):
        headers = {"Authorization": f"Bearer {regular_user_token}"}
        r = await client.post(
            "/api/v1/auth/change-password",
            json={"oldPassword": "WrongOldPass!", "newPassword": "NewPass123!!"},
            headers=headers,
        )
        assert r.status_code == 400

    async def test_change_password_weak_new(self, client, regular_user_token):
        headers = {"Authorization": f"Bearer {regular_user_token}"}
        r = await client.post(
            "/api/v1/auth/change-password",
            json={"oldPassword": "TestPass123!", "newPassword": "short"},
            headers=headers,
        )
        assert r.status_code == 422


class TestSuspendedRejectedUsers:
    async def test_suspended_user_cannot_access(self, client, suspended_user_token):
        headers = {"Authorization": f"Bearer {suspended_user_token}"}
        r = await client.get("/api/v1/auth/me", headers=headers)
        assert r.status_code == 403

    async def test_rejected_user_cannot_access(self, client, rejected_user_token):
        headers = {"Authorization": f"Bearer {rejected_user_token}"}
        r = await client.get("/api/v1/auth/me", headers=headers)
        assert r.status_code == 403


class TestPasswordReset:
    async def test_forgot_password_returns_ok(self, client, regular_user):
        r = await client.post("/api/v1/auth/forgot-password", json={
            "email": regular_user["email"],
        })
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True

    async def test_forgot_nonexistent_user_still_returns_ok(self, client):
        """No user enumeration."""
        r = await client.post("/api/v1/auth/forgot-password", json={
            "email": "nobody@test.local",
        })
        assert r.status_code == 200
        assert r.json()["ok"] is True

    async def test_reset_password_flow(self, client, regular_user):
        # Request reset
        r1 = await client.post("/api/v1/auth/forgot-password", json={
            "email": regular_user["email"],
        })
        token = r1.json()["devToken"]

        # Reset password
        r2 = await client.post("/api/v1/auth/reset-password", json={
            "token": token,
            "newPassword": "ResetPass123!",
        })
        assert r2.status_code == 204

        # Login with new password
        r3 = await client.post("/api/v1/auth/login", json={
            "email": regular_user["email"],
            "password": "ResetPass123!",
        })
        assert r3.status_code == 200

    async def test_reset_password_twice_fails(self, client, regular_user):
        r1 = await client.post("/api/v1/auth/forgot-password", json={
            "email": regular_user["email"],
        })
        token = r1.json()["devToken"]

        await client.post("/api/v1/auth/reset-password", json={
            "token": token, "newPassword": "ResetPass123!",
        })
        r2 = await client.post("/api/v1/auth/reset-password", json={
            "token": token, "newPassword": "AnotherPass123!",
        })
        assert r2.status_code == 400  # used token

    async def test_reset_password_revokes_sessions(self, client, regular_user):
        """After password reset, all refresh tokens should be revoked."""
        # Login first
        r1 = await client.post("/api/v1/auth/login", json={
            "email": regular_user["email"], "password": "TestPass123!",
        })
        old_rt = r1.json()["refreshToken"]

        # Reset password
        r2 = await client.post("/api/v1/auth/forgot-password", json={
            "email": regular_user["email"],
        })
        token = r2.json()["devToken"]
        await client.post("/api/v1/auth/reset-password", json={
            "token": token, "newPassword": "ResetPass123!",
        })

        # Old refresh should be revoked
        stored = await mongo.refresh_tokens().find_one({"token": old_rt})
        assert stored is not None
        assert stored["revoked"] is True
