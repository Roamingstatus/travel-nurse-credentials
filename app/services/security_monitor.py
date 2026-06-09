"""
Security monitoring service.

Logs security events to the DB, runs pattern-based detection (admin probing,
brute-force login, share-token abuse, upload abuse, repeated 500s), and
optionally emails SECURITY_ALERT_EMAIL for high/critical findings.

Safety rules enforced here:
- Never crashes the application (all paths swallow exceptions).
- Never stores passwords, auth tokens, API keys, file contents, or private URLs.
- Sensitive metadata keys are masked to "***" before storage.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections import defaultdict
from typing import Any, Optional

from fastapi import Request

_LOG = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sensitive key names — masked before storage
# ---------------------------------------------------------------------------

_SENSITIVE_KEYS = frozenset({
    "password", "passwd", "secret", "token", "api_key", "apikey",
    "access_token", "refresh_token", "client_secret", "auth",
    "authorization", "cookie", "session", "key", "private",
    "stripe_secret", "resend_key", "twilio",
})

# ---------------------------------------------------------------------------
# In-memory detection state (process-local, sliding-window)
# ---------------------------------------------------------------------------

_lock = threading.Lock()
_probe_hits:   dict[str, list[float]] = defaultdict(list)  # ip → timestamps
_login_fails:  dict[str, list[float]] = defaultdict(list)  # "ip:email" → timestamps
_share_abuse:  dict[str, list[float]] = defaultdict(list)  # ip → timestamps
_upload_abuse: dict[str, list[float]] = defaultdict(list)  # "uid:ip" → timestamps
_srv_errors:   dict[str, list[float]] = defaultdict(list)  # route → timestamps


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _client_ip(request: Request) -> str:
    fwd = request.headers.get("X-Forwarded-For", "")
    return fwd.split(",")[0].strip() if fwd else (
        request.client.host if request.client else "unknown"
    )


def _safe_meta(meta: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of *meta* with sensitive values masked and long strings truncated."""
    if not meta:
        return {}
    out: dict[str, Any] = {}
    for k, v in meta.items():
        if any(s in k.lower() for s in _SENSITIVE_KEYS):
            out[k] = "***"
        elif isinstance(v, str) and len(v) > 500:
            out[k] = v[:200] + "…[truncated]"
        else:
            out[k] = v
    return out


def _sliding(bucket: dict[str, list[float]], key: str, window: float) -> list[float]:
    """Append *now* to *bucket[key]* and return only in-window hits."""
    now = time.monotonic()
    cutoff = now - window
    hits = [t for t in bucket[key] if t > cutoff]
    hits.append(now)
    bucket[key] = hits
    return hits


# ---------------------------------------------------------------------------
# Core logging function
# ---------------------------------------------------------------------------

def log_security_event(
    event_type: str,
    severity: str,
    request: Request,
    user=None,
    metadata: dict | None = None,
) -> None:
    """
    Write one row to ``security_events``.

    Always safe to call — swallows every exception and emits a server-side
    warning instead of crashing the request.
    """
    try:
        from ..db import SecurityEvent, SessionLocal

        ip = _client_ip(request)
        safe = _safe_meta(metadata or {})

        db = SessionLocal()
        try:
            ev = SecurityEvent(
                event_type=event_type,
                severity=severity,
                user_id=getattr(user, "id", None),
                email=getattr(user, "email", None),
                ip_address=ip[:100],
                user_agent=(request.headers.get("User-Agent", "") or "")[:300],
                route=str(request.url.path)[:200],
                method=request.method[:10],
                request_metadata=json.dumps(safe) if safe else None,
                resolved=False,
            )
            db.add(ev)
            db.commit()
        finally:
            db.close()

        _LOG.info(
            "[security_monitor] %s/%s ip=%s route=%s user=%s",
            severity, event_type, ip,
            str(request.url.path)[:60],
            getattr(user, "email", None),
        )

        if severity in ("critical", "high"):
            _maybe_alert(event_type, severity, ip, getattr(user, "email", None), safe)

    except Exception as exc:
        _LOG.warning("[security_monitor] Failed to log %s: %s", event_type, exc)


# ---------------------------------------------------------------------------
# Pattern-detection helpers (return True when threshold crossed)
# ---------------------------------------------------------------------------

