
import time

import pytest

from backend.app.services import auth_service
from backend.app.services import auth_db


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
    with auth_db.get_connection() as conn:
        conn.execute(
            "DELETE FROM auth_otps WHERE email = %s",
            ("approved@example.com",),
        )
        conn.execute(
            """
            DELETE FROM auth_rate_limits
            WHERE email = %s OR client_ip = %s
            """,
            ("approved@example.com", "127.0.0.1"),
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

    with auth_db.get_connection() as conn:
        conn.execute(
            """
            UPDATE auth_otps
            SET expires_at = %s
            WHERE email = %s
            """,
            (time.time() - 1, "approved@example.com"),
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
    email = "approved@example.com"
    client_ip = "127.0.0.1"
    now = time.time()

    monkeypatch.setattr(
        auth_service, "_send_otp_email",
        lambda email, otp: sent.append(email),
    )
    monkeypatch.setattr(
        auth_service, "EMAIL_OTP_HOURLY_LIMIT", 5,
    )

    try:
        with auth_db.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO auth_rate_limits
                    (email, client_ip, requested_at)
                VALUES
                    (%s, %s, %s),
                    (%s, %s, %s),
                    (%s, %s, %s),
                    (%s, %s, %s),
                    (%s, %s, %s)
                """,
                (
                    email, client_ip, now - 100,
                    email, client_ip, now - 200,
                    email, client_ip, now - 300,
                    email, client_ip, now - 400,
                    email, client_ip, now - 500,
                ),
            )

        with pytest.raises(ValueError, match="email"):
            auth_service.request_otp(email, client_ip)

        assert sent == []

    finally:
        with auth_db.get_connection() as conn:
            conn.execute(
                """
                DELETE FROM auth_rate_limits
                WHERE email = %s AND client_ip = %s
                """,
                (email, client_ip),
            )





def test_ip_hourly_otp_limit(monkeypatch):
    """Reject OTP requests after the hourly IP limit."""
    sent = []
    email = "approved@example.com"
    client_ip = "127.0.0.1"
    now = time.time()

    monkeypatch.setattr(
        auth_service, "_send_otp_email",
        lambda email, otp: sent.append(email),
    )
    monkeypatch.setattr(
        auth_service, "IP_OTP_HOURLY_LIMIT", 10,
    )
    monkeypatch.setattr(
    auth_service, "EMAIL_OTP_HOURLY_LIMIT", 20,
    )
    try:
        with auth_db.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO auth_rate_limits
                    (email, client_ip, requested_at)
                SELECT %s, %s, %s
                FROM generate_series(1, 10)
                """,
                (email, client_ip, now - 100),
            )

        with pytest.raises(ValueError, match="address"):
            auth_service.request_otp(email, client_ip)

        assert sent == []

    finally:
        with auth_db.get_connection() as conn:
            conn.execute(
                """
                DELETE FROM auth_rate_limits
                WHERE email = %s AND client_ip = %s
                """,
                (email, client_ip),
            )



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
    """A stale request must not replace the latest OTP in PostgreSQL."""
    email = "approved@example.com"

    old_request_id = "old-request"
    new_request_id = "new-request"

    old_otp = "111111"
    new_otp = "222222"

    monkeypatch.setattr(
        auth_service,
        "_otp_digest",
        lambda email, otp, salt: f"{otp}:{salt}",
    )

    # Register the older request first, then the newer request.
    auth_db.register_otp_request(email, old_request_id)
    auth_db.register_otp_request(email, new_request_id)

    # The older request must not overwrite the newer OTP.
    old_saved = auth_db.save_otp_if_latest(
        email=email,
        request_id=old_request_id,
        digest=auth_service._otp_digest(email, old_otp, "old-salt"),
        salt="old-salt",
        expires_at=time.time() + auth_service.OTP_TTL_SECONDS,
    )

    assert old_saved is False

    # The latest request should be allowed to save its OTP.
    new_saved = auth_db.save_otp_if_latest(
        email=email,
        request_id=new_request_id,
        digest=auth_service._otp_digest(email, new_otp, "new-salt"),
        salt="new-salt",
        expires_at=time.time() + auth_service.OTP_TTL_SECONDS,
    )

    assert new_saved is True

    with auth_db.get_connection() as conn:
        row = conn.execute(
            """
            SELECT digest, salt
            FROM auth_otps
            WHERE email = %s
            """,
            (email,),
        ).fetchone()

    assert row == ("222222:new-salt", "new-salt")


def test_expired_database_session_is_rejected(monkeypatch):
    """An expired PostgreSQL session must not authenticate."""
    email = "approved@example.com"
    session_id = "expired-test-session"
    now = int(time.time())

    token = auth_service._serializer().dumps({
        "email": email,
        "sid": session_id,
        "iat": now,
    })

    monkeypatch.setattr(
        auth_db,
        "get_session",
        lambda sid: (email, time.time() - 10),
    )

    result = auth_service.get_session_email(token)

    assert result is None
