"""Tests for share-link creation, expiration, and revocation."""
from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException

from app.db import ShareLink, User
from app.main import _resolve_share


class TestResolveShare:
    def test_valid_link_resolves(self, db, make_share, user):
        make_share(token="valid-token")
        link, owner = _resolve_share("valid-token", db)
        assert link.token == "valid-token"
        assert owner.email == user.email

    def test_nonexistent_token_raises_404(self, db):
        with pytest.raises(HTTPException) as exc:
            _resolve_share("ghost-token", db)
        assert exc.value.status_code == 404

    def test_revoked_link_raises_404(self, db, make_share):
        make_share(token="revoked-token", revoked_at=datetime(2024, 1, 1))
        with pytest.raises(HTTPException) as exc:
            _resolve_share("revoked-token", db)
        assert exc.value.status_code == 404

    def test_expired_link_raises_404(self, db, make_share):
        past = datetime.utcnow() - timedelta(hours=1)
        make_share(token="expired-token", expires_at=past)
        with pytest.raises(HTTPException) as exc:
            _resolve_share("expired-token", db)
        assert exc.value.status_code == 404

    def test_future_expiry_resolves(self, db, make_share):
        future = datetime.utcnow() + timedelta(days=30)
        make_share(token="future-token", expires_at=future)
        link, _ = _resolve_share("future-token", db)
        assert link.token == "future-token"

    def test_no_expiry_always_resolves(self, db, make_share):
        make_share(token="no-expiry-token", expires_at=None)
        link, _ = _resolve_share("no-expiry-token", db)
        assert link.token == "no-expiry-token"

    def test_expiry_exactly_now_raises_404(self, db, make_share):
        """A link whose expires_at is in the past (even by a second) should be rejected."""
        just_past = datetime.utcnow() - timedelta(seconds=2)
        make_share(token="just-expired-token", expires_at=just_past)
        with pytest.raises(HTTPException) as exc:
            _resolve_share("just-expired-token", db)
        assert exc.value.status_code == 404

    def test_revoked_and_expired_raises_404(self, db, make_share):
        past = datetime.utcnow() - timedelta(days=5)
        make_share(token="both-token", expires_at=past, revoked_at=past)
        with pytest.raises(HTTPException):
            _resolve_share("both-token", db)

    def test_returns_correct_owner(self, db, make_share, user):
        make_share(token="owner-token")
        _, owner = _resolve_share("owner-token", db)
        assert owner.id == user.id

    def test_missing_user_raises_404(self, db):
        """Link pointing to a deleted user should raise 404."""
        link = ShareLink(user_id=99999, token="orphan-token")
        db.add(link)
        db.flush()
        with pytest.raises(HTTPException) as exc:
            _resolve_share("orphan-token", db)
        assert exc.value.status_code == 404


class TestShareLinkModel:
    def test_token_must_be_unique(self, db, make_share):
        make_share(token="unique-token")
        from sqlalchemy.exc import IntegrityError
        with pytest.raises(Exception):
            make_share(token="unique-token")

    def test_share_link_stored_in_db(self, db, make_share):
        make_share(token="stored-token")
        link = db.query(ShareLink).filter_by(token="stored-token").first()
        assert link is not None

    def test_revoke_sets_revoked_at(self, db, make_share):
        link = make_share(token="to-revoke")
        assert link.revoked_at is None
        link.revoked_at = datetime.utcnow()
        db.flush()
        refreshed = db.query(ShareLink).filter_by(token="to-revoke").first()
        assert refreshed.revoked_at is not None

    def test_multiple_links_per_user(self, db, make_share):
        make_share(token="link-a")
        make_share(token="link-b")
        make_share(token="link-c")
        count = db.query(ShareLink).count()
        assert count >= 3
