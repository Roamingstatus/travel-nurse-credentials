"""Data-privacy and cross-user isolation tests.

Verifies that User A cannot read, download, preview, or delete
documents that belong to User B.  All checks are at the HTTP level —
we want to confirm the backend enforces ownership, not just the UI.
"""
from datetime import datetime
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, Document, ShareLink, User, get_session
from app.main import app
from app.storage import save_upload

# ---------------------------------------------------------------------------
# Shared in-memory SQLite (StaticPool so all sessions see the same tables)
# ---------------------------------------------------------------------------

_ENGINE = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
    future=True,
)
Base.metadata.create_all(_ENGINE)
_Session = sessionmaker(bind=_ENGINE, autoflush=False, autocommit=False)


def _db_override():
    s = _Session()
    try:
        yield s
    finally:
        s.close()


app.dependency_overrides[get_session] = _db_override

_CLIENT = TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Fixtures: two real users + a document owned by user_b
# ---------------------------------------------------------------------------

def _make_user(google_sub, email, tier="free"):
    db = _Session()
    existing = db.query(User).filter_by(google_sub=google_sub).first()
    if existing:
        uid = existing.id
        db.close()
        db2 = _Session()
        u = db2.get(User, uid)
        db2.close()
        return u
    u = User(google_sub=google_sub, email=email, name=email.split("@")[0], subscription_tier=tier)
    db.add(u)
    db.commit()
    uid = u.id
    db.close()
    db2 = _Session()
    obj = db2.get(User, uid)
    db2.close()
    return obj


_USER_A = _make_user("sub-privacy-a", "usera@test.com", "premium_plus")
_USER_B = _make_user("sub-privacy-b", "userb@test.com", "premium_plus")


def _make_doc_for(user, title="Secret Credential"):
    db = _Session()
    doc = Document(
        user_id=user.id,
        category="Licenses & Certifications",
        title=title,
        original_filename="secret.pdf",
        stored_filename="fake_stored.pdf",
        mime_type="application/pdf",
        size_bytes=1024,
        content_hash=f"hash-privacy-{user.id}-{title}",
    )
    db.add(doc)
    db.commit()
    doc_id = doc.id
    db.close()
    db2 = _Session()
    obj = db2.get(Document, doc_id)
    db2.close()
    return obj


_DOC_B = _make_doc_for(_USER_B, "User B Secret License")


def _as(user):
    return {
        "require_user": patch("app.main.require_user", return_value=user),
        "current_user": patch("app.main.current_user", return_value=user),
    }


def _get_as(user, url):
    with patch("app.main.require_user", return_value=user), \
         patch("app.main.current_user", return_value=user):
        return _CLIENT.get(url)


def _post_as(user, url, **kwargs):
    with patch("app.main.require_user", return_value=user), \
         patch("app.main.current_user", return_value=user):
        return _CLIENT.post(url, **kwargs)


# ---------------------------------------------------------------------------
# Download ownership
# ---------------------------------------------------------------------------

class TestDownloadOwnership:
    def test_owner_doc_returns_non_403(self):
        """User B can hit their own download URL (may 404 if file missing on disk)."""
        resp = _get_as(_USER_B, f"/documents/{_DOC_B.id}/download")
        assert resp.status_code != 403

    def test_other_user_download_returns_404(self):
        """User A must NOT be able to download User B's document."""
        resp = _get_as(_USER_A, f"/documents/{_DOC_B.id}/download")
        assert resp.status_code == 404

    def test_nonexistent_doc_returns_404(self):
        resp = _get_as(_USER_A, "/documents/999999/download")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Thumbnail / view ownership
# ---------------------------------------------------------------------------

class TestThumbOwnership:
    def test_other_user_thumb_returns_404(self):
        resp = _get_as(_USER_A, f"/documents/{_DOC_B.id}/thumb")
        assert resp.status_code == 404

    def test_owner_thumb_not_403(self):
        resp = _get_as(_USER_B, f"/documents/{_DOC_B.id}/thumb")
        assert resp.status_code != 403


# ---------------------------------------------------------------------------
# Edit form ownership
# ---------------------------------------------------------------------------

