import os

from fastapi import HTTPException
from .db import User

# ── Beta mode ────────────────────────────────────────────────────────────────
# When True every signed-in user gets full Premium Plus access for free.
# Flip to False (or set env var BETA_MODE=false) when paid tiers go live.
_BETA_MODE: bool = os.environ.get("BETA_MODE", "true").lower() != "false"
# ─────────────────────────────────────────────────────────────────────────────

PREMIUM_FEATURES = [
    {
        "key": "expiration_reminders",
        "name": "Expiration Reminders",
        "description": "Get email and SMS alerts before credentials expire — 30, 14, 7 days out and on the day.",
        "action_url": "/premium/reminders/settings",
        "action_label": "Manage Reminders",
    },
    {
        "key": "calendar_sync",
        "name": "Calendar Sync",
        "description": "Export all expiration dates as a .ics file and sync with Google Calendar, Outlook, or Apple Calendar.",
        "action_url": "/premium/calendar/export",
        "action_label": "Export Calendar",
    },
    {
        "key": "packet_generation",
        "name": "Packet Generator",
        "description": "Bundle all your credentials into a clean ZIP file or PDF cover sheet for agency submissions.",
        "action_url": "/premium/packet/generate",
        "action_label": "Generate Packet",
    },
    {
        "key": "resume_enhancer",
        "name": "Resume Enhancer",
        "description": "Upload your resume and get AI-powered bullet improvements and summary rewrites.",
        "action_url": "/premium/resume/enhance",
        "action_label": "Enhance Resume",
    },
]

PREMIUM_PLUS_FEATURES = [
    {
        "key": "recruiter_share_link",
        "name": "Recruiter Share Link",
        "description": "Create secure, time-limited links so recruiters can view your credentials without logging in.",
        "action_url": "/share",
        "action_label": "Manage Share Links",
    },
    {
        "key": "agency_packet_autofill",
        "name": "Agency Packet Auto-Fill",
        "description": "Select an agency template and see exactly which documents are ready, missing, or expired.",
        "action_url": "/premium-plus/agency-packet/autofill",
        "action_label": "Auto-Fill Packet",
    },
    {
        "key": "smart_checklist",
        "name": "Smart Checklist Tracker",
        "description": "Choose your profession and get a readiness score showing complete, missing, and expiring credentials.",
        "action_url": "/premium-plus/checklist",
        "action_label": "View Checklist",
    },
    {
        "key": "one_click_submission",
        "name": "One-Click Submission",
        "description": "Submit your full credential packet directly to partner agencies in one click.",
        "action_url": None,
        "action_label": "Coming Soon",
        "coming_soon": True,
    },
]


def has_premium(user: "User | None") -> bool:
    if not user:
        return False
    if _BETA_MODE:
        return True
    tier = getattr(user, "subscription_tier", "free") or "free"
    return tier in ("premium", "premium_plus")


def has_premium_plus(user: "User | None") -> bool:
    if not user:
        return False
    if _BETA_MODE:
        return True
    tier = getattr(user, "subscription_tier", "free") or "free"
    return tier == "premium_plus"


def require_premium(user: "User | None") -> None:
    if not has_premium(user):
        raise HTTPException(403, "Upgrade required to access this feature.")


def require_premium_plus(user: "User | None") -> None:
    if not has_premium_plus(user):
        raise HTTPException(403, "Upgrade required to access this feature.")


def user_has_premium(user: "User | None") -> bool:
    """Backward-compatible alias for has_premium()."""
    return has_premium(user)
