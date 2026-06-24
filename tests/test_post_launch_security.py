"""Post-launch security regression tests."""
import hashlib
import secrets
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, Document, ShareLink, User, get_session
from app.email_auth import create_reset_token, consume_reset_token, hash_password
from app.main import app
from app.security import make_download_token

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


@pytest.fixture(autouse=True)
def _patch_db():
    app.dependency_overrides[get_session] = _db_override
    yield
    app.dependency_overrides.pop(get_session, None)


@pytest.fixture()
def client():
    return TestClient(app, raise_server_exceptions=False)


class TestResetTokenHashing:
    def test_reset_token_stored_hashed(self):
        db = _Session()
        try:
            user = User(
                google_sub=f"sub-reset-{secrets.token_hex(4)}",
                email=f"reset-{secrets.token_hex(4)}@test.com",
                name="Reset User",
            )
            db.add(user)
            db.commit()
            raw = create_reset_token(db, user)
            db.refresh(user)
            assert user.password_reset_token != raw
            assert user.password_reset_token == hashlib.sha256(raw.encode()).hexdigest()
            assert consume_reset_token(db, raw, hash_password("NewPassword12345!"))
        finally:
            db.close()


class TestShareDownloadToken:
    def test_share_download_requires_dl_token(self, client):
        db = _Session()
        try:
            user = User(google_sub="share-owner", email="owner@test.com", name="Owner")
            db.add(user)
            db.flush()
            doc = Document(
                user_id=user.id,
                title="License",
                category="Licenses & Certifications",
                original_filename="license.pdf",
                stored_filename="stored.pdf",
                mime_type="application/pdf",
                content_hash="abc123",
            )
            db.add(doc)
            db.flush()
            token = secrets.token_urlsafe(16)
            link = ShareLink(
                user_id=user.id,
                token=token,
                expires_at=datetime.utcnow() + timedelta(days=7),
            )
            db.add(link)
            db.commit()
            doc_id = doc.id
        finally:
            db.close()

        resp = client.get(f"/s/{token}/download/{doc_id}")
        assert resp.status_code == 403

        dl = make_download_token(doc_id, token)
        resp2 = client.get(f"/s/{token}/download/{doc_id}?dl={dl}")
        assert resp2.status_code in (200, 404)
