
import hashlib
import json
import urllib.error
import urllib.request
import hmac
import os
import secrets
import smtplib
import threading
import time
from email.message import EmailMessage
from backend.app.services import auth_db
from dotenv import load_dotenv
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer


# Load local .env values. Hosting environment variables also work.
load_dotenv()

OTP_TTL_SECONDS = 300
OTP_RESEND_COOLDOWN_SECONDS = 60
OTP_MAX_ATTEMPTS = 5
SESSION_TTL_SECONDS = 8 * 60 * 60

OTP_RATE_WINDOW_SECONDS = 60 * 60
EMAIL_OTP_HOURLY_LIMIT = 5
IP_OTP_HOURLY_LIMIT = 10

_lock = threading.RLock()
_otps = {}
_sessions = {}
_last_otp_request = {}

_email_otp_requests = {}
_ip_otp_requests = {}
_otp_request_generation = {}

def _cleanup_expired_auth_state(now: float) -> None:
    """Remove expired authentication and rate-limit records.

    Must be called while holding _lock.
    """

    for email, record in list(_otps.items()):
        if now >= record["expires"]:
            _otps.pop(email, None)

    for session_id, record in list(_sessions.items()):
        if now >= record["expires"]:
            _sessions.pop(session_id, None)

    for key, timestamp in list(_last_otp_request.items()):
        if now - timestamp >= OTP_RESEND_COOLDOWN_SECONDS:
            _last_otp_request.pop(key, None)

    for store in (_email_otp_requests, _ip_otp_requests):
        for key, timestamps in list(store.items()):
            valid = [
                timestamp
                for timestamp in timestamps
                if now - timestamp < OTP_RATE_WINDOW_SECONDS
            ]

            if valid:
                store[key] = valid
            else:
                store.pop(key, None)


