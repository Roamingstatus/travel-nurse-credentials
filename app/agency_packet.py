"""Agency packet auto-fill — maps user docs to agency template requirements."""
from datetime import datetime

AGENCY_TEMPLATES: dict[str, dict] = {
    "General Employment": {
        "description": "Standard employment package for most companies.",
        "required": ["Identity"],
        "recommended": ["Education", "Licenses & Certifications"],
    },
    "Healthcare Credentialing": {
        "description": "Full credentialing package for hospitals, clinics, and travel nurse agencies.",
        "required": ["Identity", "Licenses & Certifications", "Health & Compliance"],
        "recommended": ["Education"],
    },
    "Contractor Onboarding": {
        "description": "Independent contractor or staffing agency onboarding.",
        "required": ["Identity", "Licenses & Certifications"],
        "recommended": ["Education", "Health & Compliance"],
    },
    "Education / Teaching": {
        "description": "Teaching and educational institution credential requirements.",
        "required": ["Identity", "Licenses & Certifications", "Education"],
        "recommended": ["Health & Compliance"],
    },
    "Transportation / CDL": {
        "description": "Commercial driver and transportation compliance package.",
        "required": ["Identity", "Licenses & Certifications", "Health & Compliance"],
        "recommended": [],
    },
}

TEMPLATE_NAMES = list(AGENCY_TEMPLATES.keys())


def autofill_agency_packet(template_name: str, documents: list) -> dict:
    """
    Map user documents to an agency template's requirements.

    Returns:
      - template_name, description
      - required_categories
      - recommended_categories
      - matched      (categories covered)
      - missing      (categories with no doc)
      - expiring     (categories expiring within 60 days)
      - expired      (categories with only expired docs)
      - doc_mapping  (category → list of doc titles)
      - readiness_pct
    """
    from .categories import normalized_effective_category

    template = AGENCY_TEMPLATES.get(template_name, AGENCY_TEMPLATES["General Employment"])
    required: list[str] = template["required"]
    recommended: list[str] = template["recommended"]
    all_cats = required + [r for r in recommended if r not in required]

    now = datetime.utcnow()
    from datetime import timedelta
    window = timedelta(days=60)

    by_cat: dict[str, list] = {}
    for doc in documents:
        cat = normalized_effective_category(doc.category)
        by_cat.setdefault(cat, []).append(doc)

    matched: list[str] = []
    missing: list[str] = []
    expiring: list[str] = []
    expired: list[str] = []
    doc_mapping: dict[str, list[str]] = {}

    for cat in all_cats:
        docs_in_cat = by_cat.get(cat, [])
        if not docs_in_cat:
            missing.append(cat)
            continue

        valid = [d for d in docs_in_cat if d.expires_at is None or d.expires_at >= now]
        past = [d for d in docs_in_cat if d.expires_at is not None and d.expires_at < now]
        exp_soon = [d for d in valid if d.expires_at is not None and d.expires_at < now + window]

        doc_mapping[cat] = [d.title for d in docs_in_cat]

        if valid and not exp_soon:
            matched.append(cat)
        elif exp_soon:
            expiring.append(cat)
        elif not valid and past:
            expired.append(cat)
        else:
            matched.append(cat)

    req_done = sum(1 for c in required if c in matched or c in expiring)
    readiness_pct = int((req_done / len(required)) * 100) if required else 100

    return {
        "template_name": template_name,
        "description": template["description"],
        "required_categories": required,
        "recommended_categories": recommended,
        "matched": matched,
        "missing": missing,
        "expiring": expiring,
        "expired": expired,
        "doc_mapping": doc_mapping,
        "readiness_pct": readiness_pct,
    }
