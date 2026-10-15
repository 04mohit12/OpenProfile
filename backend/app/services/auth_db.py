
import os
import time
import hmac
from collections.abc import Callable, Iterator
from contextlib import contextmanager

import psycopg
from dotenv import load_dotenv

load_dotenv()


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS auth_otps (
    email TEXT PRIMARY KEY,
    digest TEXT NOT NULL,
    salt TEXT NOT NULL,
    expires_at DOUBLE PRECISION NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS auth_sessions (
    session_id TEXT PRIMARY KEY,
    email TEXT NOT NULL,
    expires_at DOUBLE PRECISION NOT NULL
);

CREATE TABLE IF NOT EXISTS auth_rate_limits (
    id BIGSERIAL PRIMARY KEY,
    email TEXT NOT NULL,
    client_ip TEXT NOT NULL,
    requested_at DOUBLE PRECISION NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_auth_rate_email_time
    ON auth_rate_limits (email, requested_at);

CREATE INDEX IF NOT EXISTS idx_auth_rate_ip_time
    ON auth_rate_limits (client_ip, requested_at);

CREATE TABLE IF NOT EXISTS auth_otp_requests (
    email TEXT PRIMARY KEY,
    request_id TEXT NOT NULL
);
"""


def get_database_url() -> str:
    """Return the configured database URL without exposing its value."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured.")
    return database_url


@contextmanager
def get_connection() -> Iterator[psycopg.Connection]:
    """Open a PostgreSQL connection and close it reliably."""
    with psycopg.connect(get_database_url(), connect_timeout=10) as conn:
        yield conn


def initialize_auth_tables() -> None:
    """Create the authentication tables and indexes if needed."""
    with get_connection() as conn:
        conn.execute(SCHEMA_SQL)



def register_otp_request(email: str, request_id: str) -> None:
    """Register the latest OTP request for an email atomically."""
    with get_connection() as conn:
        with conn.transaction():
            conn.execute(
                """
                SELECT pg_advisory_xact_lock(
                    hashtextextended(%s, 0)
                )
                """,
                (f"otp-request:{email}",),
            )

            conn.execute(
                """
                INSERT INTO auth_otp_requests (email, request_id)
                VALUES (%s, %s)
                ON CONFLICT (email) DO UPDATE SET
                    request_id = EXCLUDED.request_id
                """,
                (email, request_id),
            )



def is_latest_otp_request(email: str, request_id: str) -> bool:
    """Check whether a request is still the latest for an email."""
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT 1
            FROM auth_otp_requests
            WHERE email = %s AND request_id = %s
            """,
            (email, request_id),
        ).fetchone()

    return row is not None




def save_otp_if_latest(
    email: str,
    request_id: str,
    digest: str,
    salt: str,
    expires_at: float,
) -> bool:
    """Save the OTP only if this request is still the latest."""
    with get_connection() as conn:
        with conn.transaction():
            conn.execute(
                """
                SELECT pg_advisory_xact_lock(
                    hashtextextended(%s, 0)
                )
                """,
                (f"otp-request:{email}",),
            )

            row = conn.execute(
                """
                SELECT request_id
                FROM auth_otp_requests
                WHERE email = %s
                FOR UPDATE
                """,
                (email,),
            ).fetchone()

            if row is None or row[0] != request_id:
                return False

            conn.execute(
                """
                INSERT INTO auth_otps
                    (email, digest, salt, expires_at, attempts)
                VALUES (%s, %s, %s, %s, 0)
                ON CONFLICT (email) DO UPDATE SET
                    digest = EXCLUDED.digest,
                    salt = EXCLUDED.salt,
                    expires_at = EXCLUDED.expires_at,
                    attempts = 0
                """,
                (email, digest, salt, expires_at),
            )

            return True



def save_otp(
    email: str,
    digest: str,
    salt: str,
    expires_at: float,
) -> None:
    """Insert or replace the OTP record for an email."""
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO auth_otps
                (email, digest, salt, expires_at, attempts)
            VALUES (%s, %s, %s, %s, 0)
            ON CONFLICT (email) DO UPDATE SET
                digest = EXCLUDED.digest,
                salt = EXCLUDED.salt,
                expires_at = EXCLUDED.expires_at,
                attempts = 0
            """,
            (email, digest, salt, expires_at),
        )



