import secrets
from pathlib import Path

UPLOAD_DIR = Path(__file__).parent / "uploads"
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
    return user_dir(user_id) / stored_filename


def delete_file(user_id: int, stored_filename: str) -> None:
    p = file_path(user_id, stored_filename)
    if p.exists():
        p.unlink()