def record_admin_probe(request: Request) -> bool:
    """
    Record one admin-probe hit for this IP.
    Returns True if the critical threshold (≥5 hits in 10 min) is crossed.
    """
    ip = _client_ip(request)
    with _lock:
        hits = _sliding(_probe_hits, ip, 600)
    return len(hits) >= 5


def record_login_failure(request: Request, email: str = "") -> bool:
    """
    Record one login-failure for this IP+email.
    Returns True if the brute-force threshold (≥5 in 15 min) is crossed.
    """
    ip = _client_ip(request)
    key = f"{ip}:{email.lower()}" if email else ip
    with _lock:
        hits = _sliding(_login_fails, key, 900)
    return len(hits) >= 5


def record_share_token_invalid(request: Request) -> bool:
    """
    Record one invalid share-token hit for this IP.
    Returns True if the abuse threshold (≥10 in 10 min) is crossed.
    """
    ip = _client_ip(request)
    with _lock:
        hits = _sliding(_share_abuse, ip, 600)
    return len(hits) >= 10


def record_upload_rejected(request: Request, user_id: int | None = None) -> bool:
    """
    Record one rejected upload for this user+IP.
    Returns True if the abuse threshold (≥10 in 15 min) is crossed.
    """
    ip = _client_ip(request)
    key = f"{user_id}:{ip}" if user_id else ip
    with _lock:
        hits = _sliding(_upload_abuse, key, 900)
    return len(hits) >= 10


def record_server_error(route: str) -> bool:
    """
    Record one 500 error for *route*.
    Returns True if the error-pattern threshold (≥5 in 10 min) is crossed.
    """
    with _lock:
        hits = _sliding(_srv_errors, route, 600)
    return len(hits) >= 5


# ---------------------------------------------------------------------------
# Email alerting
# ---------------------------------------------------------------------------

_ALERT_EVENT_TYPES = frozenset({
    "unauthorized_data_access",
    "admin_probe_detected",
    "server_error",
    "login_bruteforce_suspected",
    "file_access_denied",
    "share_token_abuse",
    "upload_abuse_detected",
})


def _maybe_alert(
    event_type: str,
    severity: str,
    ip: str,
    email: str | None,
    meta: dict,
) -> None:
    """Send an alert email to SECURITY_ALERT_EMAIL. Never crashes."""
    try:
        alert_to = os.environ.get("SECURITY_ALERT_EMAIL", "").strip()
        if not alert_to:
            return

        if severity == "critical" or event_type in _ALERT_EVENT_TYPES:
            pass
        else:
            return

        resend_key = os.environ.get("RESEND_API_KEY", "")
        if not resend_key:
            _LOG.warning(
                "[security_monitor] %s/%s alert skipped — RESEND_API_KEY not set",
                severity, event_type,
            )
            return

        import resend as _resend
        _resend.api_key = resend_key
        from_email = os.environ.get("RESEND_FROM_EMAIL", "alerts@credanta.com")
        subject = f"[Credanta Security] {severity.upper()}: {event_type}"
        meta_rows = "".join(
            f"<tr><td style='padding:2px 8px;border:1px solid #ccc'>{k}</td>"
            f"<td style='padding:2px 8px;border:1px solid #ccc'>{v}</td></tr>"
            for k, v in meta.items()
        )
        html = (
            f"<h2 style='color:#c00'>Security Alert — {event_type}</h2>"
            f"<p><strong>Severity:</strong> {severity.upper()}</p>"
            f"<p><strong>IP:</strong> {ip}</p>"
            f"<p><strong>User:</strong> {email or '—'}</p>"
            + (f"<table border='0' cellpadding='4' style='border-collapse:collapse;margin-top:12px'>"
               f"<thead><tr><th style='text-align:left;border:1px solid #ccc;padding:2px 8px'>Key</th>"
               f"<th style='text-align:left;border:1px solid #ccc;padding:2px 8px'>Value</th></tr></thead>"
               f"<tbody>{meta_rows}</tbody></table>" if meta_rows else "")
        )
        _resend.Emails.send({
            "from": from_email,
            "to": [alert_to],
            "subject": subject,
            "html": html,
        })
        _LOG.info(
            "[security_monitor] Alert email sent → %s for %s/%s",
            alert_to, severity, event_type,
        )
    except Exception as exc:
        _LOG.warning("[security_monitor] Failed to send alert email: %s", exc)
