"""Calendar export for expiration reminders (ICS). No outbound email in MVP."""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

from .db import Document


def build_expiring_ics(
    documents: list[Document],
    *,
    window_days: int = 365,
    calendar_name: str = "Credential expirations",
) -> str:
    """VEVENT per document with expires_at within window; UTC timestamps."""
    now = datetime.utcnow()
    until = now + timedelta(days=window_days)
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//skillDock//EN",
        "CALSCALE:GREGORIAN",
        f"X-WR-CALNAME:{_escape_ics_text(calendar_name)}",
    ]
    for d in documents:
        if not d.expires_at:
            continue
        exp = d.expires_at
        if exp < now or exp > until:
            continue
        uid = f"{d.id}-{uuid4().hex}@skilldock"
        dtstamp = _fmt_utc(now)
        dtend = _fmt_utc(exp)
        summary = f"Expires: {d.title}"[:200]
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{uid}",
                f"DTSTAMP:{dtstamp}",
                f"DTSTART:{dtend}",
                f"DTEND:{dtend}",
                f"SUMMARY:{_escape_ics_text(summary)}",
                f"DESCRIPTION:{_escape_ics_text(d.category + ' — renew or replace before this date.')}",
                "END:VEVENT",
            ]
        )
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines)


def _fmt_utc(dt: datetime) -> str:
    return dt.strftime("%Y%m%dT%H%M%SZ")


def _escape_ics_text(s: str) -> str:
    return (
        s.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
        .replace("\r", "")
    )
