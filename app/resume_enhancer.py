"""Resume enhancer — extracts text and returns improvement suggestions."""
import logging

logger = logging.getLogger(__name__)

_MOCK_SUGGESTIONS = {
    "summary": [
        "Lead with your specialisation and years of experience (e.g. 'ICU RN with 5+ years in Level-1 trauma centres').",
        "Quantify impact where possible ('Maintained <2% CLABSI rate across 24-bed unit').",
        "Trim filler phrases like 'detail-oriented' and 'team player' — show, don't tell.",
    ],
    "bullets": [
        "Start every bullet with a strong action verb: 'Administered', 'Coordinated', 'Reduced', 'Implemented'.",
        "Add patient/case volume or outcome metrics to each role ('Managed 6-patient caseload in 12-hour shifts').",
        "Mention specific equipment, EMRs, or protocols you used (Epic, Meditech, ACLS, TNCC).",
        "Replace vague bullets ('Helped with patient care') with specific ones ('Performed wound assessments and dressing changes for post-op surgical patients').",
    ],
    "formatting": [
        "Use consistent date format throughout (MMM YYYY or MM/YYYY).",
        "Keep to 1–2 pages; recruiters scan in seconds.",
        "List certifications with expiry dates so they match your Credanta credential vault.",
    ],
}


def _extract_text_from_bytes(raw: bytes, mime_type: str, filename: str) -> str:
    """Re-use the smart_categorize extractor."""
    try:
        from .smart_categorize import _extract_text
        return _extract_text(raw, mime_type, filename)
    except Exception:
        return ""


def _ai_suggestions(text_sample: str) -> dict | None:
    """Call OpenAI if configured. Returns suggestion dict or None."""
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


def enhance_resume(raw: bytes, mime_type: str, filename: str) -> dict:
    """
    Extract text from resume and return improvement suggestions.
    Falls back to mock suggestions if AI is unavailable.
    """
    text = _extract_text_from_bytes(raw, mime_type, filename)

    ai_result = None
    if text and len(text.strip()) > 50:
        ai_result = _ai_suggestions(text)

    if ai_result and isinstance(ai_result, dict):
        suggestions = {
            "summary": ai_result.get("summary", []),
            "bullets": ai_result.get("bullets", []),
            "formatting": ai_result.get("formatting", []),
            "source": "ai",
        }
    else:
        if not text or len(text.strip()) < 50:
            logger.info("[ResumeEnhancer] Could not extract text — returning generic suggestions.")
        suggestions = {**_MOCK_SUGGESTIONS, "source": "template"}

    suggestions["text_extracted"] = bool(text and len(text.strip()) > 50)
    suggestions["char_count"] = len(text)
    return suggestions
