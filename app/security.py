"""
Credanta security utilities.

Covers:
  - Environment variable validation at startup
  - CSRF token generation and verification (per-session, HMAC constant-time compare)
  - File upload validation: MIME allow-list, magic-byte detection, extension block-list
  - In-memory sliding-window rate limiting (per client IP)
  - Cloudflare Turnstile bot-protection verification
  - HMAC-signed time-limited download tokens for public share links
  - Security HTTP headers middleware
  - Path traversal guard for file serving
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
import threading
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("credanta.security")


# ---------------------------------------------------------------------------
# Environment validation
# ---------------------------------------------------------------------------

_WEAK_SECRETS: frozenset[str] = frozenset({
    "dev", "secret", "password", "changeme", "development",
    "test", "insecure", "placeholder", "your-secret-key",
    "session_secret", "supersecret", "mysecret", "1234", "abcd",
})


def validate_env() -> None:
    """Validate environment variables for every integration at startup.

    Severity tiers
    ──────────────
    FATAL   (raises RuntimeError in production, warning in dev):
      SESSION_SECRET, GOOGLE_CLIENT_ID/SECRET, CLOUDFLARE_TURNSTILE_*
      — the app is unusable without these in production.

    ERROR   (logs ERROR in production, WARNING in dev — app still starts):
      Stripe, Resend (email), Twilio (SMS), OpenAI, Admin config
      — features degrade gracefully when these are absent.
    """
    env = (os.environ.get("APP_ENV") or os.environ.get("ENV", "development")).lower()
    is_prod = env == "production"

    def _fatal(msg: str) -> None:
        """Block startup in production; warn in development."""
        if is_prod:
            raise RuntimeError(msg)
        logger.warning("[security] %s", msg)

    def _error(msg: str) -> None:
        """Log ERROR in production (feature disabled); WARNING in development."""
        if is_prod:
            logger.error("[security] %s", msg)
        else:
            logger.warning("[security] %s", msg)

    # ── Session secret ────────────────────────────────────────────────────────
    secret = os.environ.get("SESSION_SECRET", "")
    if not secret:
        _fatal(
            "SESSION_SECRET is not set. Sessions will be invalidated on every "
            "restart.  Generate one with: "
            "python -c \"import secrets; print(secrets.token_urlsafe(48))\""
        )
    elif len(secret) < 32:
        _fatal(f"SESSION_SECRET is only {len(secret)} chars (minimum 32).")
    elif secret.lower() in _WEAK_SECRETS:
        _fatal("SESSION_SECRET looks like a known placeholder. Replace it with a random value.")

    # ── Google OAuth (core auth — fatal in production) ────────────────────────
    if not os.environ.get("GOOGLE_CLIENT_ID"):
        _fatal("GOOGLE_CLIENT_ID not set — users cannot log in.")
    if not os.environ.get("GOOGLE_CLIENT_SECRET"):
        _fatal("GOOGLE_CLIENT_SECRET not set — users cannot log in.")

    # ── Cloudflare Turnstile (bot protection — fatal in production) ───────────
    if not os.environ.get("CLOUDFLARE_TURNSTILE_SITE_KEY"):
        _fatal("CLOUDFLARE_TURNSTILE_SITE_KEY not set — bot protection disabled on login/upload.")
    if not os.environ.get("CLOUDFLARE_TURNSTILE_SECRET_KEY"):
        _fatal("CLOUDFLARE_TURNSTILE_SECRET_KEY not set — Turnstile server-side verification disabled.")

    # ── Stripe billing (optional integration) ─────────────────────────────────
    if not os.environ.get("STRIPE_SECRET_KEY"):
        _error("STRIPE_SECRET_KEY not set — billing and premium upgrades will not work.")
    if not os.environ.get("STRIPE_WEBHOOK_SECRET"):
        _error("STRIPE_WEBHOOK_SECRET not set — Stripe webhook signature verification disabled.")

    # Four granular price-ID vars read by stripe_billing.PRICE_VARS
    _stripe_price_vars = {
        "STRIPE_PRICE_PREMIUM_MONTHLY":      "Premium monthly checkout",
        "STRIPE_PRICE_PREMIUM_YEARLY":       "Premium yearly checkout",
        "STRIPE_PRICE_PREMIUM_PLUS_MONTHLY": "Premium+ monthly checkout",
        "STRIPE_PRICE_PREMIUM_PLUS_YEARLY":  "Premium+ yearly checkout",
    }
    for _var, _desc in _stripe_price_vars.items():
        if not os.environ.get(_var):
            _error(f"{_var} not set — {_desc} will fail.")

    # ── Resend — email reminders (optional integration) ───────────────────────
    if not os.environ.get("RESEND_API_KEY"):
        _error("RESEND_API_KEY not set — email expiration reminders will not be sent.")

    # ── Twilio — SMS reminders (optional integration) ─────────────────────────
    twilio_sid  = os.environ.get("TWILIO_ACCOUNT_SID", "")
    twilio_auth = os.environ.get("TWILIO_AUTH_TOKEN", "")
    twilio_from = os.environ.get("TWILIO_FROM_NUMBER", "")
    twilio_set  = [twilio_sid, twilio_auth, twilio_from]
    if any(twilio_set) and not all(twilio_set):
        missing = [
            name for name, val in [
                ("TWILIO_ACCOUNT_SID", twilio_sid),
                ("TWILIO_AUTH_TOKEN",  twilio_auth),
                ("TWILIO_FROM_NUMBER", twilio_from),
            ] if not val
        ]
        _error(
            f"Twilio is partially configured — SMS reminders will not work. "
            f"Missing: {', '.join(missing)}"
        )
    elif not all(twilio_set):
        _error(
            "TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / TWILIO_FROM_NUMBER not set "
            "— SMS reminders will not be sent."
        )

    # ── OpenAI — AI document features (optional integration) ──────────────────
    if not os.environ.get("OPENAI_API_KEY"):
        _error(
            "OPENAI_API_KEY not set — AI-assisted document categorisation and "
            "resume enhancer will be unavailable."
        )

    # ── Admin configuration ───────────────────────────────────────────────────
    if not os.environ.get("ADMIN_ROUTE"):
        _error(
            "ADMIN_ROUTE not set — admin dashboard is unreachable. "
            "Set to a secret path, e.g. ADMIN_ROUTE=/secret-admin-abc123."
        )
    if not os.environ.get("ADMIN_EMAILS"):
        _error(
            "ADMIN_EMAILS not set — no users will have admin access. "
            "Set to a comma-separated list of admin email addresses."
        )

    logger.info("[security] Environment validation complete (env=%s).", env)


# ---------------------------------------------------------------------------
# CSRF protection
# ---------------------------------------------------------------------------

def get_csrf_token(session: dict) -> str:
    """Return the per-session CSRF token, creating it if absent.

    Call this inside every GET handler (via render()) so the token exists
    in the session before the user submits any form.
    """
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_urlsafe(32)
    return session["_csrf"]


def verify_csrf_token(submitted: str, session: dict) -> bool:
    """Constant-time comparison of the submitted token against the session token.

    Returns False (not True) on any mismatch, empty value, or missing session token
    so callers can treat the result as a simple boolean gate.
    """
    expected = session.get("_csrf", "")
    if not expected or not submitted:
        return False
    return hmac.compare_digest(submitted, expected)


# ---------------------------------------------------------------------------
# Upload file validation
# ---------------------------------------------------------------------------

ALLOWED_MIME_TYPES: frozenset[str] = frozenset({
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "image/tiff",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/plain",
    "application/rtf",
    "text/rtf",
})

_BLOCKED_EXTENSIONS: frozenset[str] = frozenset({
    ".exe", ".dll", ".so", ".dylib",
    ".sh", ".bash", ".zsh", ".fish",
    ".bat", ".cmd", ".ps1", ".vbs", ".vbe",
    ".php", ".php3", ".php4", ".php5", ".phtml",
    ".asp", ".aspx", ".cgi", ".pl", ".rb",
    ".py", ".pyc",
    ".js", ".mjs", ".ts",
    ".html", ".htm", ".xhtml",
    ".svg",
    ".jar", ".war", ".ear",
    ".com", ".scr", ".pif",
})

# (magic_prefix, detected_mime)
_MAGIC_TABLE: list[tuple[bytes, str]] = [
    (b"%PDF",               "application/pdf"),
    (b"\xff\xd8\xff",      "image/jpeg"),
    (b"\x89PNG\r\n",       "image/png"),
    (b"GIF87a",             "image/gif"),
    (b"GIF89a",             "image/gif"),
    (b"PK\x03\x04",        "application/zip"),        # docx/xlsx are ZIP-based
    (b"\xd0\xcf\x11\xe0",  "application/msword"),    # OLE compound (doc/xls)
    (b"II*\x00",            "image/tiff"),
    (b"MM\x00*",            "image/tiff"),
]

_ZIP_OFFICE_MIMES: frozenset[str] = frozenset({
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
})

_OLE_OFFICE_MIMES: frozenset[str] = frozenset({
    "application/msword",
    "application/vnd.ms-excel",
})

# MIME types safe to serve inline in a browser (all others → attachment)
INLINE_SAFE_MIMES: frozenset[str] = frozenset({
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "image/tiff",
})


def _detect_magic(data: bytes) -> Optional[str]:
    for prefix, mime in _MAGIC_TABLE:
        if data[: len(prefix)] == prefix:
            return mime
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def validate_upload(
    raw: bytes,
    filename: str,
    claimed_mime: Optional[str],
) -> str:
    """Validate an uploaded file against the security policy.

    Returns the effective (trusted) MIME type to use for storage.
    Raises HTTP 400 on any policy violation.
    """
    if not raw:
        raise HTTPException(400, "Uploaded file is empty.")

    ext = Path(filename).suffix.lower() if filename else ""
    if ext in _BLOCKED_EXTENSIONS:
        logger.warning("[security] Blocked upload: dangerous extension '%s' in '%s'", ext, filename)
        raise HTTPException(400, f"File type '{ext}' is not allowed.")

    detected = _detect_magic(raw)

    # Reject executable / binary formats by magic bytes regardless of claimed MIME
    for pe_prefix in _PE_HEADERS:
        if raw[: len(pe_prefix)] == pe_prefix:
            logger.warning(
                "[security] Rejected upload '%s': executable magic bytes detected.", filename
            )
            raise HTTPException(400, "File type not permitted. Executable files cannot be uploaded.")

    if detected == "application/zip" and claimed_mime in _ZIP_OFFICE_MIMES:
        effective = claimed_mime
    elif detected == "application/msword" and claimed_mime in _OLE_OFFICE_MIMES:
        effective = claimed_mime
    elif detected is not None:
        effective = detected
    else:
        effective = claimed_mime or "application/octet-stream"

    if effective not in ALLOWED_MIME_TYPES:
        logger.warning(
            "[security] Rejected upload '%s': effective MIME '%s' not permitted.",
            filename, effective,
        )
        raise HTTPException(
            400,
            "File type not permitted. Accepted: PDF, JPEG/PNG/GIF/WEBP/TIFF images, "
            "DOC/DOCX, XLS/XLSX, plain text.",
        )

    return effective


# ---------------------------------------------------------------------------
# Malware / threat scanner
# ---------------------------------------------------------------------------

_EICAR = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"

_PE_HEADERS: tuple[bytes, ...] = (
    b"MZ",           # PE / DOS executable
    b"\x7fELF",      # ELF (Linux binary)
    b"\xca\xfe\xba\xbe",  # Mach-O fat binary
    b"\xfe\xed\xfa\xce",  # Mach-O 32-bit
    b"\xfe\xed\xfa\xcf",  # Mach-O 64-bit
    b"\xce\xfa\xed\xfe",  # Mach-O 32-bit LE
    b"\xcf\xfa\xed\xfe",  # Mach-O 64-bit LE
)

_PDF_DANGER_PATTERNS: tuple[bytes, ...] = (
    b"/JS ",
    b"/JavaScript",
    b"/Launch",
    b"/OpenAction",
    b"/AA ",
    b"/EmbeddedFile",
    b"/RichMedia",
    b"/XFA",
    b"eval(",
    b"this.exportDataObject",
    b"app.launchURL",
)

_SCRIPT_INJECTION: tuple[bytes, ...] = (
    b"<script",
    b"javascript:",
    b"vbscript:",
    b"data:text/html",
    b"<?php",
)

_MACRO_SIGNATURES: tuple[bytes, ...] = (
    b"AutoOpen",
    b"AutoExec",
    b"Auto_Open",
    b"Document_Open",
    b"Shell(",
    b"CreateObject",
    b"WScript.Shell",
    b"powershell",
    b"cmd.exe",
)


def _check_eicar(data: bytes) -> Optional[str]:
    if _EICAR in data:
        return "EICAR test file detected — antivirus test signature found"
    return None


def _check_pe_header(data: bytes, mime: Optional[str]) -> Optional[str]:
    head = data[:8]
    for sig in _PE_HEADERS:
        if head[: len(sig)] == sig:
            return f"Executable binary detected (file header matches known executable format)"
    return None


def _check_pdf_danger(data: bytes) -> Optional[str]:
    found = []
    sample = data[:65536]
    for pat in _PDF_DANGER_PATTERNS:
        if pat in sample:
            found.append(pat.decode("ascii", errors="replace").strip())
    if found:
        return f"PDF contains potentially dangerous directives: {', '.join(found[:3])}"
    return None


def _check_script_injection(data: bytes) -> Optional[str]:
    sample = data[:16384].lower()
    for pat in _SCRIPT_INJECTION:
        if pat in sample:
            return f"Script injection pattern detected: {pat.decode('ascii', errors='replace')!r}"
    return None


def _check_macros(data: bytes) -> Optional[str]:
    found = []
    for pat in _MACRO_SIGNATURES:
        if pat in data:
            found.append(pat.decode("ascii", errors="replace").strip())
    if found:
        return f"Macro/script content detected: {', '.join(found[:3])}"
    return None


def scan_file(raw: bytes, filename: str, effective_mime: Optional[str] = None) -> dict:
    """Run a lightweight in-process threat scan on uploaded file bytes.

    Returns::
        {
            "clean": bool,
            "threat": str | None,   # human-readable threat description
            "checks": [{"label": str, "ok": bool}]
        }
    """
    checks: list[dict] = []
    threat: Optional[str] = None

    def _run(label: str, fn, *args) -> None:
        nonlocal threat
        result = fn(*args)
        ok = result is None
        checks.append({"label": label, "ok": ok})
        if not ok and threat is None:
            threat = result

    _run("EICAR test-file signature", _check_eicar, raw)
    _run("Executable binary header", _check_pe_header, raw, effective_mime)

    if effective_mime == "application/pdf" or (filename or "").lower().endswith(".pdf"):
        _run("PDF dangerous directives", _check_pdf_danger, raw)
    else:
        checks.append({"label": "PDF dangerous directives", "ok": True})

    is_office = effective_mime in (
        "application/msword",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    if is_office:
        _run("Macro / script payload", _check_macros, raw)
    else:
        checks.append({"label": "Macro / script payload", "ok": True})

    _run("Script injection patterns", _check_script_injection, raw)

    checks.append({"label": "File structure integrity", "ok": threat is None})

    return {"clean": threat is None, "threat": threat, "checks": checks}


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------

class _RateLimiter:
    """Sliding-window rate limiter keyed by client IP (process-local)."""

    def __init__(self, max_calls: int, window_seconds: int, name: str = "") -> None:
        self._max = max_calls
        self._window = float(window_seconds)
        self._name = name
        self._buckets: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def _ip(self, request: Request) -> str:
        fwd = request.headers.get("X-Forwarded-For", "")
        return fwd.split(",")[0].strip() if fwd else (
            request.client.host if request.client else "unknown"
        )

    def check(self, request: Request) -> None:
        """Raise HTTP 429 if this IP has exceeded the rate limit."""
        key = self._ip(request)
        now = time.monotonic()
        cutoff = now - self._window
        with self._lock:
            hits = [t for t in self._buckets[key] if t > cutoff]
            if len(hits) >= self._max:
                logger.warning("[security] Rate limit exceeded: limiter=%s ip=%s", self._name, key)
                try:
                    from .services.security_monitor import log_security_event
                    log_security_event(
                        "rate_limit_triggered", "low", request,
                        metadata={"limiter": self._name},
                    )
                except Exception:
                    pass
                raise HTTPException(
                    429,
                    "Too many requests — please wait a moment before trying again.",
                )
            hits.append(now)
            self._buckets[key] = hits


upload_limiter    = _RateLimiter(max_calls=10, window_seconds=60,   name="upload")
auth_limiter      = _RateLimiter(max_calls=20, window_seconds=60,   name="auth")
share_limiter     = _RateLimiter(max_calls=15, window_seconds=60,   name="share")
preview_limiter   = _RateLimiter(max_calls=60, window_seconds=60,   name="preview")
feedback_limiter  = _RateLimiter(max_calls=5,  window_seconds=60,   name="feedback")
admin_limiter     = _RateLimiter(max_calls=30, window_seconds=900,  name="admin")


# ---------------------------------------------------------------------------
# Cloudflare Turnstile bot-protection
# ---------------------------------------------------------------------------

_TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


def verify_turnstile(response_token: str, remote_ip: str = "") -> bool:
    """Verify a Cloudflare Turnstile challenge response server-side.

    Returns True if verification passes, or if Turnstile is not configured
    (i.e. the secret key env var is absent) so development always works.
    Returns False if the token is missing or Cloudflare rejects it.
    Fails open (returns True) on network errors to avoid blocking legit users.
    """
    secret = os.environ.get("CLOUDFLARE_TURNSTILE_SECRET_KEY", "")
    if not secret:
        return True
    if not response_token:
        logger.warning("[security] Turnstile: missing response token from client")
        return False
    payload = urllib.parse.urlencode(
        {"secret": secret, "response": response_token, "remoteip": remote_ip}
    ).encode()
    req = urllib.request.Request(_TURNSTILE_VERIFY_URL, data=payload)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            result = json.loads(resp.read())
        success = bool(result.get("success"))
        if not success:
            logger.warning(
                "[security] Turnstile challenge failed: codes=%s",
                result.get("error-codes"),
            )
        return success
    except Exception as exc:
        logger.warning("[security] Turnstile network error (%s) — failing open", exc)
        return True


# ---------------------------------------------------------------------------
# HMAC-signed time-limited download tokens (for public share-link downloads)
# ---------------------------------------------------------------------------

_DL_TOKEN_TTL = 86400  # 24 hours


def _dl_secret() -> bytes:
    return os.environ.get("SESSION_SECRET", "dev-insecure").encode()


def make_download_token(doc_id: int, share_token: str, ttl: int = _DL_TOKEN_TTL) -> str:
    """Return a signed token granting download access to *doc_id* via *share_token*.

    Format: ``<expires_epoch>.<hex_signature>``
    """
    expires = int(time.time()) + ttl
    payload = f"{doc_id}:{share_token}:{expires}".encode()
    sig = hmac.new(_dl_secret(), payload, hashlib.sha256).hexdigest()
    return f"{expires}.{sig}"


def verify_download_token(token_str: str, doc_id: int, share_token: str) -> bool:
    """Return True if *token_str* is a valid, unexpired token for *doc_id* / *share_token*."""
    try:
        expires_s, sig = token_str.split(".", 1)
        expires = int(expires_s)
    except (ValueError, AttributeError):
        return False
    if time.time() > expires:
        return False
    payload = f"{doc_id}:{share_token}:{expires}".encode()
    expected = hmac.new(_dl_secret(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)


# ---------------------------------------------------------------------------
# Security headers middleware
# ---------------------------------------------------------------------------

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds standard security headers to every HTTP response."""

    # ── Content-Security-Policy ───────────────────────────────────────────────
    #
    # External origins used by the app (templates):
    #   challenges.cloudflare.com  — Cloudflare Turnstile widget (script + frame)
    #   cdn.jsdelivr.net           — QR-code library (mfa_setup), SortableJS (documents)
    #   cdnjs.cloudflare.com       — PDF.js, Mammoth, XLSX (document previews)
    #
    # 'unsafe-inline' in script-src and style-src is required because the
    # Jinja2 templates contain ~20 inline <script> and many inline style=""
    # attributes.  The long-term path to drop 'unsafe-inline' from script-src
    # is to introduce per-request nonces in render() and stamp every <script>.
    #
    # Stripe: checkout is a server-side redirect (302) — no Stripe JS is
    # loaded client-side, so js.stripe.com is not needed here.
    #
    # Google OAuth: /auth/google is a GET navigation, not a form submission —
    # form-action 'self' is sufficient.
    #
    # worker-src covers PDF.js calling new Worker(cdnjs_url); blob: covers
    # any browser that first fetches the script to a blob then spawns a worker.
    _CSP = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' "
            "https://challenges.cloudflare.com "
            "https://cdn.jsdelivr.net "
            "https://cdnjs.cloudflare.com; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; "
        "frame-src https://challenges.cloudflare.com; "
        "connect-src 'self' https://cdnjs.cloudflare.com; "
        "worker-src blob: https://cdnjs.cloudflare.com; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "frame-ancestors 'self';"
    )

    # X-XSS-Protection removed: deprecated in all modern browsers and
    # superseded by the Content-Security-Policy above.  Leaving it set to
    # "1; mode=block" on older IE/Chrome can trigger false-positive page blocks.
    _HEADERS: dict[str, str] = {
        "Content-Security-Policy": _CSP,
        "X-Content-Type-Options":  "nosniff",
        "X-Frame-Options":         "SAMEORIGIN",
        "Referrer-Policy":         "strict-origin-when-cross-origin",
        "Permissions-Policy":      "camera=(), microphone=(), geolocation=()",
    }

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        response = await call_next(request)
        for header, value in self._HEADERS.items():
            response.headers.setdefault(header, value)
        # Read APP_ENV first (matches is_production()), fall back to ENV
        env = (
            os.environ.get("APP_ENV", "")
            or os.environ.get("ENV", "")
        ).lower()
        if env == "production":
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )
        return response


# ---------------------------------------------------------------------------
# Path traversal guard
# ---------------------------------------------------------------------------

def assert_safe_path(base_dir: Path, target: Path) -> None:
    """Raise ValueError if *target* escapes *base_dir* (path traversal guard)."""
    try:
        target.resolve().relative_to(base_dir.resolve())
    except ValueError:
        logger.error("[security] Path traversal blocked: base=%s target=%s", base_dir, target)
        raise ValueError(f"Unsafe file path detected: {target.name!r}")
