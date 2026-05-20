import io
import zipfile
from datetime import datetime

from .db import Document, User
from .storage import file_path


def _safe(name: str) -> str:
    keep = "-_. "
    return "".join(c if c.isalnum() or c in keep else "_" for c in name).strip() or "file"


def build_zip(user: User, documents: list[Document]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        manifest_lines = [
            f"Credanta packet for {user.name or user.email}",
            f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
            f"Email: {user.email}",
            "",
            f"Documents ({len(documents)}):",
            "-" * 60,
        ]
        for d in documents:
            exp = d.expires_at.strftime("%Y-%m-%d") if d.expires_at else "—"
            iss = d.issued_at.strftime("%Y-%m-%d") if d.issued_at else "—"
            manifest_lines.append(
                f"[{d.category}] {d.title}\n  Issued: {iss}  Expires: {exp}\n  File: {d.original_filename}\n"
            )
            try:
                src = file_path(user.id, d.stored_filename)
                if src.exists():
                    folder = _safe(d.category)
                    fname = f"{_safe(d.title)}__{_safe(d.original_filename)}"
                    zf.writestr(f"{folder}/{fname}", src.read_bytes())
            except Exception:
                continue

        zf.writestr("MANIFEST.txt", "\n".join(manifest_lines))
    return buf.getvalue()
