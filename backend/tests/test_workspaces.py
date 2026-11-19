"""
test_workspaces.py — Phase 1 workspace tests.

Covers:
  - user A creates workspace, appears in their list
  - user B cannot GET, list, delete, or add members (all 404)
  - user A can GET, list, delete
  - owner cannot be removed
  - non-owner member cannot delete workspace
  - password_hash never appears in any response
"""

import uuid
import pytest
from fastapi.testclient import TestClient


# ── Helpers ────────────────────────────────────────────────────────────

def _unique_email() -> str:
    return f"ws_{uuid.uuid4().hex[:8]}@example.com"


def _register_and_login(client: TestClient, email: str = None, password: str = "password123"):
    email = email or _unique_email()
    client.post("/api/auth/register", json={"name": "User", "email": email, "password": password})
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    return r.json()["access_token"], email


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _create_ws(client: TestClient, token: str, name: str = "My Workspace"):
    return client.post("/api/workspaces", json={"name": name}, headers=_auth(token))


# ── Workspace creation ─────────────────────────────────────────────────

class TestCreateWorkspace:
    def test_create_success(self, client):
        token, _ = _register_and_login(client)
        r = _create_ws(client, token)
        assert r.status_code == 201
        body = r.json()
        assert body["name"] == "My Workspace"
        assert "id" in body
        assert "owner_id" in body

    def test_create_requires_auth(self, client):
        r = client.post("/api/workspaces", json={"name": "No Auth"})
        assert r.status_code == 401  # auto_error=False → we raise 401 ourselves

    def test_creator_appears_in_list(self, client):
        token, _ = _register_and_login(client)
        _create_ws(client, token, name="Listed WS")
        r = client.get("/api/workspaces", headers=_auth(token))
        assert r.status_code == 200
        names = [ws["name"] for ws in r.json()]
        assert "Listed WS" in names


# ── Access control: non-member ─────────────────────────────────────────

class TestNonMemberAccess:
    """User B is not a member; all requests must return 404."""

    def _setup(self, client):
        token_a, _ = _register_and_login(client)
        token_b, email_b = _register_and_login(client)
        ws_id = _create_ws(client, token_a).json()["id"]
        return token_a, token_b, email_b, ws_id

    def test_non_member_cannot_get_workspace(self, client):
        _, token_b, _, ws_id = self._setup(client)
        r = client.get(f"/api/workspaces/{ws_id}", headers=_auth(token_b))
        assert r.status_code == 404

    def test_non_member_workspace_not_in_list(self, client):
        _, token_b, _, ws_id = self._setup(client)
        r = client.get("/api/workspaces", headers=_auth(token_b))
        assert r.status_code == 200
        ids = [ws["id"] for ws in r.json()]
        assert ws_id not in ids

    def test_non_member_cannot_delete_workspace(self, client):
        _, token_b, _, ws_id = self._setup(client)
        r = client.delete(f"/api/workspaces/{ws_id}", headers=_auth(token_b))
        assert r.status_code == 404

    def test_non_member_cannot_add_members(self, client):
        _, token_b, email_b, ws_id = self._setup(client)
        r = client.post(
            f"/api/workspaces/{ws_id}/members",
            json={"email": email_b},
            headers=_auth(token_b),
        )
        assert r.status_code == 404

    def test_non_member_cannot_list_members(self, client):
        _, token_b, _, ws_id = self._setup(client)
        r = client.get(f"/api/workspaces/{ws_id}/members", headers=_auth(token_b))
        assert r.status_code == 404


# ── Owner operations ───────────────────────────────────────────────────