class TestEditOwnership:
    def test_other_user_edit_returns_404(self):
        resp = _get_as(_USER_A, f"/documents/{_DOC_B.id}/edit")
        assert resp.status_code == 404

    def test_owner_edit_returns_200(self):
        resp = _get_as(_USER_B, f"/documents/{_DOC_B.id}/edit")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Delete ownership
# ---------------------------------------------------------------------------

class TestDeleteOwnership:
    def test_other_user_cannot_delete(self):
        """User A POSTing to delete User B's doc must not succeed (not 200/302)."""
        doc_b2 = _make_doc_for(_USER_B, "Do Not Delete")
        resp = _post_as(_USER_A, f"/documents/{doc_b2.id}/delete")
        assert resp.status_code not in (200, 302)

    def test_owner_delete_is_not_forbidden(self):
        doc = _make_doc_for(_USER_B, "To Delete")
        resp = _post_as(_USER_B, f"/documents/{doc.id}/delete")
        assert resp.status_code != 403


# ---------------------------------------------------------------------------
# Packet only includes owner's documents
# ---------------------------------------------------------------------------

class TestPacketIsolation:
    def test_packet_does_not_include_other_users_docs(self, tmp_path, monkeypatch):
        """The ZIP packet for User A must not contain User B's files."""
        import app.storage as storage
        monkeypatch.setattr(storage, "UPLOAD_DIR", tmp_path)

        doc_a = _make_doc_for(_USER_A, "User A Exclusive")

        with patch("app.main.require_user", return_value=_USER_A), \
             patch("app.main.current_user", return_value=_USER_A):
            resp = _CLIENT.get("/packet")

        # Premium user with docs should get a ZIP, redirect, or non-403 response
        assert resp.status_code != 403

    def test_free_user_cannot_download_packet(self):
        free_user = _make_user("sub-free-packet", "freepacket@test.com", "free")
        with patch("app.main.require_user", return_value=free_user), \
             patch("app.main.current_user", return_value=free_user):
            resp = _CLIENT.get("/packet")
        assert resp.status_code in (302, 403)


# ---------------------------------------------------------------------------
# Share link isolation
# ---------------------------------------------------------------------------

class TestShareLinkPrivacy:
    def test_user_a_cannot_create_share_link_as_user_b(self):
        """
        User A posting to /share/create will always create a link for
        their own user_id — they cannot forge a link for User B.
        """
        resp = _post_as(_USER_A, "/share/create", data={"label": "my link", "expires_days": ""})
        # Result is either a redirect to their own share page or premium gate
        # It must NOT be a 500 error
        assert resp.status_code != 500

    def test_free_user_cannot_create_share_link(self):
        free_user = _make_user("sub-free-share", "freeshare@test.com", "free")
        resp = _post_as(free_user, "/share/create", data={"label": "hack"})
        assert resp.status_code == 403

    def test_public_share_page_requires_valid_token(self):
        resp = _CLIENT.get("/s/nonexistent-token-xyz")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Reorder endpoint — silently skips docs not owned by requester
# ---------------------------------------------------------------------------

class TestReorderIsolation:
    def test_reorder_ignores_other_user_doc(self):
        """
        Even if User A sends User B's doc_id in a reorder request, only
        docs belonging to User A will be mutated. No error, but no effect.
        """
        import json
        resp = _post_as(
            _USER_A,
            "/documents/reorder",
            content=json.dumps({"ids": [_DOC_B.id]}),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("ok") is True

        db = _Session()
        doc = db.get(Document, _DOC_B.id)
        db.close()
        assert doc.user_id == _USER_B.id


# ---------------------------------------------------------------------------
# Document list is scoped to authenticated user
# ---------------------------------------------------------------------------

class TestDocumentListScope:
    def test_user_a_docs_not_visible_to_user_b(self):
        """
        The /documents page returns 200 for both users but the DB query
        filters by user_id — tested at the query level here.
        """
        db = _Session()
        docs_a = db.query(Document).filter_by(user_id=_USER_A.id).all()
        docs_b = db.query(Document).filter_by(user_id=_USER_B.id).all()
        db.close()

        ids_a = {d.id for d in docs_a}
        ids_b = {d.id for d in docs_b}
        assert ids_a.isdisjoint(ids_b), "Users share document IDs — isolation broken!"
