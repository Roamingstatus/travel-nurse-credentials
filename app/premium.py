import os

from .db import User

PREMIUM_FEATURES = [
    {
        "key": "advanced_ai_parsing",
        "name": "Advanced AI parsing",
        "description": "OpenAI-backed category and expiration extraction from document text.",
    },
    {
        "key": "sms_reminders",
        "name": "SMS reminders",
        "description": "Text alerts before important credentials expire.",
    },
    {
        "key": "branded_share_pages",
        "name": "Branded share pages",
        "description": "Custom presentation for recruiter-facing packet links.",
    },
    {
        "key": "unlimited_storage",
        "name": "Unlimited storage",
        "description": "Expanded vault capacity for long-running credential history.",
    },
    {
        "key": "custom_folders_tags",
        "name": "Custom folders/tags",
        "description": "Organize documents beyond the default credential categories.",
    },
    {
        "key": "recruiter_analytics",
        "name": "Recruiter analytics",
        "description": "Visibility into packet views and document downloads.",
    },
    {
        "key": "advanced_packet_templates",
        "name": "Advanced packet templates",
        "description": "Configurable recruiter packet layouts and exports.",
    },
]


def user_has_premium(user: User | None) -> bool:
    if not user:
        return False
    if os.environ.get("SKILLDOCK_PREMIUM", "").lower() in {"1", "true", "yes", "on"}:
        return True
    premium_users = {
        email.strip().lower()
        for email in os.environ.get("SKILLDOCK_PREMIUM_USERS", "").split(",")
        if email.strip()
    }
    return user.email.lower() in premium_users