class TestOwnerOperations:
    def test_owner_can_add_member(self, client):
        token_a, _ = _register_and_login(client)
        _, email_b = _register_and_login(client)
        ws_id = _create_ws(client, token_a).json()["id"]

        r = client.post(
            f"/api/workspaces/{ws_id}/members",
            json={"email": email_b},
            headers=_auth(token_a),
        )
        assert r.status_code == 201

    def test_owner_can_list_members(self, client):
        token_a, _ = _register_and_login(client)
        ws_id = _create_ws(client, token_a).json()["id"]
        r = client.get(f"/api/workspaces/{ws_id}/members", headers=_auth(token_a))
        assert r.status_code == 200
        assert len(r.json()) >= 1

    def test_owner_cannot_be_removed(self, client):
        token_a, _ = _register_and_login(client)
        token_b, email_b = _register_and_login(client)
        ws_id = _create_ws(client, token_a).json()["id"]

        # Add B as member, B gets token
        client.post(
            f"/api/workspaces/{ws_id}/members",
            json={"email": email_b},
            headers=_auth(token_a),
        )

        # Get owner's user_id via /me
        owner_id = client.get("/api/auth/me", headers=_auth(token_a)).json()["id"]

        # Even if someone tried to remove the owner (here: owner tries to remove self)
        r = client.delete(
            f"/api/workspaces/{ws_id}/members/{owner_id}",
            headers=_auth(token_a),
        )
        assert r.status_code == 400

    def test_owner_can_delete_workspace(self, client):
        token_a, _ = _register_and_login(client)
        ws_id = _create_ws(client, token_a).json()["id"]
        r = client.delete(f"/api/workspaces/{ws_id}", headers=_auth(token_a))
        assert r.status_code == 204

    def test_duplicate_member_409(self, client):
        token_a, _ = _register_and_login(client)
        _, email_b = _register_and_login(client)
        ws_id = _create_ws(client, token_a).json()["id"]

        client.post(f"/api/workspaces/{ws_id}/members", json={"email": email_b}, headers=_auth(token_a))
        r = client.post(f"/api/workspaces/{ws_id}/members", json={"email": email_b}, headers=_auth(token_a))
        assert r.status_code == 409


# ── Non-owner member restrictions ──────────────────────────────────────

class TestMemberRestrictions:
    def _setup_with_member(self, client):
        token_a, _ = _register_and_login(client)
        token_b, email_b = _register_and_login(client)
        ws_id = _create_ws(client, token_a).json()["id"]
        client.post(
            f"/api/workspaces/{ws_id}/members",
            json={"email": email_b},
            headers=_auth(token_a),
        )
        return token_a, token_b, ws_id

    def test_member_can_get_workspace(self, client):
        _, token_b, ws_id = self._setup_with_member(client)
        r = client.get(f"/api/workspaces/{ws_id}", headers=_auth(token_b))
        assert r.status_code == 200

    def test_member_cannot_delete_workspace(self, client):
        _, token_b, ws_id = self._setup_with_member(client)
        r = client.delete(f"/api/workspaces/{ws_id}", headers=_auth(token_b))
        assert r.status_code == 403

    def test_member_cannot_add_members(self, client):
        _, token_b, ws_id = self._setup_with_member(client)
        _, email_c = _register_and_login(client)
        r = client.post(
            f"/api/workspaces/{ws_id}/members",
            json={"email": email_c},
            headers=_auth(token_b),
        )
        assert r.status_code == 403

    def test_member_workspace_appears_in_list(self, client):
        _, token_b, ws_id = self._setup_with_member(client)
        r = client.get("/api/workspaces", headers=_auth(token_b))
        assert r.status_code == 200
        ids = [ws["id"] for ws in r.json()]
        assert ws_id in ids


# ── Password hash never in responses ──────────────────────────────────

class TestNoPasswordHashLeak:
    def test_workspace_response_no_hash(self, client):
        token, _ = _register_and_login(client)
        r = _create_ws(client, token)
        assert "password_hash" not in r.text

    def test_members_response_no_hash(self, client):
        token, _ = _register_and_login(client)
        ws_id = _create_ws(client, token).json()["id"]
        r = client.get(f"/api/workspaces/{ws_id}/members", headers=_auth(token))
        assert "password_hash" not in r.text
