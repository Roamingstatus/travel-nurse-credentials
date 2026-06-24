"""Tests for document upload storage and deduplication logic."""
import hashlib
from pathlib import Path

import pytest

from app.storage import delete_upload, file_path, save_upload, user_dir, verify_upload_ownership


class TestUserDir:
    def test_creates_directory(self, tmp_upload_dir):
        p = user_dir(42)
        assert p.exists()
        assert p.is_dir()

    def test_path_contains_user_id(self, tmp_upload_dir):
        p = user_dir(99)
        assert "99" in str(p)

    def test_idempotent(self, tmp_upload_dir):
        p1 = user_dir(1)
        p2 = user_dir(1)
        assert p1 == p2


class TestSaveUpload:
    def test_saves_file_and_returns_name(self, tmp_upload_dir):
        name, size = save_upload(1, b"hello world", ".pdf")
        path = tmp_upload_dir / "1" / name
        assert path.exists()
        assert path.read_bytes() == b"hello world"

    def test_returns_correct_size(self, tmp_upload_dir):
        content = b"test content"
        _, size = save_upload(1, content, ".pdf")
        assert size == len(content)

    def test_suffix_preserved(self, tmp_upload_dir):
        name, _ = save_upload(1, b"data", ".pdf")
        assert name.endswith(".pdf")

    def test_suffix_without_dot(self, tmp_upload_dir):
        name, _ = save_upload(1, b"data", "pdf")
        assert name.endswith(".pdf")

    def test_unique_filenames_each_call(self, tmp_upload_dir):
        name1, _ = save_upload(1, b"data", ".pdf")
        name2, _ = save_upload(1, b"data", ".pdf")
        assert name1 != name2

    def test_suffix_sanitised_length(self, tmp_upload_dir):
        name, _ = save_upload(1, b"data", ".verylongextensionhere")
        suffix = Path(name).suffix
        assert len(suffix) <= 13  # dot + 12 chars max

    def test_empty_suffix(self, tmp_upload_dir):
        name, _ = save_upload(1, b"data", "")
        assert isinstance(name, str) and len(name) > 0


class TestFilePath:
    def test_returns_correct_path(self, tmp_upload_dir):
        name, _ = save_upload(5, b"abc", ".txt")
        p = file_path(5, name)
        assert p.exists()
        assert p.read_bytes() == b"abc"


class TestDeleteFile:
    def test_deletes_existing_file(self, tmp_upload_dir):
        name, _ = save_upload(7, b"delete me", ".txt")
        p = file_path(7, name)
        assert p.exists()
        delete_upload(7, name)
        assert not p.exists()

    def test_no_error_on_missing_file(self, tmp_upload_dir):
        delete_upload(7, "nonexistent_file.pdf")  # should not raise


class TestVerifyUploadOwnership:
    def test_owned_file(self, tmp_upload_dir):
        name, _ = save_upload(3, b"secret", ".pdf")
        assert verify_upload_ownership(3, name) is True

    def test_wrong_user(self, tmp_upload_dir):
        name, _ = save_upload(3, b"secret", ".pdf")
        assert verify_upload_ownership(4, name) is False

    def test_path_traversal_rejected(self, tmp_upload_dir):
        save_upload(3, b"secret", ".pdf")
        assert verify_upload_ownership(3, "../other/evil.pdf") is False


class TestContentHashDeduplication:
    """Unit-test the hash-based duplicate detection logic used in the upload route."""

    def test_same_content_produces_same_hash(self):
        content = b"my credential document"
        h1 = hashlib.sha256(content).hexdigest()
        h2 = hashlib.sha256(content).hexdigest()
        assert h1 == h2

    def test_different_content_produces_different_hash(self):
        h1 = hashlib.sha256(b"document A").hexdigest()
        h2 = hashlib.sha256(b"document B").hexdigest()
        assert h1 != h2

    def test_hash_length_is_64_chars(self):
        h = hashlib.sha256(b"some content").hexdigest()
        assert len(h) == 64

    def test_duplicate_detected_via_db(self, db, make_doc):
        """Simulate the duplicate check: same hash already in DB."""
        from app.db import Document
        content = b"duplicate file content"
        h = hashlib.sha256(content).hexdigest()
        make_doc(content_hash=h)

        existing = db.query(Document).filter_by(content_hash=h).first()
        assert existing is not None

    def test_no_duplicate_for_different_hash(self, db, make_doc):
        from app.db import Document
        make_doc(content_hash="hash-aaa")
        result = db.query(Document).filter_by(content_hash="hash-bbb").first()
        assert result is None

    def test_duplicate_only_within_same_user(self, db):
        """Same file content for different users should not count as duplicate."""
        from app.db import Document, User
        u1 = User(google_sub="sub-u1", email="u1@test.com")
        u2 = User(google_sub="sub-u2", email="u2@test.com")
        db.add_all([u1, u2])
        db.flush()

        h = hashlib.sha256(b"shared content").hexdigest()
        db.add(Document(
            user_id=u1.id, category="Other", title="Doc", content_hash=h,
            original_filename="f.pdf", stored_filename="s.pdf",
            mime_type="application/pdf", size_bytes=10,
        ))
        db.flush()

        dup_for_u2 = db.query(Document).filter_by(user_id=u2.id, content_hash=h).first()
        assert dup_for_u2 is None
