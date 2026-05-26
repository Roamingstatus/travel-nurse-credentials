"""
Analytics queries for the admin dashboard.
All queries read from existing tables — no heavy aggregations.
"""
from datetime import datetime, timedelta

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from .db import ChecklistResult, Document, Event, ReminderSettings, ShareLink, User


def _since(days: int) -> datetime:
    return datetime.utcnow() - timedelta(days=days)


# ---------------------------------------------------------------------------
# User metrics
# ---------------------------------------------------------------------------

def user_metrics(db: Session) -> dict:
    total = db.query(func.count(User.id)).scalar() or 0
    new_today = db.query(func.count(User.id)).filter(User.created_at >= _since(1)).scalar() or 0
    new_7d = db.query(func.count(User.id)).filter(User.created_at >= _since(7)).scalar() or 0
    new_30d = db.query(func.count(User.id)).filter(User.created_at >= _since(30)).scalar() or 0

    tier_rows = (
        db.query(User.subscription_tier, func.count(User.id))
        .group_by(User.subscription_tier)
        .all()
    )
    tiers = {r[0]: r[1] for r in tier_rows}

    return {
        "total": total,
        "new_today": new_today,
        "new_7d": new_7d,
        "new_30d": new_30d,
        "free": tiers.get("free", 0),
        "premium": tiers.get("premium", 0),
        "premium_plus": tiers.get("premium_plus", 0),
    }


# ---------------------------------------------------------------------------
# Document metrics
# ---------------------------------------------------------------------------

def document_metrics(db: Session) -> dict:
    total = db.query(func.count(Document.id)).scalar() or 0
    uploaded_7d = db.query(func.count(Document.id)).filter(Document.created_at >= _since(7)).scalar() or 0
    uploaded_30d = db.query(func.count(Document.id)).filter(Document.created_at >= _since(30)).scalar() or 0

    cat_rows = (
        db.query(Document.category, func.count(Document.id))
        .group_by(Document.category)
        .order_by(func.count(Document.id).desc())
        .limit(8)
        .all()
    )

    total_users_with_docs = db.query(func.count(func.distinct(Document.user_id))).scalar() or 0
    avg_per_user = round(total / total_users_with_docs, 1) if total_users_with_docs else 0

    return {
        "total": total,
        "uploaded_7d": uploaded_7d,
        "uploaded_30d": uploaded_30d,
        "avg_per_user": avg_per_user,
        "by_category": [{"category": r[0], "count": r[1]} for r in cat_rows],
    }


# ---------------------------------------------------------------------------
# Feature usage from events table
# ---------------------------------------------------------------------------

def feature_metrics(db: Session) -> dict:
    event_types = [
        "packet_download",
        "packet_pdf",
        "share_link_created",
        "resume_enhance",
        "checklist_generate",
        "calendar_export",
        "billing_checkout_started",
        "billing_portal_opened",
        "stripe_subscription_changed",
    ]

    all_time_rows = (
        db.query(Event.event_type, func.count(Event.id))
        .filter(Event.event_type.in_(event_types), Event.ok == 1)
        .group_by(Event.event_type)
        .all()
    )
    all_time = {r[0]: r[1] for r in all_time_rows}

    last_30d_rows = (
        db.query(Event.event_type, func.count(Event.id))
        .filter(
            Event.event_type.in_(event_types),
            Event.ok == 1,
            Event.created_at >= _since(30),
        )
        .group_by(Event.event_type)
        .all()
    )
    last_30d = {r[0]: r[1] for r in last_30d_rows}

    features = [
        {"key": "packet_download",             "label": "Packet downloads (.zip)"},
        {"key": "packet_pdf",                   "label": "Manifest downloads (.pdf)"},
        {"key": "share_link_created",           "label": "Share links created"},
        {"key": "resume_enhance",               "label": "Resume enhancements"},
        {"key": "checklist_generate",           "label": "Checklist runs"},
        {"key": "calendar_export",              "label": "Calendar exports (.ics)"},
        {"key": "billing_checkout_started",     "label": "Checkout sessions started"},
        {"key": "billing_portal_opened",        "label": "Billing portal sessions"},
        {"key": "stripe_subscription_changed",  "label": "Subscription tier changes"},
    ]
    for f in features:
        f["all_time"] = all_time.get(f["key"], 0)
        f["last_30d"] = last_30d.get(f["key"], 0)

    return features


# ---------------------------------------------------------------------------
# Recent activity feed
# ---------------------------------------------------------------------------

def recent_events(db: Session, limit: int = 60) -> list:
    rows = (
        db.query(Event, User)
        .outerjoin(User, User.id == Event.user_id)
        .order_by(Event.created_at.desc())
        .limit(limit)
        .all()
    )
    result = []
    for ev, user in rows:
        result.append({
            "id": ev.id,
            "event_type": ev.event_type,
            "ok": ev.ok,
            "created_at": ev.created_at,
            "user_email": user.email if user else None,
            "user_tier": user.subscription_tier if user else None,
            "meta": ev.meta,
        })
    return result


# ---------------------------------------------------------------------------
# Failed events
# ---------------------------------------------------------------------------

def failed_events(db: Session, limit: int = 20) -> list:
    rows = (
        db.query(Event, User)
        .outerjoin(User, User.id == Event.user_id)
        .filter(Event.ok == 0)
        .order_by(Event.created_at.desc())
        .limit(limit)
        .all()
    )
    result = []
    for ev, user in rows:
        result.append({
            "id": ev.id,
            "event_type": ev.event_type,
            "created_at": ev.created_at,
            "user_email": user.email if user else None,
            "meta": ev.meta,
        })
    return result


# ---------------------------------------------------------------------------
# Misc counts
# ---------------------------------------------------------------------------

def misc_metrics(db: Session) -> dict:
    active_share_links = (
        db.query(func.count(ShareLink.id))
        .filter(ShareLink.revoked_at.is_(None))
        .scalar() or 0
    )
    reminder_users = (
        db.query(func.count(ReminderSettings.id))
        .filter(ReminderSettings.email_enabled == 1)
        .scalar() or 0
    )
    checklist_runs = db.query(func.count(ChecklistResult.id)).scalar() or 0

    return {
        "active_share_links": active_share_links,
        "reminder_users": reminder_users,
        "checklist_runs": checklist_runs,
    }
