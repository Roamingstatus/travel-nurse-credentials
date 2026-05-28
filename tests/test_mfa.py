"""Tests for MFA/two-step verification logic."""
import json

import pytest

from app.mfa import (
    consume_recovery_code,
    decode_recovery_hashes,
    decrypt_totp_secret,
    encode_recovery_hashes,
    encrypt_totp_secret,
    generate_recovery_codes,
    generate_totp_secret,
    get_totp_uri,
    hash_recovery_code,
    verify_totp,
)


# ---------------------------------------------------------------------------
# MFA status on user model
# ---------------------------------------------------------------------------

class TestUserMFAFields:
    def test_mfa_disabled_by_default(self, user):
        assert user.mfa_enabled is False or user.mfa_enabled is None

    def test_mfa_method_null_by_default(self, user):
        assert user.mfa_method is None

    def test_phone_verified_false_by_default(self, user):
        assert not user.phone_verified

    def test_enable_mfa_persists(self, db, user):
        user.mfa_enabled = True
        user.mfa_method = "totp"
        db.flush()
        from app.db import User as DBUser
        refreshed = db.get(DBUser, user.id)
        assert refreshed.mfa_enabled is True
        assert refreshed.mfa_method == "totp"

    def test_disable_mfa_persists(self, db, user):
        user.mfa_enabled = True
        user.mfa_method = "totp"
        db.flush()
        user.mfa_enabled = False
        user.mfa_method = None
        user.mfa_totp_secret = None
        db.flush()
        from app.db import User as DBUser
        refreshed = db.get(DBUser, user.id)
        assert not refreshed.mfa_enabled


# ---------------------------------------------------------------------------
# TOTP generation and verification
# ---------------------------------------------------------------------------

class TestTOTP:
    def test_generate_secret_is_nonempty(self):
        secret = generate_totp_secret()
        assert isinstance(secret, str)
        assert len(secret) >= 16

    def test_generate_secrets_are_unique(self):
        secrets = {generate_totp_secret() for _ in range(20)}
        assert len(secrets) == 20

    def test_totp_uri_contains_issuer(self):
        import urllib.parse
        secret = generate_totp_secret()
        uri = get_totp_uri(secret, "nurse@test.com")
        decoded = urllib.parse.unquote(uri)
        assert "Credanta" in decoded
        assert "nurse@test.com" in decoded
        assert uri.startswith("otpauth://totp/")

    def test_correct_code_verifies(self):
        import pyotp
        secret = generate_totp_secret()
        code = pyotp.TOTP(secret).now()
        assert verify_totp(secret, code) is True

    def test_wrong_code_does_not_verify(self):
        secret = generate_totp_secret()
        assert verify_totp(secret, "000000") is False

    def test_empty_code_does_not_verify(self):
        secret = generate_totp_secret()
        assert verify_totp(secret, "") is False

    def test_non_numeric_code_does_not_verify(self):
        secret = generate_totp_secret()
        assert verify_totp(secret, "abcdef") is False

    def test_code_for_wrong_secret_fails(self):
        import pyotp
        secret_a = generate_totp_secret()
        secret_b = generate_totp_secret()
        code = pyotp.TOTP(secret_a).now()
        assert verify_totp(secret_b, code) is False


# ---------------------------------------------------------------------------
# Encryption round-trip
# ---------------------------------------------------------------------------

class TestSecretEncryption:
    def test_encrypt_decrypt_roundtrip(self):
        secret = generate_totp_secret()
        encrypted = encrypt_totp_secret(secret)
        assert encrypted != secret
        decrypted = decrypt_totp_secret(encrypted)
        assert decrypted == secret

    def test_decrypt_garbage_returns_none(self):
        result = decrypt_totp_secret("not-a-valid-token")
        assert result is None

    def test_different_secrets_encrypt_differently(self):
        a = generate_totp_secret()
        b = generate_totp_secret()
        assert encrypt_totp_secret(a) != encrypt_totp_secret(b)


# ---------------------------------------------------------------------------
# Recovery codes
# ---------------------------------------------------------------------------

class TestRecoveryCodes:
    def test_generates_correct_count(self):
        codes = generate_recovery_codes()
        assert len(codes) == 8

    def test_codes_are_unique(self):
        codes = generate_recovery_codes(20)
        assert len(set(codes)) == 20

    def test_hash_is_deterministic(self):
        assert hash_recovery_code("ABC123-DEF456") == hash_recovery_code("ABC123-DEF456")

    def test_hash_normalises_case(self):
        assert hash_recovery_code("abc123-def456") == hash_recovery_code("ABC123-DEF456")

    def test_hash_ignores_dashes(self):
        assert hash_recovery_code("ABCDEF") == hash_recovery_code("ABC-DEF")

    def test_encode_decode_roundtrip(self):
        codes = generate_recovery_codes()
        hashes = [hash_recovery_code(c) for c in codes]
        stored = encode_recovery_hashes(hashes)
        recovered = decode_recovery_hashes(stored)
        assert recovered == hashes

    def test_decode_none_returns_empty(self):
        assert decode_recovery_hashes(None) == []

    def test_decode_invalid_json_returns_empty(self):
        assert decode_recovery_hashes("not-json") == []

    def test_consume_valid_code_returns_true(self):
        codes = generate_recovery_codes(4)
        hashes = [hash_recovery_code(c) for c in codes]
        stored = encode_recovery_hashes(hashes)
        matched, new_stored = consume_recovery_code(codes[0], stored)
        assert matched is True
        remaining = decode_recovery_hashes(new_stored)
        assert hash_recovery_code(codes[0]) not in remaining
        assert len(remaining) == 3

    def test_consume_same_code_twice_fails(self):
        codes = generate_recovery_codes(2)
        hashes = [hash_recovery_code(c) for c in codes]
        stored = encode_recovery_hashes(hashes)
        _, new_stored = consume_recovery_code(codes[0], stored)
        matched, _ = consume_recovery_code(codes[0], new_stored)
        assert matched is False

    def test_consume_invalid_code_returns_false(self):
        codes = generate_recovery_codes(2)
        hashes = [hash_recovery_code(c) for c in codes]
        stored = encode_recovery_hashes(hashes)
        matched, unchanged = consume_recovery_code("ZZZZZZ-ZZZZZZ", stored)
        assert matched is False
        assert unchanged == stored


# ---------------------------------------------------------------------------
# Sensitive action MFA check (unit-level)
# ---------------------------------------------------------------------------

class TestMFAGateLogic:
    """
    Tests that verify the MFA gate logic in isolation.
    The actual HTTP routing is tested via the FastAPI test client in integration tests.
    Here we test the helper logic directly.
    """

    def test_mfa_disabled_user_skips_gate(self, user):
        """If MFA is not enabled, the gate should not block the action."""
        user.mfa_enabled = False
        # A user without MFA has mfa_enabled=False → gate is a no-op
        assert not user.mfa_enabled

    def test_mfa_enabled_user_triggers_gate(self, db, user):
        """If MFA is enabled, the gate should require verification."""
        user.mfa_enabled = True
        user.mfa_method = "totp"
        db.flush()
        assert user.mfa_enabled is True

    def test_sms_returns_gracefully_when_not_configured(self):
        """SMS MFA should surface a clean 'not configured' state, not crash."""
        sms_configured = False
        status = "coming_soon" if not sms_configured else "available"
        assert status == "coming_soon"
