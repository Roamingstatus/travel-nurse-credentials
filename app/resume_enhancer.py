"""Resume enhancer — extracts text and returns targeted improvement suggestions."""
import logging
import re

logger = logging.getLogger(__name__)

# ── Nursing-specific knowledge bases ─────────────────────────────────────────

_STRONG_VERBS = {
    "administered", "assessed", "collaborated", "coordinated", "delivered",
    "documented", "educated", "evaluated", "implemented", "initiated",
    "managed", "monitored", "performed", "prioritised", "prioritized",
    "provided", "reduced", "responded", "streamlined", "supervised",
    "trained", "triaged",
}

_WEAK_PHRASES = [
    "responsible for", "duties included", "helped with", "assisted with",
    "worked on", "team player", "detail-oriented", "detail oriented",
    "hardworking", "go-getter", "results-driven", "results driven",
    "self-motivated", "self motivated", "dynamic", "synergy",
    "passionate about", "strong communication",
]

_CERTS = [
    "acls", "bls", "tncc", "cen", "ccrn", "pals", "nrp", "stable",
    "nihss", "enpc", "tcrn", "ocn", "cmsrn", "scrn", "cnor", "rnfa",
    "wocn", "cpan", "capa", "chpn",
]

_EMRS = [
    "epic", "meditech", "cerner", "allscripts", "athenahealth", "eclinicalworks",
    "nextgen", "pointclickcare", "medhost", "healthstream",
]

_SPECIALTIES = [
    "icu", "er", "emergency", "trauma", "surgical", "oncology", "cardiac",
    "telemetry", "stepdown", "step-down", "icu", "nicu", "picu", "l&d",
    "labor and delivery", "pediatric", "paediatric", "or ", "operating room",
    "post-op", "post op", "med-surg", "med surg", "neurology", "neuro",
]

_DATE_PATTERNS = [
    re.compile(r'\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]* \d{4}', re.I),
    re.compile(r'\b\d{1,2}/\d{4}\b'),
    re.compile(r'\b\d{4}\b'),
]


# ── Helpers ──────────────────────────────────────────────────────────────────

def _lower(text: str) -> str:
    return text.lower()


def _find_weak_phrases(text: str) -> list[str]:
    tl = _lower(text)
    return [p for p in _WEAK_PHRASES if p in tl]


def _find_certs(text: str) -> list[str]:
    tl = _lower(text)
    return [c.upper() for c in _CERTS if re.search(r'\b' + re.escape(c) + r'\b', tl)]


def _find_emrs(text: str) -> list[str]:
    tl = _lower(text)
    return [e.title() for e in _EMRS if re.search(r'\b' + re.escape(e) + r'\b', tl)]


def _find_specialties(text: str) -> list[str]:
    tl = _lower(text)
    found = []
    for s in _SPECIALTIES:
        if s in tl:
            found.append(s.upper().strip())
    return list(dict.fromkeys(found))


def _has_metrics(text: str) -> bool:
    return bool(re.search(r'\b\d+\s*(%|patients?|beds?|years?|months?|hours?|shifts?|units?)\b', text, re.I)
                or re.search(r'\d+:\d+', text))


def _leading_verb_ratio(text: str) -> float:
    lines = [l.strip() for l in text.splitlines() if l.strip().startswith(("•", "-", "*", "·"))]
    if not lines:
        lines = [l.strip() for l in text.splitlines()
                 if len(l.strip()) > 20 and l.strip()[0].isupper()]
    if not lines:
        return 1.0
    strong = sum(1 for l in lines
                 if l.lstrip("•-*· ").lower().split()[:1]
                 and l.lstrip("•-*· ").lower().split()[0].rstrip(".,") in _STRONG_VERBS)
    return strong / len(lines)


def _date_formats_used(text: str) -> set[str]:
    formats: set[str] = set()
    if _DATE_PATTERNS[0].search(text):
        formats.add("MMM YYYY")
    if _DATE_PATTERNS[1].search(text):
        formats.add("MM/YYYY")
    if re.search(r'\b(19|20)\d{2}\b', text):
        formats.add("YYYY")
    return formats


