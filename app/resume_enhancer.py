"""Resume enhancer — rule-based analysis engine. No external AI APIs."""
import json
import logging
import re
from copy import deepcopy

logger = logging.getLogger(__name__)

# ── Role keyword libraries ────────────────────────────────────────────────────

ROLE_KEYWORDS: dict[str, list[str]] = {
    "Travel Nurse": [
        "travel nurse", "travel nursing", "compact license", "multi-state",
        "agency", "13-week", "crisis staffing", "float pool", "adaptable",
        "acls", "bls", "epic", "meditech", "cerner", "icu", "er", "med-surg",
        "telemetry", "discharge planning", "patient education", "iv therapy",
        "wound care", "medication administration",
    ],
    "Registered Nurse": [
        "patient care", "nursing assessment", "care planning", "nclex",
        "medication administration", "patient safety", "quality improvement",
        "documentation", "acls", "bls", "epic", "ehr", "patient education",
        "infection control", "iv therapy", "wound care", "discharge planning",
        "interdisciplinary", "evidence-based", "critical thinking",
    ],
    "ICU RN": [
        "intensive care", "critical care", "icu", "ventilator management",
        "crrt", "hemodynamic monitoring", "vasopressors", "ccrn", "arterial line",
        "central line", "swan-ganz", "sepsis protocol", "rapid response",
        "acls", "bls", "sedation protocol", "mechanical ventilation",
        "multi-organ failure", "critical assessment", "titration",
    ],
    "Telemetry RN": [
        "telemetry", "cardiac monitoring", "ekg", "arrhythmia", "dysrhythmia",
        "rhythm interpretation", "acls", "defibrillation", "cardiac drips",
        "holter", "12-lead", "atrial fibrillation", "pacemaker", "cardiac arrest",
        "telemetry unit", "step-down", "anti-arrhythmic",
    ],
    "Med-Surg RN": [
        "medical-surgical", "med-surg", "post-operative", "wound care",
        "discharge planning", "case management", "patient education",
        "medication administration", "iv therapy", "acls", "bls",
        "epic", "pain management", "fall prevention", "sepsis screening",
        "interdisciplinary team", "charge nurse",
    ],
    "Emergency RN": [
        "emergency", "emergency department", "triage", "trauma", "tncc",
        "cen", "acls", "pals", "high acuity", "rapid assessment", "er",
        "mass casualty", "airway management", "shock", "resuscitation",
        "bls", "stroke protocol", "chest pain", "sepsis",
    ],
    "Home Health RN": [
        "home health", "community nursing", "patient education",
        "chronic disease management", "wound care", "iv therapy", "oasis",
        "homebound", "case management", "medication management",
        "fall prevention", "skilled nursing", "care coordination",
        "episode of care", "outcome measures",
    ],
    "Legal Nurse Consultant": [
        "legal nurse", "medical records review", "litigation support",
        "expert witness", "case analysis", "medical-legal", "nurse consultant",
        "standard of care", "malpractice", "personal injury", "depositions",
        "legal terminology", "causation analysis", "healthcare law",
        "regulatory compliance",
    ],
    "Software Developer": [
        "git", "agile", "scrum", "api", "rest", "database", "sql",
        "testing", "code review", "ci/cd", "docker", "cloud", "aws",
        "microservices", "python", "javascript", "typescript",
        "object-oriented", "version control", "deployment",
    ],
    "Teacher": [
        "curriculum", "lesson planning", "classroom management", "assessment",
        "differentiated instruction", "student engagement", "rubric",
        "standards-based", "formative assessment", "summative assessment",
        "iep", "parent communication", "professional development",
        "data-driven instruction", "collaborative learning",
    ],
    "General Professional": [
        "project management", "communication", "leadership", "team",
        "problem-solving", "stakeholder", "budget", "strategic planning",
        "cross-functional", "data analysis", "presentation", "microsoft office",
        "time management", "collaboration", "process improvement",
    ],
}

