"""Custom expiration rules applied when a document has no declared expiration date.

To add new rules, append an entry to CUSTOM_EXPIRATION_RULES.  Each rule is
evaluated in order; the first keyword match wins.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional


# ---------------------------------------------------------------------------
# Rule definitions — extend here for TB, Fit Test, etc.
# ---------------------------------------------------------------------------

CUSTOM_EXPIRATION_RULES: list[dict] = [
    {
        "name": "NIH Stroke Scale",
        "keywords": [
            "nih stroke scale",
            "nihss",
            "national institutes of health stroke scale",
            "nih stroke",
        ],
        "duration": {"years": 1},
        # Tried in order; first non-None value wins.
        "base_date_priority": [
            "issue_date",
            "completion_date",
            "certificate_date",
            "detected_date",
            "upload_date",
        ],
    },
    # ── Future rules ────────────────────────────────────────────────────────
    # {
    #     "name": "TB Test",
    #     "keywords": ["tb test", "tuberculosis", "ppd", "mantoux"],
    #     "duration": {"years": 1},
    #     "base_date_priority": ["issue_date", "upload_date"],
    # },
    # {
    #     "name": "Fit Test",
    #     "keywords": ["fit test", "respirator fit", "n95 fit"],
    #     "duration": {"years": 1},
    #     "base_date_priority": ["issue_date", "upload_date"],
    # },
]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _add_duration(base: datetime, duration: dict) -> datetime:
    """Add years / months / days to *base* without requiring dateutil."""
    result = base

    years = duration.get("years", 0)
    if years:
        try:
            result = result.replace(year=result.year + years)
        except ValueError:                          # e.g. Feb 29 on non-leap year
            result = result.replace(year=result.year + years, day=28)

    months = duration.get("months", 0)
    if months:
        total = result.month + months
        year_carry = (total - 1) // 12
        new_month  = ((total - 1) % 12) + 1
        try:
            result = result.replace(year=result.year + year_carry, month=new_month)
        except ValueError:
            result = result.replace(year=result.year + year_carry, month=new_month, day=28)

    days = duration.get("days", 0)
    if days:
        result += timedelta(days=days)

    return result


def _duration_label(duration: dict) -> str:
    parts = []
    if duration.get("years"):
        parts.append(f"{duration['years']}yr")
    if duration.get("months"):
        parts.append(f"{duration['months']}mo")
    if duration.get("days"):
        parts.append(f"{duration['days']}d")
    return "+".join(parts) or "?"


def _matches_rule(rule: dict, filename: str, title: str, text: Optional[str]) -> bool:
    blob = " ".join([filename, title, text or ""]).lower()
    return any(kw in blob for kw in rule["keywords"])


def _resolve_base_date(
    rule: dict,
    issue_date: Optional[datetime],
    upload_date: Optional[datetime],
) -> tuple[Optional[datetime], Optional[str]]:
    """Return *(date, source_key)* following the rule's priority list.

    ``issue_date``, ``completion_date``, ``certificate_date``, and
    ``detected_date`` all resolve from the document's ``issued_at`` field —
    which is the best date we extracted from the document itself.
    """
    date_map: dict[str, Optional[datetime]] = {
        "issue_date":       issue_date,
        "completion_date":  issue_date,
        "certificate_date": issue_date,
        "detected_date":    issue_date,
        "upload_date":      upload_date,
    }
    for key in rule.get("base_date_priority", []):
        val = date_map.get(key)
        if val is not None:
            return val, key
    return None, None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def apply_custom_expiration_rules(
    filename: str,
    title: str,
    text: Optional[str],
    issue_date: Optional[datetime],
    upload_date: Optional[datetime],
    existing_expires: Optional[datetime],
) -> tuple[Optional[datetime], Optional[str], Optional[str]]:
    """Apply custom expiration rules when no expiration date is already set.

    Parameters
    ----------
    filename        : original filename of the uploaded document
    title           : document title / display name
    text            : extracted plain-text content (or None)
    issue_date      : detected or user-supplied issue/completion date
    upload_date     : datetime the document was uploaded (fallback base date)
    existing_expires: already-detected expiration date (rule skipped if set)

    Returns
    -------
    (expires_at, expiration_rule_applied, expiration_source)

    When a rule fires:
      - ``expires_at``              — computed expiration datetime
      - ``expiration_rule_applied`` — human label, e.g. "NIH Stroke Scale — 1yr"
      - ``expiration_source``       — ``"custom_rule"``

    When nothing fires (or ``existing_expires`` is already set):
      - ``(existing_expires, None, None)``
    """
    if existing_expires is not None:
        return existing_expires, None, None

    fn  = (filename or "").lower()
    ttl = (title    or "").lower()

    for rule in CUSTOM_EXPIRATION_RULES:
        if not _matches_rule(rule, fn, ttl, text):
            continue

        base, base_key = _resolve_base_date(rule, issue_date, upload_date)
        if base is None:
            continue

        expires = _add_duration(base, rule["duration"])
        label   = f"{rule['name']} — {_duration_label(rule['duration'])}"
        return expires, label, "custom_rule"

    return existing_expires, None, None
