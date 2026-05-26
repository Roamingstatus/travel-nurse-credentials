"""
Lightweight event logging and admin-access helpers.
"""
import json
import logging
import os
from datetime import datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .db import Event, SessionLocal


def log_event(
    event_type: str,
    user_id: int | None = None,
    meta: dict | None = None,
    ok: bool = True,
    db: Session | None = None,
) -> None:
    _close = False
    if db is None:
        db = SessionLocal()
        _close = True
    try:
        ev = Event(
            event_type=event_type,
            user_id=user_id,
            meta=json.dumps(meta) if meta else None,
            ok=1 if ok else 0,
        )
        db.add(ev)
        db.commit()
    except Exception as exc:
        logging.warning(f"[events] failed to log {event_type}: {exc}")
    finally:
        if _close:
            db.close()


def _admin_emails() -> set[str]:
    raw = os.environ.get("ADMIN_EMAILS", "")
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def require_admin(user: Any) -> None:
    if not user:
        raise HTTPException(401, "Not signed in")
    emails = _admin_emails()
    if not emails:
        if os.environ.get("ENV", "").lower() == "production":
            raise HTTPException(403, "Admin access not configured")
        return
    if user.email.lower() not in emails:
        raise HTTPException(403, "Admin access required")
