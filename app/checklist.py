"""Smart checklist tracker — maps uploaded docs against profession-specific requirements."""
import json
from datetime import datetime, timedelta

PROFILES: dict[str, dict] = {
    "General Professional": {
        "required": ["Identity"],
        "recommended": ["Education", "Licenses & Certifications"],
    },
    "Healthcare": {
        "required": ["Identity", "Licenses & Certifications", "Health & Compliance"],
        "recommended": ["Education"],
    },
    "Education / Teaching": {
        "required": ["Identity", "Licenses & Certifications", "Education"],
        "recommended": ["Health & Compliance"],
    },
    "IT / Tech": {
        "required": ["Identity", "Education"],
        "recommended": ["Licenses & Certifications"],
    },
    "Transportation / CDL": {
        "required": ["Identity", "Licenses & Certifications", "Health & Compliance"],
        "recommended": [],
    },
    "Trades / Construction": {
        "required": ["Identity", "Licenses & Certifications"],
        "recommended": ["Health & Compliance"],
    },
    "Legal": {
        "required": ["Identity", "Licenses & Certifications", "Education"],
        "recommended": [],
    },
}

PROFILE_NAMES = list(PROFILES.keys())

_EXPIRING_WINDOW = timedelta(days=60)


def generate_checklist(profile_type: str, documents: list) -> dict:
    """
    Compare user documents against the required/recommended categories for a profession.

    Returns a dict with:
      - profile_type
      - required_categories
      - recommended_categories
      - completed     (categories covered by current docs)
      - missing       (required categories with no doc)
      - expiring      (categories whose only docs are expiring soon)
      - expired       (categories whose only docs are expired)
      - readiness_score (0-100)
      - doc_count
    """
    profile = PROFILES.get(profile_type, PROFILES["General Professional"])
    required: list[str] = profile["required"]
    recommended: list[str] = profile["recommended"]
    all_needed = required + [r for r in recommended if r not in required]

    now = datetime.utcnow()

    # bucket docs by normalised category
    from .categories import normalized_effective_category
    by_cat: dict[str, list] = {}
    for doc in documents:
        cat = normalized_effective_category(doc.category)
        by_cat.setdefault(cat, []).append(doc)

    completed: list[str] = []
    missing: list[str] = []
    expiring: list[str] = []
    expired_cats: list[str] = []

    for cat in all_needed:
        docs_in_cat = by_cat.get(cat, [])
        if not docs_in_cat:
            missing.append(cat)
            continue

        valid = [d for d in docs_in_cat if d.expires_at is None or d.expires_at >= now]
        exp_soon = [d for d in valid if d.expires_at is not None and d.expires_at < now + _EXPIRING_WINDOW]
        past = [d for d in docs_in_cat if d.expires_at is not None and d.expires_at < now]

        if valid and not exp_soon:
            completed.append(cat)
        elif exp_soon and valid:
            expiring.append(cat)
        elif not valid and past:
            expired_cats.append(cat)
        else:
            completed.append(cat)

    required_total = len(required)
    required_done = sum(
        1 for c in required
        if c in completed or c in expiring
    )
    score = int((required_done / required_total) * 100) if required_total else 100

    return {
        "profile_type": profile_type,
        "required_categories": required,
        "recommended_categories": recommended,
        "completed": completed,
        "missing": missing,
        "expiring": expiring,
        "expired": expired_cats,
        "readiness_score": score,
        "doc_count": len(documents),
    }