TARGET_ROLES = list(ROLE_KEYWORDS.keys())
TONES = ["Professional", "Concise", "Healthcare Focused", "Leadership Focused", "Entry Level"]

# ── Weak phrase replacements ──────────────────────────────────────────────────

WEAK_REPLACEMENTS: list[dict] = [
    {"found": "responsible for",  "suggestions": ["Managed", "Oversaw", "Led", "Coordinated"]},
    {"found": "duties included",  "suggestions": ["Delivered", "Executed", "Performed"]},
    {"found": "helped with",      "suggestions": ["Supported", "Assisted", "Improved", "Contributed to"]},
    {"found": "helped",           "suggestions": ["Assisted", "Supported", "Facilitated"]},
    {"found": "worked on",        "suggestions": ["Developed", "Managed", "Executed", "Delivered"]},
    {"found": "worked with",      "suggestions": ["Collaborated with", "Partnered with", "Coordinated with"]},
    {"found": "participated in",  "suggestions": ["Contributed to", "Collaborated on", "Coordinated"]},
    {"found": "assisted with",    "suggestions": ["Supported", "Facilitated", "Contributed to"]},
    {"found": "assisted in",      "suggestions": ["Supported", "Coordinated", "Facilitated"]},
    {"found": "team player",      "suggestions": ["Collaborated across teams", "Cross-functional contributor"]},
    {"found": "detail-oriented",  "suggestions": ["Ensured accuracy in", "Maintained compliance with"]},
    {"found": "detail oriented",  "suggestions": ["Ensured accuracy in", "Maintained compliance with"]},
    {"found": "hardworking",      "suggestions": ["Consistently delivered", "Maintained high performance"]},
    {"found": "passionate about", "suggestions": ["Committed to", "Dedicated to", "Specialised in"]},
    {"found": "results-driven",   "suggestions": ["Achieved measurable outcomes in", "Delivered results for"]},
    {"found": "results driven",   "suggestions": ["Achieved measurable outcomes in", "Delivered results for"]},
    {"found": "self-motivated",   "suggestions": ["Independently managed", "Proactively led"]},
    {"found": "strong communication", "suggestions": ["Communicated effectively with", "Presented to"]},
    {"found": "go-getter",        "suggestions": ["Proactively initiated", "Drove improvements in"]},
]

_STRONG_VERBS = {
    "administered", "assessed", "built", "collaborated", "communicated",
    "completed", "conducted", "coordinated", "created", "delivered",
    "designed", "developed", "documented", "educated", "ensured",
    "evaluated", "executed", "facilitated", "identified", "implemented",
    "improved", "initiated", "led", "maintained", "managed", "monitored",
    "optimised", "optimized", "performed", "planned", "prioritised",
    "prioritized", "provided", "reduced", "resolved", "responded",
    "reviewed", "spearheaded", "streamlined", "supervised", "supported",
    "trained", "triaged", "utilized", "verified",
}

_SECTION_PATTERNS = {
    "Contact Information": re.compile(r'\b(email|phone|linkedin|address|@|\(\d{3}\))\b', re.I),
    "Summary":             re.compile(r'\b(summary|objective|profile|about me|professional summary)\b', re.I),
    "Work Experience":     re.compile(r'\b(experience|employment|work history|professional experience|positions held)\b', re.I),
    "Education":           re.compile(r'\b(education|degree|university|college|bachelor|master|diploma|graduated)\b', re.I),
    "Certifications":      re.compile(r'\b(certif|acls|bls|tncc|ccrn|cen|pals|nrp|license|licensure)\b', re.I),
    "Licenses":            re.compile(r'\b(licen[sc]|rn license|compact|state license|nursing license)\b', re.I),
    "Skills":              re.compile(r'\b(skills|competencies|proficiencies|technologies|tools|software)\b', re.I),
}


# ── Text helpers ──────────────────────────────────────────────────────────────

