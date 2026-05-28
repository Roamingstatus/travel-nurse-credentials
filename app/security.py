"""
Credanta security utilities.

Covers:
  - Environment variable validation at startup
  - File upload validation: MIME allow-list, magic-byte detection, extension block-list
  - In-memory sliding-window rate limiting (per client IP)
  - Security HTTP headers middleware
  - Path traversal guard for file serving
"""
from __future__ import annotations

import logging
import os
import threading
import time
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
    """Validate critical environment variables at application startup.

    In production (ENV=production) any fatal misconfiguration raises
    RuntimeError and prevents the app from starting.  In development the
    same issues are logged as warnings so the dev loop is not blocked.
    """
    env = os.environ.get("ENV", "development").lower()
    is_prod = env == "production"
    secret = os.environ.get("SESSION_SECRET", "")

    if not secret:
        msg = (
            "SESSION_SECRET is not set. Sessions will be invalidated on every "
            "restart.  Generate one with: "
            "python -c \"import secrets; print(secrets.token_urlsafe(48))\""
        )
        if is_prod:
            raise RuntimeError(msg)
        logger.warning("[security] %s", msg)
    elif len(secret) < 32:
        msg = f"SESSION_SECRET is only {len(secret)} chars (minimum 32)."
        if is_prod:
            raise RuntimeError(msg)
        logger.warning("[security] %s", msg)
    elif secret.lower() in _WEAK_SECRETS:
        msg = "SESSION_SECRET looks like a known placeholder. Replace it with a random value."
        if is_prod:
            raise RuntimeError(msg)
        logger.warning("[security] %s", msg)

    if not os.environ.get("GOOGLE_CLIENT_ID"):
        logger.warning("[security] GOOGLE_CLIENT_ID not set — OAuth login will be disabled.")
    if not os.environ.get("GOOGLE_CLIENT_SECRET"):
        logger.warning("[security] GOOGLE_CLIENT_SECRET not set — OAuth login will be disabled.")

    logger.info("[security] Environment validation complete (ENV=%s).", env)


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
                raise HTTPException(
                    429,
                    "Too many requests — please wait a moment before trying again.",
                )
            hits.append(now)
            self._buckets[key] = hits


upload_limiter = _RateLimiter(max_calls=10, window_seconds=60, name="upload")
auth_limiter   = _RateLimiter(max_calls=20, window_seconds=60, name="auth")
share_limiter  = _RateLimiter(max_calls=15, window_seconds=60, name="share")


# ---------------------------------------------------------------------------
# Security headers middleware
# ---------------------------------------------------------------------------

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds standard security headers to every HTTP response."""

    _HEADERS: dict[str, str] = {
        "X-Content-Type-Options":  "nosniff",
        "X-Frame-Options":         "SAMEORIGIN",
        "X-XSS-Protection":        "1; mode=block",
        "Referrer-Policy":         "strict-origin-when-cross-origin",
        "Permissions-Policy":      "camera=(), microphone=(), geolocation=()",
    }

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        response = await call_next(request)
        for header, value in self._HEADERS.items():
            response.headers.setdefault(header, value)
        if os.environ.get("ENV", "").lower() == "production":
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
