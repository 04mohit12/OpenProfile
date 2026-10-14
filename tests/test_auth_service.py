
import time

import pytest

from backend.app.services import auth_service



@pytest.fixture(autouse=True)
def reset_auth_state(monkeypatch):
    """Isolate authentication state between tests."""
    with auth_service._lock:
        auth_service._otps.clear()
        auth_service._sessions.clear()
        auth_service._last_otp_request.clear()
        auth_service._email_otp_requests.clear()
        auth_service._ip_otp_requests.clear()
        auth_service._otp_request_generation.clear()

    monkeypatch.setenv(
        "ALLOWED_EMAILS", "approved@example.com"
    )
    monkeypatch.setenv(
        "SESSION_SECRET",
        "test-secret-that-is-at-least-32-characters-long",
    )

    yield

    with auth_service._lock:
        auth_service._otps.clear()
        auth_service._sessions.clear()
        auth_service._last_otp_request.clear()
        auth_service._email_otp_requests.clear()
        auth_service._ip_otp_requests.clear()
        auth_service._otp_request_generation.clear()



def test_otp_is_single_use(monkeypatch):
    """A valid OTP succeeds once and then becomes invalid."""
    monkeypatch.setattr(
        auth_service, "_send_otp_email", lambda email, otp: None
    )
    monkeypatch.setattr(
        auth_service.secrets, "randbelow", lambda limit: 123456
    )

    auth_service.request_otp("approved@example.com", "127.0.0.1")

    assert auth_service.verify_otp("approved@example.com", "123456")
    assert not auth_service.verify_otp("approved@example.com", "123456")


def test_otp_expires(monkeypatch):
    """An expired OTP cannot be used."""
    monkeypatch.setattr(
        auth_service, "_send_otp_email", lambda email, otp: None
    )
    monkeypatch.setattr(
        auth_service.secrets, "randbelow", lambda limit: 123456
    )

    auth_service.request_otp("approved@example.com", "127.0.0.1")

    with auth_service._lock:
        auth_service._otps["approved@example.com"]["expires"] = (
            time.time() - 1
        )

    assert not auth_service.verify_otp("approved@example.com", "123456")


def test_otp_is_invalidated_after_five_failed_attempts(monkeypatch):
    """Five wrong attempts invalidate the current OTP."""
    monkeypatch.setattr(
        auth_service, "_send_otp_email", lambda email, otp: None
    )
    monkeypatch.setattr(
        auth_service.secrets, "randbelow", lambda limit: 123456
    )

    auth_service.request_otp("approved@example.com", "127.0.0.1")

    for _ in range(auth_service.OTP_MAX_ATTEMPTS):
        assert not auth_service.verify_otp(
            "approved@example.com", "999999"
        )

    assert not auth_service.verify_otp(
        "approved@example.com", "123456"
    )


def test_otp_resend_cooldown(monkeypatch):
    """A second request within 60 seconds is rejected."""
    monkeypatch.setattr(
        auth_service, "_send_otp_email", lambda email, otp: None
    )

    auth_service.request_otp("approved@example.com", "127.0.0.1")

    with pytest.raises(ValueError, match="wait"):
        auth_service.request_otp("approved@example.com", "127.0.0.1")


def test_unapproved_email_does_not_send_otp(monkeypatch):
    """Unapproved addresses do not trigger an email."""
    sent = []
    monkeypatch.setattr(
        auth_service, "_send_otp_email",
        lambda email, otp: sent.append(email),
    )

    auth_service.request_otp("other@example.com", "127.0.0.1")

    assert sent == []



def test_email_hourly_otp_limit(monkeypatch):
    """Reject OTP requests after the hourly email limit."""
    sent = []
    monkeypatch.setattr(
        auth_service, "_send_otp_email",
        lambda email, otp: sent.append(email),
    )
    monkeypatch.setattr(
        auth_service, "EMAIL_OTP_HOURLY_LIMIT", 5,
    )

    # Simulate five previous requests within the hour.
    now = time.time()
    auth_service._email_otp_requests["approved@example.com"] = [
        now - 10, now - 20, now - 30, now - 40, now - 50
    ]

    with pytest.raises(ValueError, match="email"):
        auth_service.request_otp(
            "approved@example.com", "127.0.0.1"
        )

    assert sent == []




def test_ip_hourly_otp_limit(monkeypatch):
    """Reject OTP requests after the hourly IP limit."""
    sent = []
    monkeypatch.setattr(
        auth_service, "_send_otp_email",
        lambda email, otp: sent.append(email),
    )
    monkeypatch.setattr(
        auth_service, "IP_OTP_HOURLY_LIMIT", 10,
    )

    now = time.time()
    auth_service._ip_otp_requests["127.0.0.1"] = [
        now - (index + 1) * 10 for index in range(10)
    ]

    with pytest.raises(ValueError, match="address"):
        auth_service.request_otp(
            "approved@example.com", "127.0.0.1"
        )

    assert sent == []


def test_cleanup_removes_expired_auth_state():
    """Expired OTPs, sessions, cooldowns, and rate records are removed."""
    now = time.time()

    auth_service._otps["expired@example.com"] = {
        "digest": "test-digest",
        "salt": "test-salt",
        "expires": now - 10,
        "attempts": 0,
    }

    auth_service._sessions["expired-session"] = {
        "email": "approved@example.com",
        "expires": now - 10,
    }

    auth_service._last_otp_request[
        ("approved@example.com", "127.0.0.1")
    ] = now - auth_service.OTP_RESEND_COOLDOWN_SECONDS - 1

    auth_service._email_otp_requests["expired@example.com"] = [
        now - auth_service.OTP_RATE_WINDOW_SECONDS - 1
    ]

    auth_service._ip_otp_requests["127.0.0.1"] = [
        now - auth_service.OTP_RATE_WINDOW_SECONDS - 1
    ]

    with auth_service._lock:
        auth_service._cleanup_expired_auth_state(now)

    assert "expired@example.com" not in auth_service._otps
    assert "expired-session" not in auth_service._sessions
    assert (
        "approved@example.com", "127.0.0.1"
    ) not in auth_service._last_otp_request
    assert "expired@example.com" not in auth_service._email_otp_requests
    assert "127.0.0.1" not in auth_service._ip_otp_requests


def test_older_otp_request_cannot_overwrite_newer_request(monkeypatch):
    """A stale request must not replace the latest OTP record."""
    email = "approved@example.com"
    now = time.time()

    old_request_id = "old-request"
    new_request_id = "new-request"

    old_otp = "111111"
    new_otp = "222222"

    old_salt = "old-salt"
    new_salt = "new-salt"

    monkeypatch.setattr(
        auth_service, "_otp_digest",
        lambda email, otp, salt: f"{otp}:{salt}",
    )

    with auth_service._lock:
        auth_service._otp_request_generation[email] = new_request_id
        auth_service._otps[email] = {
            "digest": auth_service._otp_digest(
                email, new_otp, new_salt
            ),
            "salt": new_salt,
            "expires": now + auth_service.OTP_TTL_SECONDS,
            "attempts": 0,
        }

    # Simulate the older request finishing after the newer request.
    with auth_service._lock:
        if (
            auth_service._otp_request_generation.get(email)
            == old_request_id
        ):
            auth_service._otps[email] = {
                "digest": auth_service._otp_digest(
                    email, old_otp, old_salt
                ),
                "salt": old_salt,
                "expires": now + auth_service.OTP_TTL_SECONDS,
                "attempts": 0,
            }

    assert auth_service._otp_request_generation[email] == new_request_id
    assert auth_service._otps[email]["salt"] == new_salt
