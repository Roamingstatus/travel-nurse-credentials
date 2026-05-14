"""Optional AI-assisted classification and expiry extraction (OpenAI-compatible API).

Without OPENAI_API_KEY, callers fall back to keyword heuristics in smart_categorize."""

from __future__ import annotations

import io
import json
import os
import urllib.error
import urllib.request
from datetime import datetime

from .categories import CREDENTIAL_CATEGORIES

_ALLOWED = set(CREDENTIAL_CATEGORIES)


def extract_text_sample(raw: bytes, mime_type: str | None, filename: str, max_chars: int = 12000) -> str:
    """Pull readable text from PDF or plain text uploads for AI context."""
    mt = (mime_type or "").lower()
    fn = (filename or "").lower()
    if mt.startswith("text/") or fn.endswith((".txt", ".csv", ".md")):
        try:
            return raw.decode("utf-8", errors="ignore")[:max_chars]
        except Exception:
            return ""
    if mt == "application/pdf" or fn.endswith(".pdf"):
        try:
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(raw))
            parts: list[str] = []
            for page in reader.pages[:10]:
                try:
                    t = page.extract_text() or ""
                except Exception:
                    t = ""
                parts.append(t)
            return "\n".join(parts)[:max_chars]
        except Exception:
            return ""
    return ""


def _parse_iso_date(s: str | None) -> datetime | None:
    if not s or not isinstance(s, str):
        return None
    s = s.strip().replace("Z", "").replace("z", "")
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%m/%d/%Y"):
        try:
            if fmt.startswith("%Y-%m-%d") and len(s) >= 10:
                return datetime.strptime(s[:10], "%Y-%m-%d")
            return datetime.strptime(s[:19], fmt)
        except ValueError:
            continue
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d")
    except ValueError:
        return None


def ai_refine_category_expiry(
    filename: str,
    title: str,
    text_sample: str,
    heuristic_category: str,
    heuristic_expires_at: datetime | None,
) -> tuple[str | None, datetime | None]:
    """
    Returns optional category override (high confidence only) and optional expiry date from document text.
    Requires OPENAI_API_KEY.
    """
    key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not key:
        return None, None

    allowed_list = ", ".join(sorted(_ALLOWED))
    blob = f"""Filename: {filename}
Title: {title}
Heuristic category: {heuristic_category}
Heuristic expiry (if any): {heuristic_expires_at.isoformat() if heuristic_expires_at else "unknown"}

Document text (excerpt):
{text_sample[:8000]}
"""
    sys_prompt = (
        "You classify credential documents. Respond ONLY with compact JSON: "
        '{"category":"<one of the allowed values>","expires_iso":"YYYY-MM-DD or null",'
        '"confidence":"high|low"}'
        f" Allowed categories: {allowed_list}. "
        "Use expires_iso only when a clear expiration or renewal date appears in the text. "
        "Set confidence to high only when category is obvious from the excerpt."
    )

    payload = {
        "model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        "temperature": 0.1,
        "messages": [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": blob},
        ],
        "response_format": {"type": "json_object"},
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, ValueError):
        return None, None

    try:
        content = raw["choices"][0]["message"]["content"]
        data = json.loads(content)
    except (KeyError, IndexError, json.JSONDecodeError, TypeError):
        return None, None

    conf = (data.get("confidence") or "").lower()
    cat = data.get("category")
    out_cat = cat if (isinstance(cat, str) and cat in _ALLOWED and conf == "high") else None

    exp_s = data.get("expires_iso")
    exp = _parse_iso_date(exp_s) if isinstance(exp_s, str) else None
    return out_cat, exp


def ai_enabled() -> bool:
    return bool((os.environ.get("OPENAI_API_KEY") or "").strip())
