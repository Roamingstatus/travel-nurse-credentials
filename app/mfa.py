"""
Credanta MFA service — TOTP-based two-step verification.

Responsibilities:
  - TOTP secret generation and verification (via pyotp)
  - otpauth:// URI for QR code rendering
  - Fernet-based TOTP secret encryption at rest
  - Recovery code generation and hashing
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import secrets
from typing import Optional

logger = logging.getLogger("credanta.mfa")

ISSUER = "Credanta"
TOTP_VALID_WINDOW = 1  # accept codes from ±1 period (90-second tolerance)
RECOVERY_CODE_COUNT = 8


# ---------------------------------------------------------------------------
# TOTP helpers
# ---------------------------------------------------------------------------

def generate_totp_secret() -> str:
    """Return a fresh base32 TOTP secret suitable for Google Authenticator et al."""
    import pyotp
    return pyotp.random_base32()


def get_totp_uri(secret: str, email: str) -> str:
    """Return the otpauth:// provisioning URI for QR code display."""
    import pyotp
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=email, issuer_name=ISSUER)


def generate_qr_data_url(uri: str) -> str:
    """Return a data: URL containing a PNG QR code for *uri*.

    Uses the qrcode library with Pillow backend so the image is generated
    entirely server-side — no CDN dependency, always visible.
    Returns an empty string if generation fails (template falls back to JS).
    """
    try:
        import io
        import qrcode
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=8,
            border=4,
        )
        qr.add_data(uri)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()
        return f"data:image/png;base64,{b64}"
    except Exception as exc:
        logger.warning("[mfa] QR generation failed: %s", exc)
        return ""


def verify_totp(secret: str, code: str) -> bool:
    """Return True if *code* is valid for *secret* (±1 30-second window)."""
    import pyotp
    try:
        totp = pyotp.TOTP(secret)
        return totp.verify(code.strip(), valid_window=TOTP_VALID_WINDOW)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Encryption of the stored secret
# ---------------------------------------------------------------------------

def _derive_fernet_key() -> bytes:
    """Derive a 32-byte Fernet key from SESSION_SECRET."""
    raw = os.environ.get("SESSION_SECRET", "dev-placeholder-not-for-production")
    return base64.urlsafe_b64encode(hashlib.sha256(raw.encode()).digest())


def encrypt_totp_secret(plaintext: str) -> str:
    """Encrypt a TOTP secret for database storage. Returns a str token."""
    try:
        from cryptography.fernet import Fernet
        f = Fernet(_derive_fernet_key())
        return f.encrypt(plaintext.encode()).decode()
    except Exception as exc:
        logger.warning("[mfa] Fernet unavailable, storing secret as-is: %s", exc)
        return plaintext


def decrypt_totp_secret(ciphertext: str) -> Optional[str]:
    """Decrypt a stored TOTP secret. Returns None if decryption fails."""
    try:
        from cryptography.fernet import Fernet, InvalidToken
        f = Fernet(_derive_fernet_key())
        return f.decrypt(ciphertext.encode()).decode()
    except Exception:
        logger.warning("[mfa] Failed to decrypt TOTP secret — user may need to re-enroll.")
        return None


# ---------------------------------------------------------------------------
# Recovery codes
# ---------------------------------------------------------------------------

def generate_recovery_codes(n: int = RECOVERY_CODE_COUNT) -> list[str]:
    """Generate *n* one-time recovery codes (plain text, to be shown once)."""
    return ["-".join([secrets.token_hex(3).upper() for _ in range(2)]) for _ in range(n)]


def hash_recovery_code(code: str) -> str:
    """Return the SHA-256 hex digest of a normalised recovery code for storage."""
    normalised = code.replace("-", "").upper().strip()
    return hashlib.sha256(normalised.encode()).hexdigest()


def encode_recovery_hashes(codes: list[str]) -> str:
    """Serialise a list of recovery code hashes to a JSON string for DB storage."""
    return json.dumps(codes)


def decode_recovery_hashes(stored: Optional[str]) -> list[str]:
    """Deserialise stored recovery code hashes. Returns [] on any error."""
    if not stored:
        return []
    try:
        val = json.loads(stored)
        return val if isinstance(val, list) else []
    except Exception:
        return []


def consume_recovery_code(code: str, stored_json: Optional[str]) -> tuple[bool, str]:
    """Check and consume a recovery code.

    Returns (matched, new_stored_json).  If matched, the code is removed from
    the stored list so it cannot be reused.
    """
    hashes = decode_recovery_hashes(stored_json)
    h = hash_recovery_code(code)
    if h in hashes:
        remaining = [x for x in hashes if x != h]
        return True, encode_recovery_hashes(remaining)
    return False, stored_json or "[]"
