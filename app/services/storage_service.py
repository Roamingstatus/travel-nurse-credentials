"""
Volume-backed storage adapter for Credanta document uploads.

Production (Railway): files on a mounted volume at CREDANTA_UPLOAD_DIR (/data/uploads).
Development: same API, typically app/uploads via env override.

Legacy records with storage_provider="replit_object_storage" are read from the
local volume or app/uploads fallback — Replit SDK removed; run migration script
if files only exist in a former Replit bucket.
"""
from __future__ import annotations

import logging
from typing import Optional

from ..storage import (
    delete_upload,
    resolve_upload_path,
    save_upload,
    verify_upload_ownership,
)

logger = logging.getLogger("credanta.storage_service")

PROVIDER_LOCAL = "local"
# Kept for DB rows created before Railway volume migration; reads use local paths only.
PROVIDER_REPLIT = "replit_object_storage"


def active_provider() -> str:
    return PROVIDER_LOCAL


def upload_file(user_id: int, file_bytes: bytes, suffix: str) -> tuple[str, int, str]:
    """Store file on the configured volume. Returns (stored_filename, size, provider)."""
    stored_name, stored_size = save_upload(user_id, file_bytes, suffix)
    return stored_name, stored_size, PROVIDER_LOCAL


def download_file(
    user_id: int,
    stored_filename: str,
    provider: Optional[str] = None,
) -> bytes:
    """Return file bytes from volume (or legacy app/uploads fallback)."""
    _ = provider  # provider column retained for legacy rows; path is always local now
    path = resolve_upload_path(user_id, stored_filename)
    return path.read_bytes()


def delete_file(
    user_id: int,
    stored_filename: str,
    provider: Optional[str] = None,
) -> None:
    _ = provider
    delete_upload(user_id, stored_filename)


def file_exists(
    user_id: int,
    stored_filename: str,
    provider: Optional[str] = None,
) -> bool:
    _ = provider
    return verify_upload_ownership(user_id, stored_filename)
