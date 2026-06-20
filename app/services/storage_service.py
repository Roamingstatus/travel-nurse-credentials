"""
Persistent storage adapter for Credanta document uploads.

Uses Replit Object Storage when available (production deployments); falls
back to the local filesystem for development or when no bucket is configured.

New uploads always go to the best-available backend.
Reads try the document's recorded provider first, then fall back to the
other backend — so files uploaded before migration continue to work.

Object key format:  users/{user_id}/documents/{stored_filename}
Provider constants: PROVIDER_LOCAL  = "local"
                    PROVIDER_REPLIT = "replit_object_storage"
"""
import logging
import os
import secrets
from pathlib import Path
from typing import Optional

logger = logging.getLogger("credanta.storage_service")

PROVIDER_LOCAL  = "local"
PROVIDER_REPLIT = "replit_object_storage"

_client_unavailable_logged = False


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _object_key(user_id: int, stored_filename: str) -> str:
    """Canonical object storage key.  Never uses the raw user-supplied filename."""
    safe = Path(stored_filename).name
    return f"users/{user_id}/documents/{safe}"


def _get_client():
    """Return an initialised Replit Object Storage Client, or None.

    Returns None when:
    - The package is not installed
    - No bucket ID is configured
    - Any other initialisation / auth error

    Reads the bucket ID from DEFAULT_OBJECT_STORAGE_BUCKET_ID (set by
    Replit's Object Storage integration) and passes it explicitly to
    Client() so we never depend on the sidecar returning a non-empty value.
    """
    global _client_unavailable_logged
    if os.environ.get("CREDANTA_FORCE_LOCAL_STORAGE", "").lower() == "true":
        return None
    try:
        from replit.object_storage import Client  # type: ignore
        bucket_id = os.environ.get("DEFAULT_OBJECT_STORAGE_BUCKET_ID") or None
        return Client(bucket_id=bucket_id)
    except Exception as exc:
        if not _client_unavailable_logged:
            logger.warning(
                "[storage_service] Replit Object Storage unavailable (%s). "
                "New uploads will use local filesystem and will NOT persist "
                "across deployments. Connect a Replit bucket for production.",
                exc,
            )
            _client_unavailable_logged = True
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def active_provider() -> str:
    """Return the provider that new uploads will use."""
    return PROVIDER_REPLIT if _get_client() is not None else PROVIDER_LOCAL


def upload_file(user_id: int, file_bytes: bytes, suffix: str) -> tuple[str, int, str]:
    """Store *file_bytes* and return ``(stored_filename, size_bytes, provider)``.

    Generates a cryptographically random filename — the original user-supplied
    name is never used as a storage key.

    Raises:
        Exception: propagated from the storage backend on write failure.
            Callers must catch this and NOT create a Document record.
    """
    safe_suffix = "".join(c for c in suffix if c.isalnum() or c == ".")[-12:]
    if safe_suffix and not safe_suffix.startswith("."):
        safe_suffix = "." + safe_suffix
    name = secrets.token_urlsafe(16) + safe_suffix
    size = len(file_bytes)

    client = _get_client()
    if client is not None:
        key = _object_key(user_id, name)
        client.upload_from_bytes(key, file_bytes)
        logger.info("[storage_service] stored %d bytes → %s", size, key)
        return name, size, PROVIDER_REPLIT

    # Local filesystem fallback
    from ..storage import save_upload as _local_save
    stored_name, stored_size = _local_save(user_id, file_bytes, suffix)
    return stored_name, stored_size, PROVIDER_LOCAL


def download_file(
    user_id: int,
    stored_filename: str,
    provider: Optional[str] = None,
) -> bytes:
    """Return file bytes, routing to the correct backend.

    Falls back to the other backend so files uploaded before migration
    (stored locally with provider="local") continue to work after the
    app switches to object storage for new uploads.

    Raises:
        FileNotFoundError: if the file cannot be found in any backend.
    """
    provider = provider or PROVIDER_LOCAL

    if provider == PROVIDER_REPLIT:
        client = _get_client()
        if client is not None:
            try:
                return client.download_as_bytes(_object_key(user_id, stored_filename))
            except Exception as exc:
                logger.warning(
                    "[storage_service] Object Storage miss for %s/%s (%s) "
                    "— trying local filesystem fallback",
                    user_id, stored_filename, exc,
                )

    # Try local filesystem
    from ..storage import file_path as _local_path
    try:
        p = _local_path(user_id, stored_filename)
        if p.exists():
            return p.read_bytes()
    except Exception:
        pass

    # Last resort: try object storage even if provider says "local"
    # (handles files that were manually migrated without updating the DB)
    if provider == PROVIDER_LOCAL:
        client = _get_client()
        if client is not None:
            try:
                return client.download_as_bytes(_object_key(user_id, stored_filename))
            except Exception:
                pass

    raise FileNotFoundError(
        f"Document file not found: user={user_id} filename={stored_filename}"
    )


def delete_file(
    user_id: int,
    stored_filename: str,
    provider: Optional[str] = None,
) -> None:
    """Delete from the recorded backend — best-effort, never raises."""
    provider = provider or PROVIDER_LOCAL

    if provider == PROVIDER_REPLIT:
        client = _get_client()
        if client is not None:
            try:
                client.delete(_object_key(user_id, stored_filename), ignore_not_found=True)
            except Exception as exc:
                logger.warning("[storage_service] Object Storage delete failed: %s", exc)
        _try_local_delete(user_id, stored_filename)
    else:
        _try_local_delete(user_id, stored_filename)
        # Also purge from object storage in case file was migrated
        client = _get_client()
        if client is not None:
            try:
                client.delete(_object_key(user_id, stored_filename), ignore_not_found=True)
            except Exception:
                pass


def file_exists(
    user_id: int,
    stored_filename: str,
    provider: Optional[str] = None,
) -> bool:
    """Return True if the file is reachable in any backend."""
    provider = provider or PROVIDER_LOCAL

    if provider == PROVIDER_REPLIT:
        client = _get_client()
        if client is not None:
            try:
                if client.exists(_object_key(user_id, stored_filename)):
                    return True
            except Exception:
                pass

    from ..storage import file_path as _local_path
    try:
        return _local_path(user_id, stored_filename).exists()
    except Exception:
        pass

    return False


def _try_local_delete(user_id: int, stored_filename: str) -> None:
    try:
        from ..storage import delete_file as _local_del
        _local_del(user_id, stored_filename)
    except Exception:
        pass
