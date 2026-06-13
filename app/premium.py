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

# ── Open Beta plan — features available to all users during the beta period ──
# Stored here so templates and routes can reference a single source of truth.
BETA_PLAN_FEATURES = [
    {
        "key": "document_portfolio",
        "name": "Document Portfolio",
        "description": "Store and organize all your credential documents in one place.",
        "icon": '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>',
    },
    {
        "key": "expiration_tracking",
        "name": "Expiration Tracking",
        "description": "See what's valid, expiring soon, or expired at a glance.",
        "icon": '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>',
    },
    {
        "key": "expiration_reminders",
        "name": "Expiration Reminders",
        "description": "Get email alerts before credentials expire — 30, 14, 7 days out.",
        "icon": '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>',
    },
    {
        "key": "submission_packets",
        "name": "Submission Packets",
        "description": "Bundle credentials into a clean ZIP or PDF for agency submissions.",
        "icon": '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>',
    },
    {
        "key": "recruiter_share_links",
        "name": "Recruiter Share Links",
        "description": "Share credentials via secure links — no login required for recruiters.",
        "icon": '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>',
    },
    {
        "key": "resume_enhancer",
        "name": "Resume Enhancer",
        "description": "Improve resume wording with AI-assisted suggestions.",
        "icon": '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>',
    },
    {
        "key": "smart_checklist",
        "name": "Smart Checklist",
        "description": "Track credential readiness with a profession-specific checklist.",
        "icon": '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>',
    },
    {
        "key": "calendar_sync",
        "name": "Calendar Feed",
        "description": "Subscribe to credential expirations in Google, Outlook, or Apple Calendar.",
        "icon": '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>',
    },
]

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
