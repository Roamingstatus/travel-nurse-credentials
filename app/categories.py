"""Universal credential categories and legacy mapping for existing uploads."""

# Display / upload order (excluding "Other" which sorts last)
CATEGORY_ORDER = [
    "Identity",
    "Licenses & Certifications",
    "Health & Compliance",
    "Education",
    "Other",
]

CREDENTIAL_CATEGORIES = [c for c in CATEGORY_ORDER if c != "Other"] + ["Other"]

# Minimal “career readiness” set for completeness + Ready score (not industry-specific)
CORE_REQUIRED: list[str] = []

# Map historical healthcare-specific labels onto universal buckets
LEGACY_CATEGORY_MAP: dict[str, str] = {
    "RN License": "Licenses & Certifications",
    "Compact License": "Licenses & Certifications",
    "BLS Certification": "Licenses & Certifications",
    "ACLS Certification": "Licenses & Certifications",
    "PALS Certification": "Licenses & Certifications",
    "NRP Certification": "Licenses & Certifications",
    "TNCC Certification": "Licenses & Certifications",
    "Licenses": "Licenses & Certifications",
    "Certifications": "Licenses & Certifications",
    "Driver's License": "Identity",
    "Passport": "Identity",
    "Social Security Card": "Identity",
    "COVID Vaccination": "Health & Compliance",
    "Flu Shot": "Health & Compliance",
    "Hepatitis B": "Health & Compliance",
    "MMR Titer": "Health & Compliance",
    "Varicella Titer": "Health & Compliance",
    "TB Test / PPD": "Health & Compliance",
    "Physical Exam": "Health & Compliance",
    "Drug Screen": "Health & Compliance",
    "Background Check": "Health & Compliance",
    "CPR Card": "Licenses & Certifications",
    "Resume / CV": "Other",
    "Reference Letter": "Other",
    "Skills Checklist": "Other",
    "Contracts": "Other",
    "Skills & Portfolio": "Other",
    "Employment": "Other",
    "Other": "Other",
}


def normalized_effective_category(raw: str) -> str:
    """Resolve stored category to a universal bucket for grouping and completeness."""
    if not raw:
        return "Other"
    resolved = LEGACY_CATEGORY_MAP.get(raw.strip(), raw.strip())
    if resolved in {"Licenses", "Certifications"}:
        return "Licenses & Certifications"
    if resolved in {"Contracts", "Skills & Portfolio", "Employment"}:
        return "Other"
    return resolved
