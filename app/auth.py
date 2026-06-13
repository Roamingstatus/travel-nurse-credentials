import os
import time

from fastapi import HTTPException, Request, status

from .db import SessionLocal, User


def google_configured() -> bool:
    return bool(os.environ.get("GOOGLE_CLIENT_ID") and os.environ.get("GOOGLE_CLIENT_SECRET"))


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
                client_id=os.environ.get("GOOGLE_CLIENT_ID", ""),
                client_secret=os.environ.get("GOOGLE_CLIENT_SECRET", ""),
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
