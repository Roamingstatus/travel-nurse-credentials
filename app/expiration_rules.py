"""Custom expiration rules applied when a document has no declared expiration date.

To add new rules, append an entry to CUSTOM_EXPIRATION_RULES.  Each rule is
evaluated in order; the first keyword match wins.

Rule format
-----------
Each entry is a dict with these keys:

  name               str       Human label prefix shown in the UI badge
  keywords           [str]     Any keyword match (case-insensitive) triggers
                               the rule against filename + title + text
  duration           dict      Flat duration applied for all states:
                                 {"years": 1} | {"months": 6} | {"days": 90}
  duration_by_state  dict      State-conditional durations; "__default__" is
                               required as the fallback:
                                 {"CA": {"years": 1}, "__default__": {"years": 2}}
                               Only one of duration / duration_by_state is needed.
  base_date_priority [str]     Ordered list of date sources to try; first
                               non-None value wins:
                                 "issue_date" | "completion_date" |
                                 "certificate_date" | "detected_date" |
                                 "upload_date"
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional


# ---------------------------------------------------------------------------
# Rule table — add entries here to extend the engine
# ---------------------------------------------------------------------------

CUSTOM_EXPIRATION_RULES: list[dict] = [
    # NIH — state-specific validity periods
    # California: 1 year from issue date
    # All other US states: 2 years from issue date
    {
        "name": "NIH",
        "keywords": [
            "nih",
            "national institutes of health",
            "nih stroke scale",
            "nihss",
            "nih stroke",
        ],
        "duration_by_state": {
            "CA": {"years": 1},
            "__default__": {"years": 2},
        },
        "base_date_priority": [
            "issue_date",
            "completion_date",
            "certificate_date",
            "detected_date",
            "upload_date",
        ],
    },
    # ── Future rules — uncomment and fill in to activate ───────────────────
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
    # {
    #     "name": "BLS Certification",
    #     "keywords": ["bls", "basic life support"],
    #     "duration": {"years": 2},
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
        except ValueError:
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


def _resolve_duration(rule: dict, state: Optional[str]) -> Optional[dict]:
    """Pick the correct duration dict for this rule and state.

    Priority:
      1. If ``duration_by_state`` is present, look up the state (uppercase).
         Falls back to ``__default__`` when the state is not listed.
      2. If plain ``duration`` is present, use it regardless of state.
    Returns *None* when no duration can be resolved (rule is skipped).
    """
    if "duration_by_state" in rule:
        by_state = rule["duration_by_state"]
        key = (state or "").strip().upper()
        return by_state.get(key) or by_state.get("__default__")
    return rule.get("duration")


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
    the best date extracted from the document itself.
    ``upload_date`` is the fallback.
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
    state: Optional[str] = None,
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
    state           : two-letter US state abbreviation (e.g. "CA"), used for
                      state-conditional duration rules

    Returns
    -------
    (expires_at, expiration_rule_applied, expiration_source)

    When a rule fires:
      - ``expires_at``              — computed expiration datetime
      - ``expiration_rule_applied`` — human label, e.g. "NIH — 2yr"
      - ``expiration_source``       — ``"custom_rule"``

    When nothing fires (or ``existing_expires`` is already set):
      - ``(existing_expires, None, None)``
    """
    if existing_expires is not None:
        return existing_expires, None, None

    for rule in CUSTOM_EXPIRATION_RULES:
        if not _matches_rule(rule, filename or "", title or "", text):
            continue

        duration = _resolve_duration(rule, state)
        if not duration:
            continue

        base, _ = _resolve_base_date(rule, issue_date, upload_date)
        if base is None:
            continue

        expires = _add_duration(base, duration)
        state_tag = f" ({state.upper()})" if state else ""
        label = f"{rule['name']} — {_duration_label(duration)}{state_tag}"
        return expires, label, "custom_rule"

    return existing_expires, None, None
