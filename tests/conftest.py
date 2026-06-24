"""Shared fixtures for Credanta tests."""
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, Document, ShareLink, User

# ---------------------------------------------------------------------------
# In-memory SQLite engine (isolated per test session)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def engine():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine):
    """Per-test transactional session that rolls back after each test."""
    connection = engine.connect()
    transaction = connection.begin()
    Session = sessionmaker(bind=connection, autoflush=False, autocommit=False)
    session = Session()
    yield session
    session.close()
    transaction.rollback()
    connection.close()


# ---------------------------------------------------------------------------
# Common model factories
# ---------------------------------------------------------------------------

@pytest.fixture
def user(db):
    u = User(google_sub="sub-test-001", email="nurse@test.com", name="Test Nurse")
    db.add(u)
    db.flush()
    return u


@pytest.fixture
def make_doc(db, user):
    """Factory: make_doc(category, expires_at=...) → Document"""
    def _make(
        category="Licenses & Certifications",
        title="RN License",
        original_filename="rn_license.pdf",
        stored_filename="abc123.pdf",
        mime_type="application/pdf",
        expires_at=None,
        issued_at=None,
        size_bytes=1024,
        content_hash=None,
    ):
        doc = Document(
            user_id=user.id,
            category=category,
            title=title,
            original_filename=original_filename,
            stored_filename=stored_filename,
            mime_type=mime_type,
            expires_at=expires_at,
            issued_at=issued_at,
            size_bytes=size_bytes,
            content_hash=content_hash or f"hash-{title}-{category}",
        )
        db.add(doc)
        db.flush()
        return doc
    return _make


@pytest.fixture
def make_share(db, user):
    """Factory: make_share(expires_at=..., revoked_at=...) → ShareLink"""
    def _make(token="test-token-abc", expires_at=None, revoked_at=None):
        link = ShareLink(
            user_id=user.id,
            token=token,
            expires_at=expires_at,
            revoked_at=revoked_at,
        )
        db.add(link)
        db.flush()
        return link
    return _make


# ---------------------------------------------------------------------------
# Temp upload directory
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_upload_dir(tmp_path, monkeypatch):
    """Redirect upload root to a temp path for the duration of the test."""
    import app.storage as storage
    monkeypatch.setattr(storage, "_upload_root", tmp_path)
    return tmp_path
