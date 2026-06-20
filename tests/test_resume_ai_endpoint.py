import json
import logging
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, Event, ResumeAIUsage, User
from app.main import resume_ai_event, resume_enhance_ai
from app.services.openai_service import CredantaAIError


class FakeRequest:
    def __init__(self, payload: dict, user_id: int | None = None):
        self._payload = payload
        self.session = {}
        if user_id is not None:
            self.session["user_id"] = user_id

    async def json(self):
        return self._payload


@pytest.fixture
def resume_ai_db(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    db = Session()
    user = User(email="resume-ai@test.com", name="Resume AI Tester", google_sub="resume-ai-sub")
    db.add(user)
    db.commit()
    db.refresh(user)

    monkeypatch.setattr("app.auth.SessionLocal", Session)
    yield db, user
    db.close()
    engine.dispose()


def _success_payload() -> dict:
    return {
        "professionalVersion": "Professional version",
        "recruiterVersion": "Recruiter version",
        "impactVersion": "Impact version",
        "suggestedKeywords": ["travel nursing"],
        "improvementNotes": ["Keep facts intact."],
    }


def _json_response_body(response) -> dict:
    return json.loads(response.body.decode("utf-8"))


@pytest.mark.anyio
async def test_authenticated_request_works(resume_ai_db, monkeypatch):
    db, user = resume_ai_db
    monkeypatch.setattr("app.main.generate_resume_versions", lambda **_kwargs: _success_payload())

    response = await resume_enhance_ai(
        FakeRequest({"resumeText": "Managed ICU patient care.", "targetRole": "Travel Nurse"}, user.id),
        db,
    )

    body = _json_response_body(response)
    assert response.status_code == 200
    assert body["success"] is True
    assert body["data"]["professionalVersion"] == "Professional version"


@pytest.mark.anyio
async def test_unauthenticated_request_returns_401(resume_ai_db):
    db, _user = resume_ai_db

    response = await resume_enhance_ai(
        FakeRequest({"resumeText": "Managed ICU patient care."}),
        db,
    )

    assert response.status_code == 401
    assert _json_response_body(response)["success"] is False


@pytest.mark.anyio
async def test_empty_resume_returns_400(resume_ai_db):
    db, user = resume_ai_db

    response = await resume_enhance_ai(FakeRequest({"resumeText": "   "}, user.id), db)

    assert response.status_code == 400
    assert _json_response_body(response)["success"] is False


@pytest.mark.anyio
async def test_oversized_resume_returns_400(resume_ai_db):
    db, user = resume_ai_db

    response = await resume_enhance_ai(FakeRequest({"resumeText": "x" * 12_001}, user.id), db)

    assert response.status_code == 400
    assert _json_response_body(response)["success"] is False


@pytest.mark.anyio
async def test_rate_limit_returns_429(resume_ai_db, monkeypatch):
    db, user = resume_ai_db
    for _ in range(3):
        db.add(
            ResumeAIUsage(
                user_id=user.id,
                target_role="Travel Nurse",
                model_used="gpt-5.4-mini",
                created_at=datetime.utcnow(),
            )
        )
    db.commit()
    monkeypatch.setattr("app.main.generate_resume_versions", lambda **_kwargs: _success_payload())

    response = await resume_enhance_ai(FakeRequest({"resumeText": "Managed ICU patient care."}, user.id), db)

    assert response.status_code == 429
    assert _json_response_body(response)["success"] is False


@pytest.mark.anyio
async def test_openai_failure_returns_friendly_error(resume_ai_db, monkeypatch):
    db, user = resume_ai_db

    def _fail(**_kwargs):
        raise CredantaAIError("raw provider failure", "OPENAI_OPERATION_FAILED", 502)

    monkeypatch.setattr("app.main.generate_resume_versions", _fail)

    response = await resume_enhance_ai(FakeRequest({"resumeText": "Managed ICU patient care."}, user.id), db)

    assert response.status_code == 502
    assert _json_response_body(response) == {
        "success": False,
        "message": "Unable to enhance resume right now. Please try again.",
    }


@pytest.mark.anyio
async def test_resume_text_does_not_appear_in_logs(resume_ai_db, monkeypatch, caplog):
    db, user = resume_ai_db
    secret_resume_text = "SECRET_RESUME_TEXT_SHOULD_NOT_BE_LOGGED"
    monkeypatch.setattr("app.main.generate_resume_versions", lambda **_kwargs: _success_payload())

    with caplog.at_level(logging.INFO):
        response = await resume_enhance_ai(
            FakeRequest({"resumeText": secret_resume_text, "targetRole": "ICU Nurse"}, user.id),
            db,
        )

    assert response.status_code == 200
    assert secret_resume_text not in caplog.text


@pytest.mark.anyio
async def test_resume_ai_analytics_event_logged(resume_ai_db):
    db, user = resume_ai_db

    response = await resume_ai_event(FakeRequest({"event": "resume_ai_copy", "tab": "professional"}, user.id), db)

    assert response.status_code == 200
    event = db.query(Event).filter_by(user_id=user.id, event_type="resume_ai_copy").first()
    assert event is not None
    assert "professional" in (event.meta or "")


@pytest.mark.anyio
async def test_resume_ai_analytics_rejects_unknown_event(resume_ai_db):
    db, user = resume_ai_db

    response = await resume_ai_event(FakeRequest({"event": "resume_text_should_never_log"}, user.id), db)

    assert response.status_code == 400
