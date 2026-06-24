import logging
import os
import time

from fastapi import HTTPException, Request, status

from .db import SessionLocal, User

logger = logging.getLogger("credanta.auth")

_GOOGLE_ID_SUFFIX_LEN = 12


def _oauth_env(name: str) -> str:
    """Read an OAuth env var, stripping whitespace and optional surrounding quotes."""
    raw = os.environ.get(name, "")
    if not raw:
        return ""
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
        value = value[1:-1].strip()
    return value


def google_client_id() -> str:
    return _oauth_env("GOOGLE_CLIENT_ID")


def google_client_secret() -> str:
    return _oauth_env("GOOGLE_CLIENT_SECRET")


def google_configured() -> bool:
    return bool(google_client_id() and google_client_secret())


def expected_google_callback_url() -> str:
    """Best-effort callback URL for startup diagnostics (no request context)."""
    base = _oauth_env("APP_BASE_URL").rstrip("/")
    if not base:
        railway_domain = _oauth_env("RAILWAY_PUBLIC_DOMAIN")
        if railway_domain:
            base = f"https://{railway_domain.rstrip('/')}"
    if base:
        return f"{base}/auth/google/callback"
    return "<derived at request time from Host header — set APP_BASE_URL on Railway>"


def log_google_oauth_diagnostics() -> None:
    """Safe startup logging for Google OAuth — never logs full client ID or secret."""
    cid = google_client_id()
    secret = google_client_secret()
    id_suffix = (
        cid[-_GOOGLE_ID_SUFFIX_LEN:]
        if len(cid) >= _GOOGLE_ID_SUFFIX_LEN
        else "(too short or missing)"
    )

    logger.warning(
        "[oauth] Google Client ID configured: %s | Google Client Secret configured: %s | Client ID suffix: ...%s",
        "YES" if cid else "NO",
        "YES" if secret else "NO",
        id_suffix,
    )
    logger.warning("[oauth] Expected callback URL: %s", expected_google_callback_url())

    if cid and secret:
        if cid == secret:
            logger.error(
                "[oauth] GOOGLE_CLIENT_SECRET equals GOOGLE_CLIENT_ID — causes Google error 401 invalid_client. "
                "Set GOOGLE_CLIENT_SECRET to the secret from Google Cloud Console (starts with GOCSPX-)."
            )
        elif secret.endswith(".apps.googleusercontent.com"):
            logger.error(
                "[oauth] GOOGLE_CLIENT_SECRET looks like a Client ID, not a secret — causes 401 invalid_client."
            )
        if not cid.endswith(".apps.googleusercontent.com"):
            logger.error(
                "[oauth] GOOGLE_CLIENT_ID format unexpected — should end with .apps.googleusercontent.com"
            )


def microsoft_configured() -> bool:
    return bool(
        os.environ.get("MICROSOFT_CLIENT_ID") and os.environ.get("MICROSOFT_CLIENT_SECRET")
    )


def apple_configured() -> bool:
    return bool(
        os.environ.get("APPLE_CLIENT_ID")
        and os.environ.get("APPLE_TEAM_ID")
        and os.environ.get("APPLE_KEY_ID")
        and os.environ.get("APPLE_PRIVATE_KEY")
    )


def generate_apple_client_secret() -> str:
    """Generate a short-lived JWT client_secret for Apple Sign In (ES256, 6 months)."""
    from authlib.jose import jwt as _jwt

    private_key_pem = os.environ.get("APPLE_PRIVATE_KEY", "")
    # Handle secrets stored with literal \n instead of real newlines
    if "\\n" in private_key_pem:
        private_key_pem = private_key_pem.replace("\\n", "\n")

    now = int(time.time())
    header = {"alg": "ES256", "kid": os.environ.get("APPLE_KEY_ID", "")}
    payload = {
        "iss": os.environ.get("APPLE_TEAM_ID", ""),
        "iat": now,
        "exp": now + 15_897_600,  # 6 months — safe for container lifetime
        "aud": "https://appleid.apple.com",
        "sub": os.environ.get("APPLE_CLIENT_ID", ""),
    }
    token_bytes = _jwt.encode(header, payload, private_key_pem)
    return token_bytes.decode("utf-8") if isinstance(token_bytes, bytes) else token_bytes


class _LazyOAuth:
    """Defers authlib import until the first OAuth route is hit.

    authlib.integrations.starlette_client pulls in httpx and its transports,
    which adds ~860 ms to cold-start import time. Since OAuth is only needed
    when a user clicks a sign-in button, we can safely defer it.
    """

    _real: object | None = None

    def _get(self) -> object:
        if self._real is None:
            from authlib.integrations.starlette_client import OAuth

            inst = OAuth()
            inst.register(
                name="google",
                client_id=google_client_id(),
                client_secret=google_client_secret(),
                server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
                client_kwargs={"scope": "openid email profile"},
            )
            if microsoft_configured():
                inst.register(
                    name="microsoft",
                    client_id=os.environ.get("MICROSOFT_CLIENT_ID", ""),
                    client_secret=os.environ.get("MICROSOFT_CLIENT_SECRET", ""),
                    server_metadata_url=(
                        "https://login.microsoftonline.com/common/v2.0"
                        "/.well-known/openid-configuration"
                    ),
                    client_kwargs={"scope": "openid email profile"},
                )
            self._real = inst
        return self._real

    def __getattr__(self, name: str) -> object:
        return getattr(self._get(), name)


oauth = _LazyOAuth()


def current_user(request: Request) -> User | None:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    db = SessionLocal()
    try:
        return db.get(User, user_id)
    finally:
        db.close()


def require_user(request: Request) -> User:
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not signed in")
    return user
