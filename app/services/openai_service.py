"""Server-side OpenAI helpers for Credanta.

This module mirrors the contract of ``server/services/openaiService.ts`` for
the current FastAPI runtime. It never exposes API keys or logs resume content.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.4-mini")
MAX_RESUME_INPUT_CHARS = 12_000
MAX_RESUME_OUTPUT_TOKENS = 1_800


def is_openai_configured() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY", "").strip())


@dataclass
class CredantaAIError(Exception):
    public_message: str
    code: str = "OPENAI_OPERATION_FAILED"
    status_code: int = 502

    def __str__(self) -> str:
        return self.public_message


def _log_event(operation: str, model: str, success: bool, code: str | None = None) -> None:
    payload = {
        "operation": operation,
        "model": model,
        "success": success,
    }
    if code:
        payload["code"] = code
    logger.info("[openai] %s", payload)


def _resume_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "professionalVersion": {"type": "string"},
            "recruiterVersion": {"type": "string"},
            "impactVersion": {"type": "string"},
            "suggestedKeywords": {"type": "array", "items": {"type": "string"}},
            "improvementNotes": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "professionalVersion",
            "recruiterVersion",
            "impactVersion",
            "suggestedKeywords",
            "improvementNotes",
        ],
    }


def _build_prompt(resume_text: str, target_role: str | None) -> str:
    role = target_role.strip() if target_role and target_role.strip() else "Healthcare role not specified"
    return "\n".join([
        "You are helping Credanta users improve resume wording for healthcare recruiting.",
        f"Target role: {role}",
        "",
        "Rules:",
        "- Do not invent experience.",
        "- Do not invent certifications.",
        "- Do not invent licenses.",
        "- Do not invent employers.",
        "- Preserve factual content.",
        "- Improve wording only.",
        "- If a detail is unclear or missing, do not add it.",
        "",
        "Return only structured JSON matching the provided schema.",
        "",
        "Resume text:",
        resume_text.strip(),
    ])


def _extract_output_text(payload: dict[str, Any]) -> str:
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"]
    parts: list[str] = []
    for item in payload.get("output") or []:
        for content in item.get("content") or []:
            text = content.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "\n".join(parts)


def _parse_resume_versions(payload: dict[str, Any]) -> dict[str, Any]:
    raw = _extract_output_text(payload)
    if not raw:
        raise CredantaAIError("AI response could not be read.", "OPENAI_RESPONSE_EMPTY", 502)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise CredantaAIError("AI response was not valid JSON.", "OPENAI_RESPONSE_INVALID_JSON", 502)

    required_strings = ("professionalVersion", "recruiterVersion", "impactVersion")
    required_lists = ("suggestedKeywords", "improvementNotes")
    if not isinstance(data, dict):
        raise CredantaAIError("AI response had an unexpected format.", "OPENAI_RESPONSE_SCHEMA_MISMATCH", 502)
    if any(not isinstance(data.get(key), str) for key in required_strings):
        raise CredantaAIError("AI response had an unexpected format.", "OPENAI_RESPONSE_SCHEMA_MISMATCH", 502)
    if any(not isinstance(data.get(key), list) for key in required_lists):
        raise CredantaAIError("AI response had an unexpected format.", "OPENAI_RESPONSE_SCHEMA_MISMATCH", 502)

    return {
        "professionalVersion": data["professionalVersion"],
        "recruiterVersion": data["recruiterVersion"],
        "impactVersion": data["impactVersion"],
        "suggestedKeywords": [str(item) for item in data["suggestedKeywords"]],
        "improvementNotes": [str(item) for item in data["improvementNotes"]],
    }


def generate_resume_versions(
    resume_text: str,
    target_role: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    operation = "generateResumeVersions"
    model_used = model or DEFAULT_MODEL
    if not is_openai_configured():
        error = CredantaAIError(
            "AI service is not configured. Please add OPENAI_API_KEY on the server.",
            "OPENAI_API_KEY_MISSING",
            503,
        )
        _log_event(operation, model_used, False, error.code)
        raise error

    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    body = {
        "model": model_used,
        "max_output_tokens": MAX_RESUME_OUTPUT_TOKENS,
        "input": _build_prompt(resume_text, target_role),
        "text": {
            "format": {
                "type": "json_schema",
                "name": "credanta_resume_versions",
                "strict": True,
                "schema": _resume_schema(),
            },
        },
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            payload = json.loads(response.read().decode("utf-8"))
        result = _parse_resume_versions(payload)
        _log_event(operation, model_used, True)
        return result
    except CredantaAIError as exc:
        _log_event(operation, model_used, False, exc.code)
        raise
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        logger.warning("[openai] resume generation failed: %s", type(exc).__name__)
        _log_event(operation, model_used, False, "OPENAI_OPERATION_FAILED")
        raise CredantaAIError(
            "AI suggestions are temporarily unavailable. Please try again shortly.",
            "OPENAI_OPERATION_FAILED",
            502,
        )
