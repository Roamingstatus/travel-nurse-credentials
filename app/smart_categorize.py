"""Lightweight heuristics (no external API). Premium tier can swap in real AI parsing."""

import io
import re
from datetime import datetime
from pathlib import Path

# Keywords → category (first match wins; order matters)
_LICENSE_CERT_KEYS = (
    "license",
    "licence",
    "permit",
    "registration",
    "bar exam",
    "cpa",
    "notary",
    "certification",
    "certificate",
    "credential",
    "exam result",
    "pmp",
    "aws",
    "google cloud",
    "bls",
    "acls",
    "pals",
    "nrp",
    "tncc",
    "cpr",
)

_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("Identity", ("passport", "drivers", "driver", "driver's", "license id", "state id", "ssn", "social security", "national id", "birth certificate", "government id")),
    ("Licenses & Certifications", _LICENSE_CERT_KEYS),
    ("Health & Compliance", ("vaccin", "immuniz", "tb ", "ppd", "drug screen", "physical exam", "osha", "hipaa", "compliance", "titer", "flu shot", "covid", "hepatitis", "varicella", "mmr", "background check")),
    ("Education", ("diploma", "transcript", "degree", "university", "college", "ged", "training completion")),
]


def infer_category(filename: str, title: str) -> str:
    blob = f"{filename} {title}".lower()
    for cat, keys in _RULES:
        if any(k in blob for k in keys):
            return cat
    return "Other"


# --- Date extraction ---

_MONTH_MAP = {
    'january': 1, 'february': 2, 'march': 3, 'april': 4,
    'may': 5, 'june': 6, 'july': 7, 'august': 8,
    'september': 9, 'october': 10, 'november': 11, 'december': 12,
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'jun': 6,
    'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
}

_MONTH_RE = r'(?:january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)'

_DATE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'\b(\d{1,2})[/\-](\d{1,2})[/\-](20\d{2})\b'), 'mdy'),
    (re.compile(r'\b(20\d{2})[-/](\d{2})[-/](\d{2})\b'), 'ymd'),
    (re.compile(rf'\b({_MONTH_RE})[,.\s]+(\d{{1,2}})[,.\s]+(20\d{{2}})\b', re.IGNORECASE), 'mname_d_y'),
    (re.compile(rf'\b(\d{{1,2}})[,.\s]+({_MONTH_RE})[,.\s]+(20\d{{2}})\b', re.IGNORECASE), 'd_mname_y'),
]

_EXPIRY_CTX = re.compile(
    r'(expir|valid\s+(?:through|until|thru)|renew|not\s+valid\s+after|void\s+after|good\s+(?:through|until)|use\s+by)',
    re.IGNORECASE,
)
_ISSUE_CTX = re.compile(
    r'(issued?|date\s+of\s+issue|effective|valid\s+from|start\s+date|date\s+issued)',
    re.IGNORECASE,
)


def _parse_date_match(m: re.Match, ptype: str) -> datetime | None:
    try:
        if ptype == 'mdy':
            mo, d, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        elif ptype == 'ymd':
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        elif ptype == 'mname_d_y':
            mo = _MONTH_MAP.get(m.group(1).lower())
            d, y = int(m.group(2)), int(m.group(3))
        elif ptype == 'd_mname_y':
            d = int(m.group(1))
            mo = _MONTH_MAP.get(m.group(2).lower())
            y = int(m.group(3))
        else:
            return None
        if mo and 1 <= mo <= 12 and 1 <= d <= 31 and 2000 <= y <= 2050:
            return datetime(y, mo, d)
    except (ValueError, TypeError):
        pass
    return None


def _extract_dates_from_text(text: str) -> tuple[datetime | None, datetime | None]:
    issued: datetime | None = None
    expires: datetime | None = None
    now = datetime.now()

    for pat, ptype in _DATE_PATTERNS:
        for m in pat.finditer(text):
            dt = _parse_date_match(m, ptype)
            if not dt:
                continue
            context = text[max(0, m.start() - 120): m.start()].lower()
            if _EXPIRY_CTX.search(context):
                if expires is None:
                    expires = dt
            elif _ISSUE_CTX.search(context):
                if issued is None:
                    issued = dt
            else:
                if dt > now and expires is None:
                    expires = dt
                elif dt <= now and issued is None:
                    issued = dt

    return issued, expires


_DATE_PATTERNS_SIMPLE = (re.compile(r"(20\d{2})[-/](\d{2})[-/](\d{2})"),)


def infer_expiry_from_text(filename: str, title: str) -> datetime | None:
    """Best-effort date from filename/title (YYYY-MM-DD style)."""
    text = f"{filename} {title}"
    for pat in _DATE_PATTERNS_SIMPLE:
        m = pat.search(text)
        if not m:
            continue
        try:
            if m.lastindex == 3 and len(m.group(1)) == 4:
                y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
                return datetime(y, mo, d)
        except ValueError:
            continue
    return None


# --- Text extraction ---

def _extract_text(raw: bytes, mime_type: str, filename: str) -> str:
    mt = (mime_type or '').lower()
    fn = (filename or '').lower()
    if mt.startswith('text/') or fn.endswith(('.txt', '.csv', '.md')):
        try:
            return raw.decode('utf-8', errors='ignore')[:15000]
        except Exception:
            return ''
    if mt == 'application/pdf' or fn.endswith('.pdf'):
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(raw))
            parts: list[str] = []
            for page in reader.pages[:8]:
                try:
                    parts.append(page.extract_text() or '')
                except Exception:
                    pass
            return '\n'.join(parts)[:15000]
        except Exception:
            return ''
    return ''


def _extract_pdf_title(raw: bytes, mime_type: str, filename: str) -> str | None:
    mt = (mime_type or '').lower()
    fn = (filename or '').lower()
    if mt == 'application/pdf' or fn.endswith('.pdf'):
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(raw))
            info = reader.metadata
            if info and hasattr(info, 'title') and info.title:
                t = str(info.title).strip()
                if 3 < len(t) < 200 and not t.startswith('%'):
                    return t
        except Exception:
            pass
    return None


def _clean_filename_as_title(filename: str) -> str:
    stem = Path(filename).stem
    stem = re.sub(r'[_\-\.]+', ' ', stem)
    stem = re.sub(r'^\d+\s*', '', stem)
    stem = stem.strip()
    return stem.title() if stem else ''


# --- Main entry point ---

def extract_document_metadata(raw: bytes, mime_type: str, filename: str) -> dict:
    """
    Extract title, category, issued_at, expires_at from document content.
    Returns dict with string dates (YYYY-MM-DD) or None values.
    """
    text = _extract_text(raw, mime_type, filename)

    title = _extract_pdf_title(raw, mime_type, filename)
    if not title:
        title = _clean_filename_as_title(filename) or None

    category = infer_category(filename, title or '')
    if category == 'Other' and text:
        category = infer_category('', text[:1000])

    issued_at, expires_at = _extract_dates_from_text(text) if text else (None, None)

    if not expires_at:
        expires_at = infer_expiry_from_text(filename, title or '')

    return {
        'title': title,
        'category': category if category != 'Other' else None,
        'issued_at': issued_at.strftime('%Y-%m-%d') if issued_at else None,
        'expires_at': expires_at.strftime('%Y-%m-%d') if expires_at else None,
    }