def _extract_text_from_bytes(raw: bytes, mime_type: str, filename: str) -> str:
    try:
        from .smart_categorize import _extract_text
        return _extract_text(raw, mime_type, filename)
    except Exception as exc:
        logger.warning("[resume_enhancer] Text extraction failed for %r: %s", filename, exc)
        return ""


def _lower(text: str) -> str:
    return text.lower()


def _detect_sections(text: str) -> tuple[list[str], list[str]]:
    found, missing = [], []
    for section, pattern in _SECTION_PATTERNS.items():
        if pattern.search(text):
            found.append(section)
        else:
            missing.append(section)
    return found, missing


def _detect_weak_words(text: str) -> list[dict]:
    tl = _lower(text)
    hits = []
    for entry in WEAK_REPLACEMENTS:
        if entry["found"] in tl:
            hits.append(entry)
    return hits


def _leading_verb_bullets(text: str) -> tuple[int, int]:
    """Returns (strong_count, total_bullet_count)."""
    lines = [l.strip() for l in text.splitlines()
             if l.strip() and l.strip()[0] in "•-*·▪–"]
    if not lines:
        lines = [l.strip() for l in text.splitlines()
                 if len(l.strip()) > 20 and l.strip()[0].isupper()
                 and not l.strip().endswith(":")]
    total = len(lines)
    strong = sum(1 for l in lines
                 if l.lstrip("•-*·▪– ").lower().split()[:1]
                 and l.lstrip("•-*·▪– ").lower().split()[0].rstrip(".,;") in _STRONG_VERBS)
    return strong, total


def _has_metrics(text: str) -> bool:
    return bool(
        re.search(r'\b\d+\s*(%|patients?|beds?|years?|months?|hours?|shifts?|units?)\b', text, re.I)
        or re.search(r'\d+:\d+', text)
        or re.search(r'\$[\d,]+', text)
    )


def _date_formats(text: str) -> set[str]:
    fmts: set[str] = set()
    if re.search(r'\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]* \d{4}', text, re.I):
        fmts.add("MMM YYYY")
    if re.search(r'\b\d{1,2}/\d{4}\b', text):
        fmts.add("MM/YYYY")
    if re.search(r'\b\d{1,2}/\d{1,2}/\d{2,4}\b', text):
        fmts.add("MM/DD/YYYY")
    return fmts


def _long_paragraphs(text: str) -> int:
    """Count paragraphs over 300 chars."""
    return sum(1 for p in re.split(r'\n{2,}', text) if len(p.strip()) > 300)


def _repeated_phrases(text: str) -> list[str]:
    words = re.findall(r'\b[a-z]{4,}\b', _lower(text))
    from collections import Counter
    counts = Counter(words)
    common_filler = {"with", "that", "have", "this", "from", "they", "will", "been", "were",
                     "their", "your", "more", "also", "about", "which", "when", "able",
                     "each", "work", "team", "care", "nursing", "patient", "patients"}
    return [w for w, c in counts.most_common(20) if c >= 4 and w not in common_filler]


def _keyword_match(text: str, role: str) -> tuple[list[str], list[str], int]:
    tl = _lower(text)
    keywords = ROLE_KEYWORDS.get(role, ROLE_KEYWORDS["General Professional"])
    found = [k for k in keywords if k.lower() in tl]
    missing = [k for k in keywords if k.lower() not in tl]
    pct = round(len(found) / len(keywords) * 100) if keywords else 0
    return found, missing, pct


# ── Scoring ───────────────────────────────────────────────────────────────────

def _score_completeness(found_sections: list[str]) -> int:
    weights = {
        "Contact Information": 15,
        "Summary": 20,
        "Work Experience": 25,
        "Education": 20,
        "Certifications": 10,
        "Skills": 10,
    }
    return min(100, sum(weights.get(s, 0) for s in found_sections))


