import os
import stripe


def _key() -> str:
    return os.environ.get("STRIPE_SECRET_KEY", "")


def stripe_configured() -> bool:
    return bool(_key())


def _price(env_var: str) -> str:
    return os.environ.get(env_var, "")


PRICE_VARS = {
    "premium_monthly":       "STRIPE_PRICE_PREMIUM_MONTHLY",
    "premium_yearly":        "STRIPE_PRICE_PREMIUM_YEARLY",
    "premium_plus_monthly":  "STRIPE_PRICE_PREMIUM_PLUS_MONTHLY",
    "premium_plus_yearly":   "STRIPE_PRICE_PREMIUM_PLUS_YEARLY",
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
    stripe.api_key = _key()
    if user.stripe_customer_id:
        return user.stripe_customer_id
    customer = stripe.Customer.create(
        email=user.email,
        name=user.name or user.email,
        metadata={"user_id": str(user.id)},
    )
    return customer.id


def create_checkout_session(user, price_id: str, success_url: str, cancel_url: str):
    stripe.api_key = _key()
    customer_id = get_or_create_customer(user)
    session = stripe.checkout.Session.create(
        customer=customer_id,
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={"user_id": str(user.id)},
        allow_promotion_codes=True,
        billing_address_collection="auto",
    )
    return session


def create_portal_session(user, return_url: str):
    stripe.api_key = _key()
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
