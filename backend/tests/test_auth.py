"""
test_auth.py — Phase 1 auth tests.

Covers:
  - register success, duplicate email, short password
  - login success, wrong password, unknown email (same 401 message)
  - /me with valid token, no token, tampered token, expired token
  - password_hash never appears in any response
"""

import time
import uuid

import jwt
import pytest
from fastapi.testclient import TestClient


# ── Helpers ────────────────────────────────────────────────────────────

def _register(client: TestClient, email: str, password: str = "password123", name: str = "Test User"):
    return client.post("/api/auth/register", json={"name": name, "email": email, "password": password})


def _login(client: TestClient, email: str, password: str = "password123"):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def _unique_email() -> str:
    return f"test_{uuid.uuid4().hex[:8]}@example.com"


# ── Register ───────────────────────────────────────────────────────────

class TestRegister:
    def test_register_success(self, client):
        r = _register(client, _unique_email())
        assert r.status_code == 201
        body = r.json()
        assert body["email"] == body["email"].lower()
        assert "id" in body
        assert "created_at" in body

    def test_register_stores_email_lowercase(self, client):
        r = _register(client, "UPPER@Example.COM")
        assert r.status_code == 201
        assert r.json()["email"] == "upper@example.com"

    def test_register_duplicate_email_409(self, client):
        email = _unique_email()
        _register(client, email)
        r = _register(client, email)
        assert r.status_code == 409

    def test_register_short_password_422(self, client):
        r = _register(client, _unique_email(), password="short")
        assert r.status_code == 422

    def test_password_hash_never_in_response(self, client):
        r = _register(client, _unique_email())
        assert "password_hash" not in r.text
        assert "password" not in r.json()


# ── Login ──────────────────────────────────────────────────────────────

class TestLogin:
    def test_login_success(self, client):
        email = _unique_email()
        _register(client, email)
        r = _login(client, email)
        assert r.status_code == 200
        body = r.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"

    def test_login_wrong_password_401(self, client):
        email = _unique_email()
        _register(client, email)
        r = _login(client, email, password="wrongpassword")
        assert r.status_code == 401

    def test_login_email_stripped_and_lowercased(self, client):
        """Login must accept email with whitespace and mixed case."""
        email = _unique_email()
        _register(client, email)
        r = client.post("/api/auth/login", json={"email": f"  {email.upper()}  ", "password": "password123"})
        assert r.status_code == 200

    def test_login_unknown_email_401(self, client):
        r = _login(client, "nobody@nowhere.com")
        assert r.status_code == 401

    def test_wrong_password_and_unknown_email_same_message(self, client):
        """Security: same error message for both failures — no enumeration."""
        email = _unique_email()
        _register(client, email)
        r_wrong_pw = _login(client, email, password="wrongpassword")
        r_unknown = _login(client, "nobody@nowhere.com")
        assert r_wrong_pw.json()["detail"] == r_unknown.json()["detail"]

    def test_password_hash_never_in_login_response(self, client):
        email = _unique_email()
        _register(client, email)
        r = _login(client, email)
        assert "password_hash" not in r.text


# ── /me ────────────────────────────────────────────────────────────────

class TestMe:
    def _get_token(self, client: TestClient) -> str:
        email = _unique_email()
        _register(client, email)
        return _login(client, email).json()["access_token"]

    def test_me_valid_token(self, client):
        token = self._get_token(client)
        r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert "email" in r.json()

    def test_me_no_token_401(self, client):
        r = client.get("/api/auth/me")
        assert r.status_code == 401  # auto_error=False → we raise 401 ourselves

    def test_me_tampered_token_401(self, client):
        token = self._get_token(client)
        # Flip the last character to tamper with signature
        bad_token = token[:-1] + ("A" if token[-1] != "A" else "B")
        r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {bad_token}"})
        assert r.status_code == 401

    def test_me_expired_token_401(self, client):
        from app.core.config import settings
        from datetime import datetime, timedelta, timezone
        payload = {
            "sub": str(uuid.uuid4()),
            "type": "access",
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) - timedelta(seconds=1),
        }
        expired_token = jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")
        r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
        assert r.status_code == 401

    def test_me_no_password_hash_in_response(self, client):
        token = self._get_token(client)
        r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert "password_hash" not in r.text
