from datetime import datetime, timedelta

from .db import Document

EXPIRING_WINDOW_DAYS = 60


def status_for(doc: Document, now: datetime | None = None) -> str:
    now = now or datetime.utcnow()
    if not doc.expires_at:
        return "no-expiry"
    if doc.expires_at < now:
        return "expired"
    if doc.expires_at < now + timedelta(days=EXPIRING_WINDOW_DAYS):
        return "expiring"
    return "current"


def ui_status_label(doc: Document, now: datetime | None = None) -> str:
    """Human-facing status for UI (valid / expiring soon / expired)."""
    s = status_for(doc, now)
    if s == "expired":
        return "expired"
    if s == "expiring":
        return "expiring_soon"
    return "valid"


def days_until(doc: Document, now: datetime | None = None) -> int | None:
    if not doc.expires_at:
        return None
    now = now or datetime.utcnow()
    return (doc.expires_at - now).days


def summarize(documents: list[Document]) -> dict:
    now = datetime.utcnow()
    by_status = {"expired": [], "expiring": [], "current": [], "no-expiry": []}
    for d in documents:
        by_status[status_for(d, now)].append(d)

    recent = sorted(
        documents,
        key=lambda d: d.created_at or datetime.min,
        reverse=True,
    )[:6]

    return {
        "total": len(documents),
        "expired": by_status["expired"],
        "expiring": by_status["expiring"],
        "current": by_status["current"],
        "no_expiry": by_status["no-expiry"],
        "recent": recent,
    }
