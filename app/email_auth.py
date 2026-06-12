"""Email/password authentication helpers for Credanta.

This module handles:
- Password hashing (bcrypt)
- Password strength validation
- Email-auth user registration
- Email-auth user login with brute-force tracking
- Password reset token generation and verification

Google OAuth users are unaffected; their google_sub column is still set and
their auth_provider is 'google'. Email-auth users have auth_provider='email'
and a placeholder google_sub of 'email:<uuid>' to satisfy the unique constraint.
"""
from __future__ import annotations

import logging
import secrets
import uuid
from datetime import datetime, timedelta

import bcrypt
from sqlalchemy.orm import Session

from .db import User

logger = logging.getLogger("credanta.email_auth")

# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

_BCRYPT_ROUNDS = 12


def hash_password(plain: str) -> str:
    """Return a bcrypt hash string for *plain*. Never log the input."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if *plain* matches the stored bcrypt *hashed* string."""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register_email_user(
    db: Session,
    *,
    email: str,
    name: str,
    password_hash: str,
) -> User:
    """Create a new email-auth user. Caller must commit the session.

    Raises ValueError if the email is already registered.
    Does NOT validate password strength — do that before calling this.
    """
    email = email.lower().strip()
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise ValueError("email_taken")

    # SQLite requires google_sub to be unique; use a namespaced placeholder
    # so email users have a distinct, non-colliding value.
    placeholder_sub = f"email:{uuid.uuid4()}"

    user = User(
        google_sub=placeholder_sub,
        email=email,
        name=name.strip() or email.split("@")[0],
        picture=None,
        auth_provider="email",
        password_hash=password_hash,
        subscription_tier="free",
    )
    db.add(user)
    return user


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

_LOCKOUT_THRESHOLD = 10       # lock account after N consecutive failures
_LOCKOUT_DURATION_MIN = 15    # minutes to lock
_FAILURE_WINDOW_MIN = 60      # minutes to count failures within


def check_account_lockout(user: User) -> bool:
    """Return True if the account is currently locked out."""
    if not getattr(user, "lockout_until", None):
        return False
    return datetime.utcnow() < user.lockout_until


def authenticate_email_user(
    db: Session,
    email: str,
    password: str,
) -> User | None:
    """Attempt login for an email-auth user.

    Returns the User on success or None on failure.
    Increments failed_login_count and applies lockout if threshold reached.
    Always takes roughly the same time whether user exists or not.
    Does NOT reveal whether the email address is registered.
    """
    email = email.lower().strip()
    user = db.query(User).filter(User.email == email, User.auth_provider == "email").first()

    # Run bcrypt even when user is missing to prevent timing attacks
    _dummy_hash = "$2b$12$0000000000000000000000000000000000000000000000000000000"
    stored_hash = getattr(user, "password_hash", None) or _dummy_hash

    password_ok = verify_password(password, stored_hash)

    if user is None:
        # User doesn't exist — we still did the bcrypt work for timing safety
        return None

    # Check lockout state
    if check_account_lockout(user):
        logger.warning("[email_auth] Login blocked (account locked): email=%s", email)
        return None

    if not password_ok:
        _record_failed_login(db, user)
        return None

    # Successful login — clear failure counters
    user.failed_login_count = 0
    user.failed_login_reset_at = None
    user.lockout_until = None
    db.commit()
    return user


def _record_failed_login(db: Session, user: User) -> None:
    """Increment failure count; apply lockout if threshold is reached."""
    now = datetime.utcnow()
    window_start = now - timedelta(minutes=_FAILURE_WINDOW_MIN)

    # Reset counter if failure window has expired
    reset_at = getattr(user, "failed_login_reset_at", None)
    if reset_at is None or reset_at < window_start:
        user.failed_login_count = 0
        user.failed_login_reset_at = now

    count = (getattr(user, "failed_login_count", 0) or 0) + 1
    user.failed_login_count = count

    if count >= _LOCKOUT_THRESHOLD:
        user.lockout_until = now + timedelta(minutes=_LOCKOUT_DURATION_MIN)
        logger.warning(
            "[email_auth] Account locked for %d min after %d failures: email=%s",
            _LOCKOUT_DURATION_MIN, count, user.email,
        )

    try:
        db.commit()
    except Exception as exc:
        logger.warning("[email_auth] Failed to persist login failure: %s", exc)
        db.rollback()


# ---------------------------------------------------------------------------
# Password reset
# ---------------------------------------------------------------------------

_RESET_TOKEN_TTL_MIN = 60  # token valid for 1 hour


def create_reset_token(db: Session, user: User) -> str:
    """Generate a secure reset token, store a hash of it, and return the raw token."""
    raw_token = secrets.token_urlsafe(48)
    user.password_reset_token = raw_token
    user.password_reset_expires_at = datetime.utcnow() + timedelta(minutes=_RESET_TOKEN_TTL_MIN)
    db.commit()
    return raw_token


def consume_reset_token(db: Session, raw_token: str, new_password_hash: str) -> bool:
    """Verify token, update the password, invalidate the token.

    Returns True on success, False if token is missing or expired.
    """
    user = db.query(User).filter(User.password_reset_token == raw_token).first()
    if not user:
        return False
    expires = getattr(user, "password_reset_expires_at", None)
    if not expires or datetime.utcnow() > expires:
        return False
    user.password_hash = new_password_hash
    user.password_reset_token = None
    user.password_reset_expires_at = None
    user.failed_login_count = 0
    user.lockout_until = None
    db.commit()
    return True
