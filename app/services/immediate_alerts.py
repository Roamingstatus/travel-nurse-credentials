"""Immediate expired-document alert helper.

Call check_and_send_immediate_expired_alert() after:
  - document upload
  - expiration date edit
  - daily scheduler sweep

The helper is idempotent — duplicate-protection via reminder_logs ensures
each channel fires at most once per document.
"""
from __future__ import annotations

import logging
from datetime import date, datetime

_LOG = logging.getLogger(__name__)


def check_and_send_immediate_expired_alert(user, document, db) -> dict:
    """Send one-time expired-document alerts for premium users.

    Returns {"email": result_or_None, "sms": result_or_None}.
    Never raises — all failures are logged and recorded in reminder_logs.
    """
    result: dict = {"email": None, "sms": None}
    try:
        if not document.expires_at:
            return result
        if document.expires_at.date() >= date.today():
            return result

        from ..premium import has_premium, has_premium_plus
        if not has_premium(user):
            return result

        from .email_service import send_expired_document_email
        from .sms_service import send_expired_document_sms

        settings = getattr(user, "reminder_settings", None)

        # ── Email (Premium+) ──────────────────────────────────────────────────
        if has_premium(user) and settings and settings.email_enabled:
            if not _already_sent(db, user.id, document.id, "email"):
                email_result = send_expired_document_email(user, document)
                _write_log(db, user, document, "email", email_result)
                result["email"] = email_result
            else:
                result["email"] = {"ok": True, "duplicate": True}

        # ── SMS (Premium+ only) ───────────────────────────────────────────────
        if has_premium_plus(user) and settings and settings.sms_enabled:
            phone = (settings.phone_number or None) or getattr(user, "phone_number", None)
            if phone:
                if not _already_sent(db, user.id, document.id, "sms"):
                    sms_result = send_expired_document_sms(user, document)
                    _write_log(db, user, document, "sms", sms_result)
                    result["sms"] = sms_result
                else:
                    result["sms"] = {"ok": True, "duplicate": True}

    except Exception as exc:
        _LOG.error(
            "[immediate_alerts] error for doc=%s user=%s: %s",
            getattr(document, "id", "?"),
            getattr(user, "id", "?"),
            exc,
        )
    return result


def get_expired_alert_statuses(db, user_id: int, doc_ids: list[int]) -> dict:
    """Return {doc_id: {"email": "sent"|"failed"|None, "sms": "sent"|"failed"|None}}
    for documents with at least one immediate_expired reminder_log entry."""
    if not doc_ids:
        return {}

    from ..db import ReminderLog

    logs = (
        db.query(ReminderLog)
        .filter(
            ReminderLog.user_id == user_id,
            ReminderLog.document_id.in_(doc_ids),
            ReminderLog.trigger_type == "immediate_expired",
        )
        .order_by(ReminderLog.sent_at.asc())
        .all()
    )

    statuses: dict = {}
    for log in logs:
        if log.document_id not in statuses:
            statuses[log.document_id] = {}
        statuses[log.document_id][log.reminder_type] = log.status
    return statuses


def _already_sent(db, user_id: int, document_id: int, reminder_type: str) -> bool:
    from ..db import ReminderLog

    return (
        db.query(ReminderLog)
        .filter(
            ReminderLog.user_id == user_id,
            ReminderLog.document_id == document_id,
            ReminderLog.reminder_type == reminder_type,
            ReminderLog.trigger_type == "immediate_expired",
        )
        .first()
    ) is not None


def _write_log(db, user, document, reminder_type: str, result: dict) -> None:
    from ..db import ReminderLog
    from ..events import log_event

    entry = ReminderLog(
        user_id=user.id,
        document_id=document.id,
        reminder_type=reminder_type,
        trigger_type="immediate_expired",
        days_before=0,
        sent_at=datetime.utcnow(),
        status="sent" if result.get("ok") and not result.get("duplicate") else "failed",
        provider_message_id=result.get("message_id"),
        error_message=result.get("error") if not result.get("ok") else None,
    )
    try:
        db.add(entry)
        db.commit()
    except Exception as exc:
        _LOG.error("[immediate_alerts] failed to write log: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass

    ok = result.get("ok") and not result.get("duplicate")
    event_type = (
        f"expired_alert_{reminder_type}_sent"
        if ok
        else (
            "expired_alert_skipped_duplicate"
            if result.get("duplicate")
            else "expired_alert_failed"
        )
    )
    try:
        log_event(
            event_type,
            user_id=user.id,
            meta={
                "document_id": document.id,
                "subscription_tier": user.subscription_tier,
                "trigger_type": "immediate_expired",
                "reminder_type": reminder_type,
            },
            db=db,
        )
    except Exception as exc:
        _LOG.error("[immediate_alerts] failed to log event: %s", exc)