def _setting(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _approved_emails() -> set[str]:
    return {
        address.strip().lower()
        for address in _setting("ALLOWED_EMAILS").split(",")
        if address.strip()
    }


def _session_secret() -> str:
    secret = _setting("SESSION_SECRET")
    if len(secret) < 32:
        raise RuntimeError(
            "SESSION_SECRET must contain at least 32 characters."
        )
    return secret


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(
        _session_secret(),
        salt="openprofile-auth-session",
    )


def _otp_digest(email: str, otp: str, salt: str) -> str:
    secret = _session_secret().encode("utf-8")
    message = f"{email}:{salt}:{otp}".encode("utf-8")
    return hmac.new(secret, message, hashlib.sha256).hexdigest()




def _send_otp_email(email: str, otp: str) -> None:
    api_key = _setting("RESEND_API_KEY")

    if not api_key:
        raise RuntimeError("Resend API key is not configured.")

    payload = {
        "from": "OpenProfile <onboarding@resend.dev>",
        "to": [email],
        "subject": "Your OpenProfile verification code",
        "text": f"""Your OpenProfile verification code is: {otp}

This code expires in 5 minutes and can only be used once.
If you did not request this code, you can ignore this email.
""",
    }

    request = urllib.request.Request(
        "https://api.resend.com/emails",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            if not 200 <= response.status < 300:
                raise RuntimeError(
                    "Unable to send the verification email. "
                    "Please try again later."
                )
    except (urllib.error.HTTPError, urllib.error.URLError,
            OSError, TimeoutError):
        raise RuntimeError(
            "Unable to send the verification email. Please try again later."
        ) from None






def request_otp(email: str, client_ip: str = "unknown") -> None:
    """Send an OTP to an approved email address without exposing the allowlist."""
    normalized = email.strip().lower()

    if not normalized or len(normalized) > 254 or "@" not in normalized:
        raise ValueError("Enter a valid email address.")

    if normalized not in _approved_emails():
        return

    now = time.time()
    request_id = secrets.token_urlsafe(16)

    # Enforce persistent cooldown and rate limits.
    auth_db.reserve_otp_request(
        email=normalized,
        client_ip=client_ip,
        now=now,
        cooldown_seconds=OTP_RESEND_COOLDOWN_SECONDS,
        rate_window_seconds=OTP_RATE_WINDOW_SECONDS,
        email_hourly_limit=EMAIL_OTP_HOURLY_LIMIT,
        ip_hourly_limit=IP_OTP_HOURLY_LIMIT,
    )

    # Register this request before sending the email.
    try:
        auth_db.register_otp_request(normalized, request_id)
    except Exception:
        try:
            auth_db.cancel_otp_request(normalized, client_ip, now)
        except Exception:
            pass

        raise RuntimeError(
            "Unable to store the verification request. Please try again later."
        ) from None

    otp = f"{secrets.randbelow(1_000_000):06d}"
    salt = secrets.token_hex(16)

    try:
        _send_otp_email(normalized, otp)
    except Exception:
        try:
            auth_db.cancel_otp_request(normalized, client_ip, now)
        except Exception:
            pass
        raise RuntimeError(
            "Unable to send the verification email. Please try again later."
        ) from None


    try:
        saved = auth_db.save_otp_if_latest(
            email=normalized,
            request_id=request_id,
            digest=_otp_digest(normalized, otp, salt),
            salt=salt,
            expires_at=time.time() + OTP_TTL_SECONDS,
        )
    except Exception:
        raise RuntimeError(
            "Unable to store the verification code. Please try again later."
        ) from None

    if not saved:
        # A newer request superseded this one.
        return





def verify_otp(email: str, otp: str) -> bool:
    """Validate and consume a six-digit OTP stored in PostgreSQL."""
    normalized = email.strip().lower()

    if not otp.isdigit() or len(otp) != 6:
        return False

    return auth_db.verify_otp_record(
        email=normalized,
        otp=otp,
        digest_for_salt=lambda salt: _otp_digest(
            normalized, otp, salt
        ),
        max_attempts=OTP_MAX_ATTEMPTS,
    )



def create_session(email: str) -> str:
    """Create a signed session token and persist it for revocation."""
    normalized = email.strip().lower()

    if normalized not in _approved_emails():
        raise ValueError("Email address is not approved.")

    session_id = secrets.token_urlsafe(24)
    now = int(time.time())
    expires_at = now + SESSION_TTL_SECONDS

    token = _serializer().dumps({
        "email": normalized,
        "sid": session_id,
        "iat": now,
    })

    auth_db.save_session(
        session_id=session_id,
        email=normalized,
        expires_at=expires_at,
    )

    return token


def get_session_email(token: str) -> str | None:
    """Return the authenticated email, or None for an invalid session."""
    try:
        payload = _serializer().loads(
            token,
            max_age=SESSION_TTL_SECONDS,
        )
    except (BadSignature, SignatureExpired, TypeError, ValueError):
        return None

    email = payload.get("email")
    session_id = payload.get("sid")

    if not isinstance(email, str) or not isinstance(session_id, str):
        return None

    try:
        session = auth_db.get_session(session_id)
    except Exception:
        # Fail closed if the session store is unavailable.
        return None

    if session is None:
        return None

    stored_email, expires_at = session

    if time.time() >= expires_at:
        try:
            auth_db.delete_session(session_id)
        except Exception:
            pass
        return None

    if stored_email != email:
        return None

    if email not in _approved_emails():
        return None

    return email


def revoke_session(token: str) -> None:
    """Revoke a session during logout."""
    try:
        payload = _serializer().loads(
            token,
            max_age=SESSION_TTL_SECONDS,
        )
    except (BadSignature, SignatureExpired, TypeError, ValueError):
        return

    session_id = payload.get("sid")

    if isinstance(session_id, str):
        try:
            auth_db.delete_session(session_id)
        except Exception:
            # Logout should still clear the browser cookie.
            pass