def _score_summary(text: str) -> int:
    tl = _lower(text)
    if not re.search(r'\b(summary|objective|profile|about me|professional summary)\b', tl):
        return 20
    score = 40
    if re.search(r'\b(icu|er|cardiac|telemetry|surgical|pediatric|nicu|med.surg|oncology|emergency|rn|nurse)\b', tl):
        score += 20
    if re.search(r'\b\d+\s*\+?\s*(years?|yrs?)\b', tl):
        score += 20
    summary_block = re.search(r'(summary|objective|profile)[^\n]*\n(.{50,400})', text, re.I)
    if summary_block:
        score += 20
    return min(100, score)


def _score_action_verbs(strong: int, total: int) -> int:
    if total == 0:
        return 30
    ratio = strong / total
    return min(100, int(ratio * 100))


def _score_readability(text: str) -> int:
    score = 100
    long_paras = _long_paragraphs(text)
    if long_paras > 2:
        score -= 25
    elif long_paras > 0:
        score -= 10
    bullet_lines = sum(1 for l in text.splitlines() if l.strip() and l.strip()[0] in "•-*·▪–")
    if bullet_lines == 0:
        score -= 25
    elif bullet_lines < 4:
        score -= 10
    chars = len(text)
    if chars < 500:
        score -= 20
    elif chars > 6000:
        score -= 10
    repeated = _repeated_phrases(text)
    if len(repeated) > 5:
        score -= 10
    return max(0, score)


def _score_formatting(text: str, date_fmts: set[str]) -> int:
    score = 100
    if len(date_fmts) > 1:
        score -= 25
    elif len(date_fmts) == 0:
        score -= 15
    chars = len(text)
    if chars < 300:
        score -= 30
    elif chars > 7000:
        score -= 15
    if not re.search(r'\b(email|phone|\(\d{3}\)|@)\b', text, re.I):
        score -= 20
    if not _has_metrics(text):
        score -= 10
    return max(0, score)


def _overall_score(cats: dict) -> int:
    weights = {
        "completeness": 0.25,
        "action_verbs": 0.20,
        "keywords": 0.20,
        "readability": 0.15,
        "formatting": 0.10,
        "summary": 0.10,
    }
    return min(100, round(sum(cats[k] * w for k, w in weights.items())))


def _score_label(score: int) -> str:
    if score >= 85:
        return "Strong"
    if score >= 70:
        return "Good — needs polish"
    if score >= 50:
        return "Needs improvement"
    return "Needs major work"


def _score_color(score: int) -> str:
    if score >= 85:
        return "good"
    if score >= 70:
        return "warn"
    if score >= 50:
        return "warn"
    return "bad"


# ── Suggestion + checklist generation ────────────────────────────────────────

def _build_suggestions(text: str, missing_sections: list[str], weak_words: list[dict],
                       strong: int, total: int, keyword_pct: int,
                       keywords_missing: list[str], date_fmts: set[str],
                       target_role: str, tone: str) -> list[str]:
    tips: list[str] = []

    if "Summary" in missing_sections:
        tips.append("Add a Professional Summary section at the top (2–3 sentences with your specialty, years, and top certifications).")

    if not _has_metrics(text):
        tips.append("Add measurable outcomes — patient ratios, unit size, case volumes, or percentage improvements.")

    if weak_words:
        ex = weak_words[0]["found"]
        alt = " / ".join(weak_words[0]["suggestions"][:2])
        tips.append(f'Replace passive phrases like "{ex}" → try "{alt}" to make bullets more impactful.')

    if total > 0 and (strong / total) < 0.5:
        tips.append("Start more bullet points with strong action verbs: Administered, Coordinated, Monitored, Triaged, Implemented.")

    if keyword_pct < 50 and keywords_missing:
        missing_ex = ", ".join(keywords_missing[:4])
        tips.append(f"Add more {target_role} keywords to pass ATS filters — missing: {missing_ex}.")

    if "Certifications" in missing_sections:
        tips.append("Add a Certifications section listing name, issuing body, and expiry date for each credential.")

    if "Skills" in missing_sections:
        tips.append("Add a Skills section listing EMRs, clinical software, and specialty competencies.")

    if len(date_fmts) > 1:
        tips.append(f"Standardise date formats — currently mixed ({', '.join(sorted(date_fmts))}). Use 'MMM YYYY' throughout.")

    if "Education" in missing_sections:
        tips.append("Add an Education section with your nursing degree, institution, and graduation year.")

    if "Contact Information" in missing_sections:
        tips.append("Ensure contact details (phone, email, LinkedIn) appear at the top of the resume.")

    return tips[:10]


