"""Persistent local upload storage for Credanta (Railway Volume / dev filesystem).

All user document bytes live under CREDANTA_UPLOAD_DIR (default /data/uploads).
Layout:  {root}/{user_id}/{uuid}{suffix}

Files are never served directly from this path — routes enforce auth + ownership.
"""
from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path

logger = logging.getLogger("credanta.storage")

DEFAULT_UPLOAD_DIR = Path("/data/uploads")
LEGACY_UPLOAD_DIR = Path(__file__).parent / "uploads"

_upload_root: Path | None = None


def get_upload_directory() -> Path:
    """Return the configured upload root, creating it if missing."""
    global _upload_root
    if _upload_root is None:
        raw = os.environ.get("CREDANTA_UPLOAD_DIR", "").strip()
        _upload_root = Path(raw) if raw else DEFAULT_UPLOAD_DIR
    return _upload_root


def _legacy_upload_directory() -> Path:
    """Pre-volume local uploads (app/uploads) — read-only fallback for migration."""
    return LEGACY_UPLOAD_DIR


def ensure_upload_storage_ready(*, require_writable: bool = False) -> Path:
    """Create upload root and verify writability. Never logs file contents."""
    root = get_upload_directory()
    root.mkdir(parents=True, exist_ok=True)
    (root / "feedback").mkdir(parents=True, exist_ok=True)
    if require_writable:
        probe = root / ".storage_probe"
        try:
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
        except OSError as exc:
            raise RuntimeError(f"Upload directory is not writable: {root}") from exc
    return root


def user_dir(user_id: int) -> Path:
    p = get_upload_directory() / str(user_id)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _safe_suffix(suffix: str) -> str:
    safe = "".join(c for c in (suffix or "") if c.isalnum() or c == ".")[-12:]
    if safe and not safe.startswith("."):
        safe = "." + safe
    return safe


def _safe_stored_name(stored_filename: str) -> str:
    return Path(stored_filename).name


def save_upload(user_id: int, file_bytes: bytes, suffix: str) -> tuple[str, int]:
    """Write *file_bytes* under the user's directory. Returns (stored_name, size)."""
    safe_suffix = _safe_suffix(suffix)
    name = f"{uuid.uuid4().hex}{safe_suffix}"
    path = user_dir(user_id) / name
    path.write_bytes(file_bytes)
    logger.info("[storage] saved user_id=%s bytes=%d", user_id, len(file_bytes))
    return name, len(file_bytes)


def file_path(user_id: int, stored_filename: str) -> Path:
    """Resolved path for a stored file with path-traversal protection."""
    base = user_dir(user_id)
    safe_name = _safe_stored_name(stored_filename)
    target = (base / safe_name).resolve()
    base_resolved = base.resolve()
    if not str(target).startswith(str(base_resolved)):
        logger.error(
            "[storage] Path traversal blocked: user_id=%s filename=%r",
            user_id,
            stored_filename,
        )
        raise ValueError(f"Unsafe stored filename: {stored_filename!r}")
    return target


def _legacy_file_path(user_id: int, stored_filename: str) -> Path | None:
    """Return legacy app/uploads path if it exists (pre-volume migration)."""
    base = _legacy_upload_directory() / str(user_id)
    safe_name = _safe_stored_name(stored_filename)
    target = (base / safe_name).resolve()
    try:
        base_resolved = base.resolve()
    except FileNotFoundError:
        return None
    if not str(target).startswith(str(base_resolved)):
        return None
    return target if target.exists() else None


def resolve_upload_path(user_id: int, stored_filename: str) -> Path:
    """Find file on volume or legacy local path. Raises FileNotFoundError."""
    primary = file_path(user_id, stored_filename)
    if primary.exists():
        return primary
    legacy = _legacy_file_path(user_id, stored_filename)
    if legacy is not None:
        return legacy
    raise FileNotFoundError(
        f"Upload not found: user={user_id} filename={_safe_stored_name(stored_filename)}"
    )


def verify_upload_ownership(user_id: int, stored_filename: str) -> bool:
    """True if *stored_filename* resolves under *user_id*'s storage tree."""
    try:
        resolve_upload_path(user_id, stored_filename)
        return True
    except (ValueError, FileNotFoundError):
        return False


def delete_upload(user_id: int, stored_filename: str) -> None:
    """Delete from volume and legacy paths — best effort, never raises."""
    for resolver in (
        lambda: file_path(user_id, stored_filename),
        lambda: _legacy_file_path(user_id, stored_filename),
    ):
        try:
            p = resolver()
            if p is not None and p.exists():
                p.unlink()
        except (ValueError, OSError):
            pass


# Backward-compatible alias used elsewhere in the codebase
delete_file = delete_upload


# Backward-compatible alias — prefer get_upload_directory()
def __getattr__(name: str):
    if name == "UPLOAD_DIR":
        return get_upload_directory()
    raise AttributeError(name)
