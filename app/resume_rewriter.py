"""Local rule-based resume rewriter. No external APIs. Preserves all facts."""
import re

_BULLET_CHARS = frozenset("•-*·▪–◦▸▹►")

# ── Tone-specific opener replacement tables ───────────────────────────────────
# Keys are lowercase weak phrases; values replace them at the START of a bullet.

_TONE_OPENERS: dict[str, dict[str, str]] = {
    "professional": {
        "was responsible for": "Managed",
        "responsible for":     "Managed",
        "duties included":     "Performed",
        "duties include":      "Perform",
        "helped with":         "Assisted with",
        "helped to":           "Worked to",
        "helped":              "Assisted",
        "worked on":           "Contributed to",
        "worked with":         "Collaborated with",
        "participated in":     "Collaborated on",
        "assisted with":       "Supported",
        "assisted in":         "Facilitated",
        "assisted":            "Supported",
        "took care of":        "Cared for",
        "was involved in":     "Participated in",
        "was part of":         "Contributed to",
        "was tasked with":     "Managed",
        "did":                 "Performed",
        "provided support for":"Supported",
    },
    "concise": {
        "was responsible for": "Led",
        "responsible for":     "Led",
        "duties included":     "Handled",
        "duties include":      "Handle",
        "helped with":         "Supported",
        "helped to":           "Worked to",
        "helped":              "Supported",
        "worked on":           "Executed",
        "worked with":         "Partnered with",
        "participated in":     "Contributed to",
        "assisted with":       "Supported",
        "assisted in":         "Supported",
        "assisted":            "Supported",
        "took care of":        "Managed",
        "was involved in":     "Contributed to",
        "was part of":         "Supported",
        "was tasked with":     "Led",
        "did":                 "Completed",
        "provided support for":"Supported",
    },
    "impact": {
        "was responsible for": "Owned and led",
        "responsible for":     "Spearheaded",
        "duties included":     "Delivered",
        "duties include":      "Deliver",
        "helped with":         "Improved",
        "helped to":           "Drove",
        "helped":              "Enhanced",
        "worked on":           "Executed",
        "worked with":         "Partnered with",
        "participated in":     "Led",
        "assisted with":       "Contributed to",
        "assisted in":         "Led",
        "assisted":            "Contributed to",
        "took care of":        "Championed",
        "was involved in":     "Led",
        "was part of":         "Drove",
        "was tasked with":     "Owned",
        "did":                 "Delivered",
        "provided support for":"Championed",
    },
    "healthcare": {
        "was responsible for": "Managed",
        "responsible for":     "Provided",
        "duties included":     "Delivered",
        "duties include":      "Deliver",
        "helped with":         "Facilitated",
        "helped to":           "Worked to",
        "helped":              "Assisted",
        "worked on":           "Delivered",
        "worked with":         "Collaborated with",
        "participated in":     "Contributed to",
        "assisted with":       "Facilitated",
        "assisted in":         "Facilitated",
        "assisted":            "Assisted",
        "took care of":        "Provided care for",
        "was involved in":     "Supported",
        "was part of":         "Contributed to",
        "was tasked with":     "Managed",
        "did":                 "Performed",
        "provided support for":"Supported",
    },
}

# Safe healthcare term upgrades (applied to all tones)
_HC_BASIC: list[tuple[str, str]] = [
    (r'\btook\s+vitals\b',          "assessed vital signs"),
    (r'\bvitals\b',                  "vital signs"),
    (r'\bcharted\b',                 "documented"),
    (r'\bcharting\b',                "clinical documentation"),
    (r'\bgave\s+meds\b',             "administered medications"),
    (r'\bgave\s+the\s+meds\b',       "administered medications"),
    (r'\bgave\s+medications\b',      "administered medications"),
    (r'\bpt\b(?=[\s,])',             "patient"),
    (r'\bpts\b(?=[\s,])',            "patients"),
]

# Additional upgrades used only in the healthcare-focused version
_HC_EXTRA: list[tuple[str, str]] = [
    (r'\bmeds\b',                    "medications"),
    (r'\bgave\s+report\b',           "completed handoff communication"),
    (r'\bgave\s+the\s+report\b',     "completed handoff communication"),
    (r'\btook\s+report\b',           "received handoff communication"),
    (r'\bdoctors\b',                 "physicians"),
    (r'\bdoctor\b',                  "physician"),
    (r'\bwound\s+care\b',            "wound care management"),
    (r'\bpain\s+management\b',       "pain assessment and management"),
]

_HC_FULL = _HC_BASIC + _HC_EXTRA

