"""APScheduler-based daily reminder job."""
from __future__ import annotations

import logging
from datetime import date, datetime

_LOG = logging.getLogger(__name__)
_scheduler = None


def check_expiring_documents() -> None:
    """Daily job: find documents at reminder thresholds and dispatch notifications."""
    from ..db import Document, ReminderSettings, SessionLocal, User
    from ..premium import has_premium, has_premium_plus
    from .email_service import send_expiration_email
    from .sms_service import send_expiration_sms

    _LOG.info("[scheduler] Running daily reminder check")
    db = None
    try:
        db = SessionLocal()
        today = date.today()
        active = db.query(ReminderSettings).filter(
            (ReminderSettings.email_enabled == 1) | (ReminderSettings.sms_enabled == 1)
        ).all()
        _LOG.info("[scheduler] %d users with reminders active", len(active))

        for settings in active:
            user = db.query(User).filter_by(id=settings.user_id).first()
            if not user:
                continue

            reminder_days = settings.get_days_list()
            docs = db.query(Document).filter_by(user_id=user.id).all()

            for doc in docs:
                if not doc.expires_at:
                    continue
                days_left = (doc.expires_at.date() - today).days
                if days_left not in reminder_days:
                    continue

                if settings.email_enabled and has_premium(user):
                    _send_if_not_duplicate(db, user, doc, "email", days_left, send_expiration_email)

                if settings.sms_enabled and has_premium_plus(user):
                    _send_if_not_duplicate(db, user, doc, "sms", days_left, send_expiration_sms)

    except Exception as exc:
        _LOG.error("[scheduler] Unhandled error: %s", exc)
    finally:
        if db is not None:
            db.close()


def _send_if_not_duplicate(db, user, doc, reminder_type: str, days_before: int, send_fn) -> None:
    from ..db import ReminderLog
    from ..events import log_event

    today = date.today()
    day_start = datetime.combine(today, datetime.min.time())

    already = db.query(ReminderLog).filter(
        ReminderLog.user_id == user.id,
        ReminderLog.document_id == doc.id,
        ReminderLog.reminder_type == reminder_type,
        ReminderLog.days_before == days_before,
        ReminderLog.sent_at >= day_start,
    ).first()

    if already:
        _LOG.debug("[scheduler] duplicate skip — %s doc=%s %sd", reminder_type, doc.id, days_before)
        return

    result = send_fn(user, doc, days_before)

    entry = ReminderLog(
        user_id=user.id,
        document_id=doc.id,
        reminder_type=reminder_type,
        days_before=days_before,
        sent_at=datetime.utcnow(),
        status="sent" if result.get("ok") else "failed",
        provider_message_id=result.get("message_id"),
        error_message=result.get("error") if not result.get("ok") else None,
    )
    db.add(entry)
    db.commit()

    event_type = f"reminder_{reminder_type}_sent" if result.get("ok") else "reminder_send_failed"
    log_event(event_type, user_id=user.id, meta={
        "document_id": doc.id,
        "days_before": days_before,
        "reminder_type": reminder_type,
        "subscription_tier": user.subscription_tier,
        "ok": result.get("ok"),
    }, db=db)


def start_scheduler():
    """Start the APScheduler background scheduler. Safe to call at startup."""
    global _scheduler
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        _scheduler = BackgroundScheduler(timezone="UTC")
        _scheduler.add_job(
            check_expiring_documents,
            "cron",
            hour=8,
            minute=0,
            id="daily_reminders",
            replace_existing=True,
        )
        _scheduler.start()
        _LOG.info("[scheduler] Started — daily reminders at 08:00 UTC")
        return _scheduler
    except Exception as exc:
        _LOG.error("[scheduler] Failed to start: %s", exc)
        return None


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        _LOG.info("[scheduler] Stopped")
