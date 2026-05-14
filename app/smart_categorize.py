"""Lightweight heuristics (no external API). Premium tier can swap in real AI parsing."""

import re
from datetime import datetime

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
)

_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("Identity", ("passport", "drivers", "driver", "driver's", "license id", "state id", "ssn", "social security", "national id", "birth certificate", "government id")),
    ("Licenses & Certifications", _LICENSE_CERT_KEYS),
    ("Health & Compliance", ("vaccin", "immuniz", "tb ", "ppd", "drug screen", "physical exam", "osha", "hipaa", "compliance", "titer", "flu shot", "covid")),
    ("Education", ("diploma", "transcript", "degree", "university", "college", "ged", "training completion")),
]


def infer_category(filename: str, title: str) -> str:
    blob = f"{filename} {title}".lower()
    for cat, keys in _RULES:
        if any(k in blob for k in keys):
            return cat
    return "Other"


_DATE_PATTERNS = (re.compile(r"(20\d{2})[-/](\d{2})[-/](\d{2})"),)


def infer_expiry_from_text(filename: str, title: str) -> datetime | None:
    """Best-effort date from filename/title (YYYY-MM-DD style)."""
    text = f"{filename} {title}"
    for pat in _DATE_PATTERNS:
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