# Filler patterns removed in Concise version
_CONCISE_FILLERS: list[tuple[str, str]] = [
    (r'\bin\s+order\s+to\b',                    "to"),
    (r'\bdue\s+to\s+the\s+fact\s+that\b',        "because"),
    (r'\bon\s+a\s+regular\s+basis\b',            "regularly"),
    (r'\bat\s+this\s+point\s+in\s+time\b',       "currently"),
    (r'\bin\s+a\s+timely\s+manner\b',            "promptly"),
    (r'\ba\s+large\s+number\s+of\b',             "many"),
    (r'\ba\s+number\s+of\b',                     "several"),
    (r'\bon\s+a\s+daily\s+basis\b',              "daily"),
    (r'\bon\s+an\s+ongoing\s+basis\b',           "consistently"),
    (r'\bwas\s+able\s+to\b',                     ""),
    (r'\bin\s+order\s+for\b',                    "for"),
    (r'\bfor\s+the\s+purpose\s+of\b',            "to"),
    (r'\bfrom\s+time\s+to\s+time\b',             "periodically"),
    (r'\bmake\s+a\s+determination\b',            "determine"),
    (r'\bprovide\s+support\s+to\b',              "support"),
    (r'\bprovides\s+support\s+to\b',             "supports"),
]

_SUMMARY_SECTION = re.compile(
    r'\b(summary|professional summary|objective|profile|about me)\b', re.I)

_HEADER_WORDS = {
    "summary", "professional summary", "objective", "profile", "about me",
    "experience", "work experience", "professional experience",
    "employment", "employment history", "work history",
    "education", "educational background",
    "certifications", "certifications & licenses", "certifications and licenses",
    "licenses", "licensure",
    "skills", "core competencies", "technical skills", "key skills",
    "references", "publications", "awards", "achievements",
    "professional development", "volunteer", "affiliations",
    "contact", "contact information", "contact info",
}


# ── Line classification ───────────────────────────────────────────────────────

def _is_bullet(line: str) -> bool:
    s = line.strip()
    return bool(s) and s[0] in _BULLET_CHARS


def _is_header(line: str) -> bool:
    s = line.strip()
    if not s or len(s) > 70:
        return False
    clean = s.rstrip(":").strip()
    if clean.upper() == clean and len(clean) > 2 and not re.search(r'\d{4}', clean):
        return True
    return clean.lower() in _HEADER_WORDS


def _is_date_or_contact(line: str) -> bool:
    s = line.strip()
    if re.search(
        r'\b\d{4}\b|\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\b|present',
        s, re.I
    ):
        return True
    if re.search(r'@|\(\d{3}\)|\d{3}[-.\s]\d{3}[-.\s]\d{4}', s):
        return True
    return False


def _is_separator(line: str) -> bool:
    """Lines that are just dashes, underscores, or pipes — used as dividers."""
    return bool(re.match(r'^[-_=|]{3,}\s*$', line.strip()))


# ── Text transformation helpers ───────────────────────────────────────────────

def _strip_bullet(line: str) -> tuple[str, str]:
    """Returns (indented_prefix_with_char, content)."""
    s = line.lstrip()
    if s and s[0] in _BULLET_CHARS:
        indent = len(line) - len(s)
        return line[:indent] + s[0] + " ", s[1:].lstrip()
    return "", s


def _replace_opener(text: str, replacements: dict) -> str:
    """Replace a weak phrase at the very start of text."""
    t = text.strip()
    tl = t.lower()
    for phrase in sorted(replacements, key=len, reverse=True):
        if tl.startswith(phrase):
            rest = t[len(phrase):]
            return replacements[phrase] + rest
    return text


def _apply_regexes(text: str, patterns: list) -> str:
    for pat, repl in patterns:
        text = re.sub(pat, repl, text, flags=re.I)
    return text


def _clean_double_spaces(text: str) -> str:
    return re.sub(r'  +', ' ', text).strip()


# ── Per-line rewriting ────────────────────────────────────────────────────────

def _rewrite_bullet(line: str, tone: str, hc_terms: list) -> str:
    prefix, content = _strip_bullet(line)
    if not content.strip():
        return line

    # 1. Replace weak opener
    content = _replace_opener(content, _TONE_OPENERS.get(tone, {}))

    # 2. Apply healthcare terms
    if hc_terms:
        content = _apply_regexes(content, hc_terms)

    # 3. Concise: strip filler phrases
    if tone == "concise":
        content = _apply_regexes(content, _CONCISE_FILLERS)

    content = _clean_double_spaces(content)
    return prefix + content