def verify_otp_record(
    email: str,
    otp: str,
    digest_for_salt: Callable[[str], str],
    max_attempts: int,
) -> bool:
    """Verify and consume an OTP atomically."""
    with get_connection() as conn:
        with conn.transaction():
            row = conn.execute(
                """
                SELECT digest, salt, expires_at, attempts
                FROM auth_otps
                WHERE email = %s
                FOR UPDATE
                """,
                (email,),
            ).fetchone()

            if row is None:
                return False

            stored_digest, salt, expires_at, attempts = row

            if time.time() >= expires_at or attempts >= max_attempts:
                conn.execute(
                    "DELETE FROM auth_otps WHERE email = %s",
                    (email,),
                )
                return False

            actual_digest = digest_for_salt(salt)

            if not hmac.compare_digest(stored_digest, actual_digest):
                attempts += 1

                if attempts >= max_attempts:
                    conn.execute(
                        "DELETE FROM auth_otps WHERE email = %s",
                        (email,),
                    )
                else:
                    conn.execute(
                        """
                        UPDATE auth_otps
                        SET attempts = %s
                        WHERE email = %s
                        """,
                        (attempts, email),
                    )
                return False

            conn.execute(
                "DELETE FROM auth_otps WHERE email = %s",
                (email,),
            )
            return True


def save_session(
    session_id: str,
    email: str,
    expires_at: float,
) -> None:
    """Persist an authenticated session."""
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO auth_sessions (session_id, email, expires_at)
            VALUES (%s, %s, %s)
            ON CONFLICT (session_id) DO UPDATE SET
                email = EXCLUDED.email,
                expires_at = EXCLUDED.expires_at
            """,
            (session_id, email, expires_at),
        )


def get_session(session_id: str) -> tuple[str, float] | None:
    """Retrieve a session's email and expiry."""
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT email, expires_at
            FROM auth_sessions
            WHERE session_id = %s
            """,
            (session_id,),
        ).fetchone()

    if row is None:
        return None

    return row[0], row[1]


def delete_session(session_id: str) -> None:
    """Revoke a session."""
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM auth_sessions WHERE session_id = %s",
            (session_id,),
        )


def reserve_otp_request(
    email: str,
    client_ip: str,
    now: float,
    cooldown_seconds: int,
    rate_window_seconds: int,
    email_hourly_limit: int,
    ip_hourly_limit: int,
) -> None:
    """Atomically enforce OTP cooldown and email/IP hourly limits."""
    with get_connection() as conn:
        with conn.transaction():
            # Serialize requests for this email and IP across workers.
            conn.execute(
                """
                SELECT pg_advisory_xact_lock(
                    hashtextextended(%s, 0)
                )
                """,
                (f"email:{email}",),
            )
            conn.execute(
                """
                SELECT pg_advisory_xact_lock(
                    hashtextextended(%s, 0)
                )
                """,
                (f"ip:{client_ip}",),
            )

            cutoff = now - rate_window_seconds

            last = conn.execute(
                """
                SELECT MAX(requested_at)
                FROM auth_rate_limits
                WHERE email = %s AND client_ip = %s
                """,
                (email, client_ip),
            ).fetchone()[0]

            if last is not None and now - last < cooldown_seconds:
                raise ValueError(
                    "Please wait before requesting another verification code."
                )

            email_count = conn.execute(
                """
                SELECT COUNT(*)
                FROM auth_rate_limits
                WHERE email = %s AND requested_at > %s
                """,
                (email, cutoff),
            ).fetchone()[0]

            if email_count >= email_hourly_limit:
                raise ValueError(
                    "Too many verification requests for this email. Try again later."
                )

            ip_count = conn.execute(
                """
                SELECT COUNT(*)
                FROM auth_rate_limits
                WHERE client_ip = %s AND requested_at > %s
                """,
                (client_ip, cutoff),
            ).fetchone()[0]

            if ip_count >= ip_hourly_limit:
                raise ValueError(
                    "Too many verification requests from this address. Try again later."
                )

            conn.execute(
                """
                INSERT INTO auth_rate_limits
                    (email, client_ip, requested_at)
                VALUES (%s, %s, %s)
                """,
                (email, client_ip, now),
            )

            # Remove expired rate-limit history.
            conn.execute(
                "DELETE FROM auth_rate_limits WHERE requested_at <= %s",
                (cutoff,),
            )

def cancel_otp_request(
    email: str,
    client_ip: str,
    requested_at: float,
) -> None:
    """Remove a rate-limit reservation when OTP delivery fails."""
    with get_connection() as conn:
        conn.execute(
            """
            DELETE FROM auth_rate_limits
            WHERE email = %s
              AND client_ip = %s
              AND requested_at = %s
            """,
            (email, client_ip, requested_at),
        )
