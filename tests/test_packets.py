"""Tests for ZIP packet generation."""
import io
import zipfile
from datetime import datetime

import pytest

from types import SimpleNamespace

from app.packet import _safe, build_zip


def _user(name="Test Nurse", email="nurse@test.com"):
    return SimpleNamespace(id=1, name=name, email=email)


def _doc(
    category="Licenses & Certifications",
    title="RN License",
    original_filename="rn_license.pdf",
    stored_filename=None,
    expires_at=None,
    issued_at=None,
    user_id=1,
):
    return SimpleNamespace(
        category=category,
        title=title,
        original_filename=original_filename,
        stored_filename=stored_filename or "missing_file.pdf",
        expires_at=expires_at,
        issued_at=issued_at,
        user_id=user_id,
    )


class TestSafeFilename:
    def test_alphanumeric_unchanged(self):
        assert _safe("RNLicense") == "RNLicense"

    def test_spaces_preserved(self):
        assert " " in _safe("RN License")

    def test_special_chars_replaced(self):
        result = _safe("file<>:/\\|?*.pdf")
        assert "<" not in result
        assert ">" not in result
        assert ":" not in result

    def test_dashes_preserved(self):
        assert "-" in _safe("rn-license")

    def test_empty_string_returns_file(self):
        assert _safe("") == "file"

    def test_unicode_sanitised(self):
        result = _safe("résumé")
        assert isinstance(result, str)


class TestBuildZip:
    def test_returns_bytes(self, tmp_upload_dir):
        u = _user()
        blob = build_zip(u, [])
        assert isinstance(blob, bytes)
        assert len(blob) > 0

    def test_valid_zip_structure(self, tmp_upload_dir):
        u = _user()
        blob = build_zip(u, [])
        buf = io.BytesIO(blob)
        assert zipfile.is_zipfile(buf)

    def test_manifest_always_present(self, tmp_upload_dir):
        u = _user()
        blob = build_zip(u, [])
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            assert "MANIFEST.txt" in zf.namelist()

    def test_manifest_contains_user_name(self, tmp_upload_dir):
        u = _user(name="Jane Nurse")
        blob = build_zip(u, [])
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            manifest = zf.read("MANIFEST.txt").decode()
        assert "Jane Nurse" in manifest

    def test_manifest_contains_user_email_fallback(self, tmp_upload_dir):
        u = _user(name=None, email="jane@test.com")
        blob = build_zip(u, [])
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            manifest = zf.read("MANIFEST.txt").decode()
        assert "jane@test.com" in manifest

    def test_manifest_lists_document_title(self, tmp_upload_dir):
        u = _user()
        doc = _doc(title="My RN License")
        blob = build_zip(u, [doc])
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            manifest = zf.read("MANIFEST.txt").decode()
        assert "My RN License" in manifest

    def test_manifest_shows_expiry_date(self, tmp_upload_dir):
        u = _user()
        doc = _doc(expires_at=datetime(2027, 6, 15))
        blob = build_zip(u, [doc])
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            manifest = zf.read("MANIFEST.txt").decode()
        assert "2027-06-15" in manifest

    def test_manifest_shows_dash_for_no_expiry(self, tmp_upload_dir):
        u = _user()
        doc = _doc(expires_at=None)
        blob = build_zip(u, [doc])
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            manifest = zf.read("MANIFEST.txt").decode()
        assert "—" in manifest

    def test_manifest_document_count(self, tmp_upload_dir):
        u = _user()
        docs = [_doc(title=f"Doc {i}") for i in range(3)]
        blob = build_zip(u, docs)
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            manifest = zf.read("MANIFEST.txt").decode()
        assert "Documents (3)" in manifest

    def test_missing_file_does_not_crash(self, tmp_upload_dir):
        """Docs whose stored file doesn't exist should be skipped gracefully."""
        u = _user()
        doc = _doc(stored_filename="does_not_exist_anywhere.pdf")
        blob = build_zip(u, [doc])
        assert len(blob) > 0

    def test_real_file_included_in_zip(self, tmp_upload_dir):
        """If the file exists on disk it should appear inside the ZIP."""
        import app.storage as storage
        from app.storage import save_upload

        u = _user()
        content = b"this is my credential file"
        stored_name, _ = save_upload(u.id, content, ".pdf")

        doc = _doc(
            category="Identity",
            title="Passport",
            stored_filename=stored_name,
            original_filename="passport.pdf",
        )
        blob = build_zip(u, [doc])
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            names = zf.namelist()
        assert any("passport" in n.lower() or "Passport" in n for n in names)

    def test_files_organised_by_category(self, tmp_upload_dir):
        """Files should be placed in a folder named after their category."""
        from app.storage import save_upload

        u = _user()
        content = b"license data"
        stored_name, _ = save_upload(u.id, content, ".pdf")

        doc = _doc(
            category="Licenses & Certifications",
            title="RN License",
            stored_filename=stored_name,
        )
        blob = build_zip(u, [doc])
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            names = zf.namelist()
        folder_names = {n.split("/")[0] for n in names if "/" in n}
        assert any("Licenses" in f or "Certifications" in f for f in folder_names)