def _rewrite_prose(line: str, tone: str, hc_terms: list) -> str:
    """Rewrite a non-bullet prose line (summary paragraphs, descriptions)."""
    text = line

    # Apply HC terms
    if hc_terms:
        text = _apply_regexes(text, hc_terms)

    # Replace weak phrases anywhere in the line (not just openers)
    for phrase in sorted(_TONE_OPENERS.get(tone, {}), key=len, reverse=True):
        pattern = r'(?<!\w)' + re.escape(phrase) + r'(?!\w)'
        repl = _TONE_OPENERS[tone][phrase]
        # Only replace at sentence starts (capitalised) and after punctuation
        def _replace_if_start(m: re.Match) -> str:
            start = text[:m.start()].rstrip()
            if not start or start[-1] in '.!?,;:\n':
                return repl
            return m.group(0)
        text = re.sub(pattern, _replace_if_start, text, flags=re.I)

    if tone == "concise":
        text = _apply_regexes(text, _CONCISE_FILLERS)

    return _clean_double_spaces(text)


# ── Full document rewriting ───────────────────────────────────────────────────

def _rewrite(lines: list[str], tone: str) -> str:
    hc_terms = _HC_FULL if tone == "healthcare" else _HC_BASIC

    result: list[str] = []
    in_summary = False
    summary_lines_written = 0

    for raw_line in lines:
        # Blank lines: pass through, exit summary mode
        if not raw_line.strip():
            result.append("")
            in_summary = False
            continue

        # Separator lines
        if _is_separator(raw_line):
            result.append(raw_line)
            continue

        # Section headers: preserve, update summary flag
        if _is_header(raw_line):
            result.append(raw_line)
            in_summary = bool(_SUMMARY_SECTION.search(raw_line))
            summary_lines_written = 0
            continue

        # Date/contact lines: preserve exactly
        if _is_date_or_contact(raw_line):
            result.append(raw_line)
            continue

        # Bullet lines: rewrite
        if _is_bullet(raw_line):
            result.append(_rewrite_bullet(raw_line, tone, hc_terms))
            continue

        # Summary paragraph: rewrite gently
        if in_summary:
            rewritten = _rewrite_prose(raw_line, tone, hc_terms)
            # Concise: keep only first 2 sentences of summary
            if tone == "concise" and summary_lines_written >= 2:
                continue
            result.append(rewritten)
            summary_lines_written += 1
            continue

        # Everything else (employer lines, short title lines, misc):
        # Apply HC terms only; don't touch structure
        line = raw_line
        if hc_terms:
            line = _apply_regexes(line, hc_terms)
        if tone == "concise":
            line = _apply_regexes(line, _CONCISE_FILLERS)
        result.append(line)

    # Collapse 3+ consecutive blank lines to 2
    text = "\n".join(result)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# ── Public entry point ────────────────────────────────────────────────────────

def rewrite_resume(text: str, target_role: str = "Travel Nurse") -> dict:
    """
    Generate up to 4 rewritten versions of a resume.
    Preserves all facts — only wording and structure are improved.

    Returns dict with keys: professional, concise, impact, healthcare (if applicable).
    Each value: {title, desc, text}
    """
    lines = text.splitlines()

    is_healthcare = bool(re.search(
        r'\b(nurse|rn|lpn|cna|medical|clinical|patient|icu|er|emergency|hospital|'
        r'healthcare|health\s*care|nursing|clinician|caregiver|aide|therapist|'
        r'travel\s+nurse|registered\s+nurse)\b',
        text, re.I,
    ))
    # Also include healthcare version if the selected role is healthcare
    hc_roles = {"Travel Nurse", "Registered Nurse", "ICU RN", "Telemetry RN",
                 "Med-Surg RN", "Emergency RN", "Home Health RN", "Legal Nurse Consultant"}
    if target_role in hc_roles:
        is_healthcare = True

    versions: dict[str, dict] = {}

    version_defs = [
        ("professional", "Professional",
         "Polished, balanced language suitable for general applications."),
        ("concise",      "Concise",
         "Shorter and tighter — easy for recruiters to scan in seconds."),
        ("impact",       "Impact",
         "Stronger action verbs and confident, results-oriented wording."),
        ("healthcare",   "Healthcare-Focused",
         "Professional clinical language tailored for healthcare and nursing roles."),
    ]

    for tone, title, desc in version_defs:
        if tone == "healthcare" and not is_healthcare:
            continue
        versions[tone] = {
            "title": title,
            "desc":  desc,
            "text":  _rewrite(lines, tone),
        }

    return versions
