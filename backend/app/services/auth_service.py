
import hashlib
import hmac
import os
import secrets
import smtplib
import threading
import time
from email.message import EmailMessage

from dotenv import load_dotenv
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer


# Load local .env values. Hosting environment variables also work.
load_dotenv()

OTP_TTL_SECONDS = 300
OTP_RESEND_COOLDOWN_SECONDS = 60
OTP_MAX_ATTEMPTS = 5
SESSION_TTL_SECONDS = 8 * 60 * 60

_lock = threading.RLock()
_otps = {}
_sessions = {}
_last_otp_request = {}


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
    host = _setting("SMTP_HOST", "smtp.gmail.com")
    port = int(_setting("SMTP_PORT", "465"))
    username = _setting("SMTP_USERNAME")
    password = _setting("SMTP_APP_PASSWORD")

    if not username or not password:
        raise RuntimeError("SMTP credentials are not configured.")

    message = EmailMessage()
    message["Subject"] = "Your OpenProfile verification code"
    message["From"] = username
    message["To"] = email
    message.set_content(
        f"""Your OpenProfile verification code is: {otp}

This code expires in 5 minutes and can only be used once.
If you did not request this code, you can ignore this email.
"""
    )

    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=20) as server:
                server.login(username, password)
                server.send_message(message)
        else:
            with smtplib.SMTP(host, port, timeout=20) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(username, password)
                server.send_message(message)
    except (smtplib.SMTPException, OSError, TimeoutError):
        raise RuntimeError(
            "Unable to send the verification email. Please try again later."
        ) from None



def request_otp(email: str, client_ip: str = "unknown") -> None:
    """Send an OTP to an approved email address.

    Returns the same result for approved and unapproved addresses
    to avoid exposing the allowlist through the API.
    """
    normalized = email.strip().lower()

    if not normalized or len(normalized) > 254 or "@" not in normalized:
        raise ValueError("Enter a valid email address.")

    if normalized not in _approved_emails():
        return

    now = time.time()
    request_key = (normalized, client_ip)

    with _lock:
        previous = _last_otp_request.get(request_key, 0)
        if now - previous < OTP_RESEND_COOLDOWN_SECONDS:
            raise ValueError(
                "Please wait before requesting another verification code."
            )

        # Reserve the cooldown before sending to limit concurrent requests.
        _last_otp_request[request_key] = now

    otp = f"{secrets.randbelow(1_000_000):06d}"
    salt = secrets.token_hex(16)

    try:
        _send_otp_email(normalized, otp)
    except Exception:
        with _lock:
            _last_otp_request.pop(request_key, None)
        raise RuntimeError(
            "Unable to send the verification email. Please try again later."
        ) from None

    with _lock:
        _otps[normalized] = {
            "digest": _otp_digest(normalized, otp, salt),
            "salt": salt,
            "expires": now + OTP_TTL_SECONDS,
            "attempts": 0,
        }


def verify_otp(email: str, otp: str) -> bool:
    """Validate a six-digit OTP once, with expiry and attempt limits."""
    normalized = email.strip().lower()

    if not otp.isdigit() or len(otp) != 6:
        return False

    with _lock:
        record = _otps.get(normalized)

        if not record:
            return False

        if time.time() >= record["expires"]:
            _otps.pop(normalized, None)
            return False

        record["attempts"] += 1

        expected = record["digest"]
        actual = _otp_digest(normalized, otp, record["salt"])

        if not hmac.compare_digest(expected, actual):
            if record["attempts"] >= OTP_MAX_ATTEMPTS:
                _otps.pop(normalized, None)
            return False

        # A successful code is single-use.
        _otps.pop(normalized, None)
        return True


def create_session(email: str) -> str:
    """Create a signed session token and register it for revocation."""
    normalized = email.strip().lower()

    if normalized not in _approved_emails():
        raise ValueError("Email address is not approved.")

    session_id = secrets.token_urlsafe(24)
    now = int(time.time())

    token = _serializer().dumps({
        "email": normalized,
        "sid": session_id,
        "iat": now,
    })

    with _lock:
        _sessions[session_id] = {
            "email": normalized,
            "expires": now + SESSION_TTL_SECONDS,
        }

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

    with _lock:
        session = _sessions.get(session_id)

        if not session or time.time() >= session["expires"]:
            _sessions.pop(session_id, None)
            return None

        if session["email"] != email:
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
        with _lock:
            _sessions.pop(session_id, None)
