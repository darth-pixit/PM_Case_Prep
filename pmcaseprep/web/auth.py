"""Shared passwordless auth for every experiment on this deploy.

One login system, two doors, zero passwords:
  * "Continue with Google" — Google Identity Services returns a signed ID token
    (a JWT); we verify it server-side against Google's public keys. Nothing to
    remember, nothing to reset.
  * "Email me a code" — a 6-digit one-time code sent via Resend. The code IS
    the login, so there is no password and therefore no forgot-password flow.

Both doors end the same way: the verified email is linked to the visitor's
cookie uid in the existing `users` table (SkillGraph), and anonymous work done
before login is merged in. Every experiment (/arena, /recruiter, /referrals)
shares this — one account follows the person across all of them.

Verification is deliberately dependency-light: Google tokens check via
`google-auth` when installed, and codes hash with sha256 into a small SQLite
table in the same DB file as everything else.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
import time
from pathlib import Path

import httpx

GOOGLE_CLIENT_ID = os.environ.get("PMCP_GOOGLE_CLIENT_ID", "")
RESEND_API_KEY = os.environ.get("PMCP_RESEND_KEY", "")
# Without a verified domain Resend only delivers from its onboarding sender —
# fine for an experiment; swap in "PM Case Prep <login@yourdomain.com>" later.
EMAIL_FROM = os.environ.get("PMCP_EMAIL_FROM", "PM Case Prep <onboarding@resend.dev>")
RESEND_URL = "https://api.resend.com/emails"

CODE_TTL_S = 10 * 60  # a code is good for 10 minutes
CODE_MAX_ATTEMPTS = 5  # then the code is burned — request a new one

_SCHEMA = """
CREATE TABLE IF NOT EXISTS auth_codes (
    email      TEXT PRIMARY KEY,
    code_hash  TEXT NOT NULL,
    expires_at REAL NOT NULL,
    attempts   INTEGER NOT NULL DEFAULT 0
);
"""


def google_enabled() -> bool:
    return bool(GOOGLE_CLIENT_ID)


def email_enabled() -> bool:
    return bool(RESEND_API_KEY)


def valid_email(email: str) -> bool:
    return "@" in email and "." in email.rsplit("@", 1)[-1] and len(email) <= 254


def verify_google_token(credential: str) -> str | None:
    """Verify a Google ID token and return the verified email, or None.

    The token is a JWT signed by Google; `google-auth` fetches Google's current
    public keys and checks signature, audience (our client id), expiry and
    issuer. We additionally require `email_verified` — an unverified email on
    a Google account must not claim progress belonging to the real owner.
    """
    if not GOOGLE_CLIENT_ID or not credential:
        return None
    try:
        from google.auth.transport import requests as google_requests
        from google.oauth2 import id_token as google_id_token

        info = google_id_token.verify_oauth2_token(
            credential, google_requests.Request(), GOOGLE_CLIENT_ID
        )
        if not info.get("email_verified"):
            return None
        email = str(info.get("email") or "").strip().lower()
        return email if valid_email(email) else None
    except Exception:  # noqa: BLE001 - any invalid/expired/foreign token -> no login
        return None


class AuthCodes:
    """One-time email codes. Stored hashed (a DB leak must not leak live codes),
    single active code per email, TTL + attempt caps."""

    def __init__(self, db_path: str | Path):
        self.conn = sqlite3.connect(str(db_path))
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    @staticmethod
    def _hash(code: str) -> str:
        return hashlib.sha256(code.encode()).hexdigest()

    def issue(self, email: str) -> str:
        """Create (and store) a fresh 6-digit code for this email."""
        code = f"{secrets.randbelow(1_000_000):06d}"
        self.conn.execute(
            "INSERT INTO auth_codes (email, code_hash, expires_at, attempts) "
            "VALUES (?, ?, ?, 0) "
            "ON CONFLICT(email) DO UPDATE SET code_hash = excluded.code_hash, "
            "expires_at = excluded.expires_at, attempts = 0",
            (email, self._hash(code), time.time() + CODE_TTL_S),
        )
        self.conn.commit()
        return code

    def verify(self, email: str, code: str) -> bool:
        """Check a code. Burns the row on success, expiry, or too many tries."""
        row = self.conn.execute(
            "SELECT code_hash, expires_at, attempts FROM auth_codes WHERE email = ?",
            (email,),
        ).fetchone()
        if row is None:
            return False
        code_hash, expires_at, attempts = row
        if time.time() > expires_at or attempts >= CODE_MAX_ATTEMPTS:
            self._burn(email)
            return False
        if not hmac.compare_digest(code_hash, self._hash(code.strip())):
            self.conn.execute(
                "UPDATE auth_codes SET attempts = attempts + 1 WHERE email = ?", (email,)
            )
            self.conn.commit()
            return False
        self._burn(email)  # single-use
        return True

    def _burn(self, email: str) -> None:
        self.conn.execute("DELETE FROM auth_codes WHERE email = ?", (email,))
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()


def send_code_email(email: str, code: str) -> bool:
    """Deliver the code via Resend. Returns False (never raises) on failure so
    the endpoint can tell the user to retry instead of 500ing."""
    if not RESEND_API_KEY:
        return False
    try:
        resp = httpx.post(
            RESEND_URL,
            headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
            json={
                "from": EMAIL_FROM,
                "to": [email],
                "subject": f"{code} is your PM Case Prep code",
                "text": (
                    f"Your sign-in code is {code}\n\n"
                    "It expires in 10 minutes. If you didn't request this, ignore it."
                ),
            },
            timeout=10,
        )
        return resp.status_code in (200, 201)
    except Exception:  # noqa: BLE001 - network problems must not 500 the login
        return False
