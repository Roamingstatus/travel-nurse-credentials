import os

from fastapi import HTTPException, Request, status

from .db import SessionLocal, User


class _LazyOAuth:
    """Defers authlib import until the first OAuth route is hit.

    authlib.integrations.starlette_client pulls in httpx and its transports,
    which adds ~860 ms to cold-start import time. Since OAuth is only needed
    when a user clicks "Sign in with Google", we can safely defer it.
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
            self._real = inst
        return self._real

    def __getattr__(self, name: str) -> object:
        return getattr(self._get(), name)


oauth = _LazyOAuth()


def google_configured() -> bool:
    return bool(os.environ.get("GOOGLE_CLIENT_ID") and os.environ.get("GOOGLE_CLIENT_SECRET"))


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
