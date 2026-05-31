import json
import os
import urllib.parse
import urllib.request

import stripe


def _fetch_connector_credentials() -> dict | None:
    hostname = os.environ.get("REPLIT_CONNECTORS_HOSTNAME")
    if not hostname:
        return None

    repl_identity = os.environ.get("REPL_IDENTITY")
    web_repl_renewal = os.environ.get("WEB_REPL_RENEWAL")

    if repl_identity:
        token = f"repl {repl_identity}"
    elif web_repl_renewal:
        token = f"depl {web_repl_renewal}"
    else:
        return None

    is_production = os.environ.get("REPLIT_DEPLOYMENT") == "1"
    target_env = "production" if is_production else "development"

    def _query(env: str) -> dict | None:
        params = urllib.parse.urlencode({
            "include_secrets": "true",
            "connector_names": "stripe",
            "environment": env,
        })
        url = f"https://{hostname}/api/v2/connection?{params}"
        req = urllib.request.Request(
            url,
            headers={"Accept": "application/json", "X-Replit-Token": token},
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
            items = data.get("items", [])
            if not items:
                return None
            settings = items[0].get("settings", {})
            key = settings.get("secret")
            if not key:
                return None
            return {
                "secret_key": key,
                "publishable_key": settings.get("publishable"),
            }
        except Exception:
            return None

    result = _query(target_env)
    if result is None and target_env == "production":
        result = _query("development")
    return result


def _secret_key() -> str:
    creds = _fetch_connector_credentials()
    if creds and creds.get("secret_key"):
        return creds["secret_key"]
    return os.environ.get("STRIPE_SECRET_KEY", "")


def stripe_configured() -> bool:
    return bool(_secret_key())


def _price(env_var: str) -> str:
    return os.environ.get(env_var, "")


PRICE_VARS = {
    "premium_monthly":      "STRIPE_PRICE_PREMIUM_MONTHLY",
    "premium_yearly":       "STRIPE_PRICE_PREMIUM_YEARLY",
    "premium_plus_monthly": "STRIPE_PRICE_PREMIUM_PLUS_MONTHLY",
    "premium_plus_yearly":  "STRIPE_PRICE_PREMIUM_PLUS_YEARLY",
}


def price_ids() -> dict:
    return {k: _price(v) for k, v in PRICE_VARS.items()}


def tier_for_price_id(price_id: str) -> str:
    ids = price_ids()
    if price_id in (ids["premium_monthly"], ids["premium_yearly"]):
        return "premium"
    if price_id in (ids["premium_plus_monthly"], ids["premium_plus_yearly"]):
        return "premium_plus"
    return "free"


def get_or_create_customer(user) -> str:
    stripe.api_key = _secret_key()
    if user.stripe_customer_id:
        return user.stripe_customer_id
    customer = stripe.Customer.create(
        email=user.email,
        name=user.name or user.email,
        metadata={"user_id": str(user.id)},
    )
    return customer.id


def create_checkout_session(user, price_id: str, success_url: str, cancel_url: str):
    stripe.api_key = _secret_key()
    customer_id = get_or_create_customer(user)
    session = stripe.checkout.Session.create(
        customer=customer_id,
        mode="subscription",
        payment_method_types=["card"],
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={"user_id": str(user.id)},
        allow_promotion_codes=True,
        billing_address_collection="auto",
    )
    return session


def create_portal_session(user, return_url: str):
    stripe.api_key = _secret_key()
    if not user.stripe_customer_id:
        return None
    session = stripe.billing_portal.Session.create(
        customer=user.stripe_customer_id,
        return_url=return_url,
    )
    return session


def construct_webhook_event(payload: bytes, sig_header: str):
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    return stripe.Webhook.construct_event(payload, sig_header, secret)