def _build_checklist(text: str, missing_sections: list[str], weak_words: list[dict],
                     strong: int, total: int, keyword_pct: int) -> list[dict]:
    items = []

    def item(label: str, done: bool) -> dict:
        return {"item": label, "done": done}

    items.append(item("Professional Summary present",  "Summary" not in missing_sections))
    items.append(item("Work Experience section present", "Work Experience" not in missing_sections))
    items.append(item("Education section present",     "Education" not in missing_sections))
    items.append(item("Certifications section present","Certifications" not in missing_sections))
    items.append(item("Skills section present",        "Skills" not in missing_sections))
    items.append(item("Contact info present",          "Contact Information" not in missing_sections))
    items.append(item("Uses strong action verbs",      total > 0 and (strong / total) >= 0.6))
    items.append(item("Contains measurable outcomes",  _has_metrics(text)))
    items.append(item("No passive/weak phrases",       len(weak_words) == 0))
    items.append(item("Keyword match ≥ 50%",           keyword_pct >= 50))
    items.append(item("Consistent date formatting",    len(_date_formats(text)) <= 1))
    items.append(item("Resume is appropriate length",  500 <= len(text) <= 6000))

    return items


# ── Main entry point ──────────────────────────────────────────────────────────

def enhance_resume(raw: bytes = b"", mime_type: str = "", filename: str = "",
                   text_input: str = "", target_role: str = "Travel Nurse",
                   tone: str = "Professional") -> dict:
    if text_input and len(text_input.strip()) > 50:
        text = text_input.strip()
    else:
        text = _extract_text_from_bytes(raw, mime_type, filename)

    text_ok = bool(text and len(text.strip()) > 50)

    if not text_ok:
        logger.info("[ResumeEnhancer] Could not extract text — returning generic suggestions.")
        return {
            "overall_score": 0,
            "score_label": "Could not read file",
            "score_color": "bad",
            "categories": {k: {"score": 0, "label": l} for k, l in [
                ("completeness", "Completeness"), ("summary", "Summary"),
                ("action_verbs", "Action Verbs"), ("keywords", "Keywords"),
                ("readability", "Readability"), ("formatting", "Formatting"),
            ]},
            "found_sections": [],
            "missing_sections": list(_SECTION_PATTERNS.keys()),
            "weak_words": [],
            "keywords_found": [],
            "keywords_missing": ROLE_KEYWORDS.get(target_role, [])[:8],
            "keyword_pct": 0,
            "suggestions": [
                "Could not extract text from this file. Try a PDF, DOCX, or TXT version.",
                "Add a Professional Summary section.",
                "Use strong action verbs on every bullet point.",
                "Include certifications with expiry dates.",
            ],
            "checklist": [],
            "formatting_notes": ["File text could not be extracted — try a different format."],
            "source": "template",
            "text_extracted": False,
            "char_count": 0,
            "target_role": target_role,
            "tone": tone,
        }

    # Run AI if available (OpenAI key set)
    ai_result = _ai_suggestions(text, target_role)

    # Always run local analysis for categories + structured data
    found_sections, missing_sections = _detect_sections(text)
    weak_words = _detect_weak_words(text)
    strong, total = _leading_verb_bullets(text)
    date_fmts = _date_formats(text)
    kw_found, kw_missing, kw_pct = _keyword_match(text, target_role)

    cat_scores = {
        "completeness": _score_completeness(found_sections),
        "summary":      _score_summary(text),
        "action_verbs": _score_action_verbs(strong, total),
        "keywords":     kw_pct,
        "readability":  _score_readability(text),
        "formatting":   _score_formatting(text, date_fmts),
    }
    overall = _overall_score(cat_scores)

    category_labels = {
        "completeness": "Completeness",
        "summary":      "Summary",
        "action_verbs": "Action Verbs",
        "keywords":     "Keywords",
        "readability":  "Readability",
        "formatting":   "Formatting",
    }

    if ai_result:
        suggestions = ai_result.get("suggestions") or ai_result.get("summary", [])
        if not suggestions:
            suggestions = _build_suggestions(text, missing_sections, weak_words,
                                             strong, total, kw_pct, kw_missing, date_fmts,
                                             target_role, tone)
        source = "ai"
    else:
        suggestions = _build_suggestions(text, missing_sections, weak_words,
                                         strong, total, kw_pct, kw_missing, date_fmts,
                                         target_role, tone)
        source = "analysis"

    formatting_notes: list[str] = []
    if len(date_fmts) > 1:
        formatting_notes.append(f"Mixed date formats detected ({', '.join(sorted(date_fmts))}). Standardise to 'MMM YYYY'.")
    if _long_paragraphs(text) > 1:
        formatting_notes.append("Long paragraphs found. Break them into bullet points for readability.")
    if len(text) < 500:
        formatting_notes.append("Resume appears very short. Expand experience with specific duties and outcomes.")
    elif len(text) > 6500:
        formatting_notes.append("Resume may be too long (>2 pages). Trim older roles to 1–2 bullets each.")
    if not re.search(r'\b(email|phone|\(\d{3}\)|@)\b', text, re.I):
        formatting_notes.append("Contact information not clearly visible. Add phone and email at the top.")
    if not _has_metrics(text):
        formatting_notes.append("No measurable outcomes detected. Add numbers, percentages, or patient ratios.")
    repeated = _repeated_phrases(text)
    if repeated:
        formatting_notes.append(f"Repeated words found: {', '.join(repeated[:5])}. Vary your language.")
    if not formatting_notes:
        formatting_notes.append("No major formatting issues detected.")

    return {
        "overall_score": overall,
        "score_label":   _score_label(overall),
        "score_color":   _score_color(overall),
        "categories":    {k: {"score": cat_scores[k], "label": category_labels[k]}
                          for k in cat_scores},
        "found_sections":   found_sections,
        "missing_sections": missing_sections,
        "weak_words":       weak_words[:8],
        "keywords_found":   kw_found,
        "keywords_missing": kw_missing[:12],
        "keyword_pct":      kw_pct,
        "suggestions":      suggestions,
        "checklist":        _build_checklist(text, missing_sections, weak_words,
                                             strong, total, kw_pct),
        "formatting_notes": formatting_notes,
        "source":           source,
        "text_extracted":   True,
        "char_count":       len(text),
        "target_role":      target_role,
        "tone":             tone,
    }


# ── Optional AI path ──────────────────────────────────────────────────────────

def _ai_suggestions(text: str, target_role: str) -> dict | None:
    try:
        import os, openai
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            return None
        client = openai.OpenAI(api_key=api_key)
        prompt = (
            f"You are a professional resume coach for {target_role}. "
            "Review the resume and return JSON with key 'suggestions': a list of 5-8 specific improvements. "
            "Be concise and specific to the content. Output only valid JSON.\n\n"
            f"Resume:\n{text[:3000]}"
        )
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
            response_format={"type": "json_object"},
        )
        return json.loads(response.choices[0].message.content)
    except Exception as exc:
        logger.debug(f"[ResumeEnhancer] AI unavailable: {exc}")
        return None