def _has_summary_section(text: str) -> bool:
    return bool(re.search(r'(summary|objective|profile|about me)', text, re.I))


def _char_to_pages(n: int) -> float:
    return n / 3000.0


# ── Core analysis ────────────────────────────────────────────────────────────

def _analyse(text: str) -> dict:
    summary_tips: list[str] = []
    bullet_tips: list[str] = []
    formatting_tips: list[str] = []

    tl = _lower(text)

    # ── Summary section ───────────────────────────────────────────────────
    certs = _find_certs(text)
    emrs = _find_emrs(text)
    specialties = _find_specialties(text)

    if not _has_summary_section(text):
        summary_tips.append(
            "Add a short Professional Summary at the top (2–3 sentences). "
            "Lead with your specialty and years of experience, e.g. "
            "'Travel RN with 6+ years in ICU/trauma — ACLS/BLS certified, proficient in Epic and Meditech.'"
        )
    else:
        if not specialties:
            summary_tips.append(
                "Your summary doesn't mention a specific unit or specialty. "
                "Name it clearly — 'NICU', 'ER', 'Cardiac Telemetry', etc. — "
                "so recruiters know immediately where you work best."
            )
        if not re.search(r'\d+\s*(year|yr)', tl):
            summary_tips.append(
                "State your years of experience in the summary "
                "(e.g. '4+ years of experience') — recruiters filter by this instantly."
            )

    if certs:
        summary_tips.append(
            f"Good — your certifications ({', '.join(certs[:5])}) are present. "
            "Make sure each one has its expiry date listed so it matches your Credanta vault."
        )
    else:
        summary_tips.append(
            "No certifications detected (ACLS, BLS, TNCC, CCRN, etc.). "
            "Add a dedicated Certifications section with name and expiry date."
        )

    if emrs:
        summary_tips.append(
            f"EMR systems found: {', '.join(emrs)}. "
            "If you have proficiency ratings (Basic / Intermediate / Advanced), add them."
        )
    else:
        summary_tips.append(
            "No EMR systems mentioned. Recruiters screen heavily for Epic, Meditech, "
            "and Cerner — list every system you've used."
        )

    # ── Bullet points ─────────────────────────────────────────────────────
    weak = _find_weak_phrases(text)
    if weak:
        examples = '", "'.join(weak[:3])
        bullet_tips.append(
            f'Replace passive phrases like "{examples}" with specific action verbs. '
            "E.g. 'Responsible for patient education' → 'Educated patients and families on post-discharge wound care protocols.'"
        )

    verb_ratio = _leading_verb_ratio(text)
    if verb_ratio < 0.5:
        bullet_tips.append(
            "Most of your bullet points don't start with a strong action verb. "
            "Begin each one with: Administered, Assessed, Coordinated, Monitored, "
            "Prioritized, Triaged, Implemented, Educated, Reduced, or Supervised."
        )
    else:
        bullet_tips.append(
            "Good use of action verbs. Make sure every bullet follows the "
            "pattern: [Verb] + [What you did] + [For whom / how many] + [Result]."
        )

    if not _has_metrics(text):
        bullet_tips.append(
            "No numbers or metrics detected anywhere in your resume. Add patient ratios "
            "(e.g. '1:2 nurse-to-patient ratio'), unit size, caseload, or outcome stats. "
            "Numbers make your experience concrete and stand out to hiring managers."
        )
    else:
        bullet_tips.append(
            "Metrics found — keep adding them wherever possible. "
            "Include patient volume, unit bed count, or any measurable outcomes you influenced."
        )

    if specialties:
        bullet_tips.append(
            f"Specialty areas detected: {', '.join(specialties[:4])}. "
            "Tailor each job's bullets to highlight the specific skills and procedures "
            "relevant to that setting."
        )

    # ── Formatting ────────────────────────────────────────────────────────
    date_formats = _date_formats_used(text)
    if len(date_formats) > 1:
        formatting_tips.append(
            f"Inconsistent date formats found ({', '.join(sorted(date_formats))}). "
            "Pick one style and apply it everywhere — 'MMM YYYY' (e.g. Jan 2022) "
            "is the most recruiter-friendly."
        )
    elif date_formats:
        formatting_tips.append(
            f"Date format looks consistent ({', '.join(date_formats)}). "
            "Ensure every position shows both start and end date."
        )
    else:
        formatting_tips.append(
            "No dates detected. Make sure every role has a clear date range "
            "(e.g. 'Jun 2021 – Present') so there are no unexplained gaps."
        )

    est_pages = _char_to_pages(len(text))
    if est_pages > 2.2:
        formatting_tips.append(
            "Your resume appears to be over 2 pages. Travel nurse recruiters prefer "
            "1–2 pages maximum — trim older roles to 1–2 bullets each."
        )
    elif est_pages < 0.4:
        formatting_tips.append(
            "Your resume looks very short. Expand bullet points with specific duties, "
            "patient populations, and measurable outcomes for each role."
        )
    else:
        formatting_tips.append(
            "Length looks good. Use clear section headers (Summary, Experience, "
            "Certifications, Education, Skills) with consistent spacing."
        )

    if not re.search(r'reference|linkedin|phone|\(\d{3}\)', tl):
        formatting_tips.append(
            "Consider adding a LinkedIn profile URL and direct phone number "
            "to the header — travel agencies often call before emailing."
        )

    return {
        "summary": summary_tips,
        "bullets": bullet_tips,
        "formatting": formatting_tips,
        "source": "analysis",
    }


