import logging
import os
import secrets
from pathlib import Path

logger = logging.getLogger("credanta.storage")

UPLOAD_DIR = Path(os.environ.get("CREDANTA_UPLOAD_DIR", Path(__file__).parent / "uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def user_dir(user_id: int) -> Path:
    p = UPLOAD_DIR / str(user_id)
    p.mkdir(parents=True, exist_ok=True)
    return p


def save_upload(user_id: int, file_bytes: bytes, suffix: str) -> tuple[str, int]:
    safe_suffix = "".join(c for c in suffix if c.isalnum() or c == ".")[-12:]
    if not safe_suffix.startswith("."):
        safe_suffix = "." + safe_suffix if safe_suffix else ""
    name = secrets.token_urlsafe(16) + safe_suffix
    path = user_dir(user_id) / name
    path.write_bytes(file_bytes)
    return name, len(file_bytes)


def file_path(user_id: int, stored_filename: str) -> Path:
    """Return the filesystem path for a stored file.

    Uses only the *basename* of stored_filename so any path separators
    embedded in the value cannot escape the user's directory.
    """
    base = user_dir(user_id)
    # Strip directory components — stored_filename should already be a bare
    # token, but we enforce this as a path-traversal defence-in-depth measure.
    safe_name = Path(stored_filename).name
    target = (base / safe_name).resolve()
    base_resolved = base.resolve()
    if not str(target).startswith(str(base_resolved)):
        logger.error(
            "[storage] Path traversal blocked: user_id=%s filename=%r",
            user_id, stored_filename,
        )
        raise ValueError(f"Unsafe stored filename: {stored_filename!r}")
    return target


def delete_file(user_id: int, stored_filename: str) -> None:
    p = file_path(user_id, stored_filename)
    if p.exists():
        p.unlink()
