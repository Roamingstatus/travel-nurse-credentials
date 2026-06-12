import os

from fastapi import HTTPException
from .db import User

# ── Environment detection ─────────────────────────────────────────────────────
# Priority: APP_ENV → ENV (legacy) → Replit deployment auto-detect → "development"

def _detect_app_env() -> str:
    for key in ("APP_ENV", "ENV"):
        val = os.environ.get(key, "").lower()
        if val in ("development", "production"):
            return val
    # Auto-detect Replit deployment (deployed apps set REPLIT_DEPLOYMENT_ID)
    if os.environ.get("REPLIT_DEPLOYMENT_ID") or os.environ.get("REPLIT_DEPLOYMENT"):
        return "production"
    return "development"


_APP_ENV: str = _detect_app_env()


def is_development() -> bool:
    """Return True when running in the development/preview environment."""
    return _APP_ENV == "development"


def is_production() -> bool:
    """Return True when running in a public production/deployed environment."""
    return _APP_ENV == "production"


# ── Admin access ──────────────────────────────────────────────────────────────
def _admin_email_set() -> set:
    raw = os.environ.get("ADMIN_EMAILS", "")
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def is_admin(user: "User | None") -> bool:
    """True if user is in the ADMIN_EMAILS allowlist (or any user in dev when no list is set)."""
    if not user:
        return False
    emails = _admin_email_set()
    if not emails:
        return is_development()
    return user.email.lower() in emails


# ── Beta mode ────────────────────────────────────────────────────────────────
# BETA_MODE=true  — legacy flag; same effect as BETA_UNLOCK_ALL_FEATURES.
# BETA_UNLOCK_ALL_FEATURES=true — public beta flag per spec; grants every
#   logged-in user full Premium Plus access without a Stripe subscription.
#   Stripe code and premium gating logic are preserved for future use; this
#   flag bypasses the gating only while the beta is active.
_BETA_MODE: bool = (
    os.environ.get("BETA_MODE", "false").lower() == "true"
    or os.environ.get("BETA_UNLOCK_ALL_FEATURES", "false").lower() == "true"
)
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
        "key": "packet_generation",
        "name": "Packet Generator",
        "description": "Bundle all your credentials into a clean ZIP file or PDF cover sheet for agency submissions.",
        "action_url": "/premium/packet/generate",
        "action_label": "Generate Packet",
    },
]

PREMIUM_PLUS_FEATURES = [
    {
        "key": "calendar_sync",
        "name": "Auto-Syncing Calendar Feed",
        "description": "Subscribe once in Google Calendar, Outlook, or Apple Calendar — your credential expirations stay in sync automatically.",
        "action_url": "/premium/calendar",
        "action_label": "Get Calendar Feed",
    },
    {
        "key": "recruiter_share_link",
        "name": "Recruiter Share Link",
        "description": "Create secure, time-limited links so recruiters can view your credentials without logging in.",
        "action_url": "/share",
        "action_label": "Manage Share Links",
    },
    {
        "key": "sms_reminders",
        "name": "SMS Expiration Reminders",
        "description": "Get a text message when a credential is 30, 14, 7, or 0 days from expiring — straight to your phone.",
        "action_url": "/premium/reminders/settings",
        "action_label": "Configure SMS Reminders",
        "coming_soon": True,
    },
    {
        "key": "agency_packet_autofill",
        "name": "Agency Packet Auto-Fill",
        "description": "Select an agency template and see exactly which documents are ready, missing, or expired.",
        "action_url": "/premium-plus/agency-packet/autofill",
        "action_label": "Auto-Fill Packet",
        "coming_soon": True,
    },
    {
        "key": "smart_checklist",
        "name": "Smart Checklist Tracker",
        "description": "Choose your profession and get a readiness score showing complete, missing, and expiring credentials.",
        "action_url": "/premium-plus/checklist",
        "action_label": "View Checklist",
        "coming_soon": True,
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


# ── Centralized feature-access helpers ────────────────────────────────────────
# Use these in route handlers and templates instead of ad-hoc checks.

def can_access_security_settings(user: "User | None") -> bool:
    """Security / account settings — available to every logged-in user."""
    return user is not None


def can_access_two_step_verification(user: "User | None") -> bool:
    """Two-step verification (MFA) — available to every logged-in user."""
    return user is not None


def can_access_beta_feedback(user: "User | None") -> bool:
    """Beta feedback widget — available to every logged-in user."""
    return user is not None


def can_access_admin_testing(user: "User | None") -> bool:
    """Admin testing dashboard — admin-allowlisted users only."""
    return is_admin(user)


def can_access_premium_feature(user: "User | None") -> bool:
    """Premium (or Premium+) gated feature."""
    return has_premium(user)


def can_access_premium_plus_feature(user: "User | None") -> bool:
    """Premium+ gated feature."""
    return has_premium_plus(user)