# ── AI path (optional upgrade) ────────────────────────────────────────────────

def _ai_suggestions(text_sample: str) -> dict | None:
    try:
        import os
        import openai
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            return None
        client = openai.OpenAI(api_key=api_key)
        prompt = (
            "You are a professional resume coach for healthcare travel nurses. "
            "Review the following resume text and return a JSON object with three keys: "
            "'summary' (list of 2-3 improvement suggestions for the professional summary), "
            "'bullets' (list of 2-4 bullet-point improvement tips), "
            "'formatting' (list of 1-3 formatting tips). "
            "Be specific to the content provided. Output only valid JSON.\n\n"
            f"Resume text:\n{text_sample[:3000]}"
        )
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=600,
            response_format={"type": "json_object"},
        )
        import json
        return json.loads(response.choices[0].message.content)
    except Exception as exc:
        logger.warning(f"[ResumeEnhancer] AI call failed: {exc}")
        return None


# ── Public entry point ────────────────────────────────────────────────────────

def _extract_text_from_bytes(raw: bytes, mime_type: str, filename: str) -> str:
    try:
        from .smart_categorize import _extract_text
        return _extract_text(raw, mime_type, filename)
    except Exception:
        return ""


def enhance_resume(raw: bytes, mime_type: str, filename: str) -> dict:
    text = _extract_text_from_bytes(raw, mime_type, filename)
    text_ok = bool(text and len(text.strip()) > 50)

    if text_ok:
        ai_result = _ai_suggestions(text)
        if ai_result and isinstance(ai_result, dict):
            suggestions = {
                "summary": ai_result.get("summary", []),
                "bullets": ai_result.get("bullets", []),
                "formatting": ai_result.get("formatting", []),
                "source": "ai",
            }
        else:
            suggestions = _analyse(text)
    else:
        logger.info("[ResumeEnhancer] Could not extract text — returning generic suggestions.")
        from copy import deepcopy
        suggestions = {
            "summary": [
                "Lead with your specialisation and years of experience.",
                "Quantify impact where possible ('Maintained <2% CLABSI rate across 24-bed unit').",
                "Trim filler phrases like 'detail-oriented' — show, don't tell.",
            ],
            "bullets": [
                "Start every bullet with a strong action verb: Administered, Coordinated, Triaged.",
                "Add patient/case volume or outcome metrics to each role.",
                "Mention specific equipment, EMRs, or protocols (Epic, Meditech, ACLS, TNCC).",
            ],
            "formatting": [
                "Use consistent date format throughout (MMM YYYY).",
                "Keep to 1–2 pages.",
                "List certifications with expiry dates.",
            ],
            "source": "template",
        }

    suggestions["text_extracted"] = text_ok
    suggestions["char_count"] = len(text)
    return suggestions
