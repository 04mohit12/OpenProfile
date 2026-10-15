
from fastapi.testclient import TestClient

from backend.app import main
from backend.app.services import auth_service


client = TestClient(main.app)


def test_me_requires_authentication():
    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401


def test_invalid_otp_returns_401(monkeypatch):
    monkeypatch.setattr(
        auth_service, "verify_otp", lambda email, otp: False
    )

    response = client.post(
        "/api/v1/auth/verify-otp",
        json={
            "email": "approved@example.com",
            "otp": "123456",
        },
    )

    assert response.status_code == 401


def test_invalid_email_is_rejected():
    response = client.post(
        "/api/v1/auth/request-otp",
        json={"email": "not-an-email"},
    )

    assert response.status_code == 422


def test_malformed_otp_is_rejected():
    response = client.post(
        "/api/v1/auth/verify-otp",
        json={
            "email": "approved@example.com",
            "otp": "12AB",
        },
    )

    assert response.status_code == 422


def test_successful_verification_sets_session_cookie(monkeypatch):
    monkeypatch.setattr(
        auth_service, "verify_otp", lambda email, otp: True
    )
    monkeypatch.setattr(
        auth_service,
        "create_session",
        lambda email: "test-session-token",
    )

    response = client.post(
        "/api/v1/auth/verify-otp",
        json={
            "email": "approved@example.com",
            "otp": "123456",
        },
    )

    assert response.status_code == 200
    assert response.json()["message"] == "Login successful."

    cookie = response.headers["set-cookie"]
    assert "openprofile_session=test-session-token" in cookie
    assert "httponly" in cookie.lower()


def test_logout_clears_session_cookie(monkeypatch):
    revoked = []

    monkeypatch.setattr(
        auth_service, "revoke_session", lambda token: revoked.append(token)
    )
    client.cookies.set("openprofile_session", "test-session-token")

    response = client.post("/api/v1/auth/logout")

    assert response.status_code == 200
    assert response.json()["message"] == "Logged out successfully."
    assert revoked == ["test-session-token"]
    assert "openprofile_session=" in response.headers["set-cookie"]
    assert "max-age=0" in response.headers["set-cookie"].lower()

    client.cookies.clear()


def test_otp_verification_database_failure(monkeypatch):
    def raise_database_error(email, otp):
        raise RuntimeError("Database unavailable")

    monkeypatch.setattr(
        auth_service,
        "verify_otp",
        raise_database_error,
    )

    response = client.post(
        "/api/v1/auth/verify-otp",
        json={
            "email": "approved@example.com",
            "otp": "123456",
        },
    )

    assert response.status_code == 503
    assert "Database unavailable" not in response.text
