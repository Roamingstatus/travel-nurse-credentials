"""
Run this once to create Stripe products and prices for Credanta.
After running, copy the printed price IDs into your Replit Secrets:
  STRIPE_PRICE_PREMIUM_MONTHLY
  STRIPE_PRICE_PREMIUM_YEARLY
  STRIPE_PRICE_PREMIUM_PLUS_MONTHLY
  STRIPE_PRICE_PREMIUM_PLUS_YEARLY

Usage:
  STRIPE_SECRET_KEY=sk_test_... python scripts/seed_stripe_products.py
"""

import os
import sys

import stripe

key = os.environ.get("STRIPE_SECRET_KEY")
if not key:
    sys.exit("ERROR: STRIPE_SECRET_KEY environment variable is not set.")

stripe.api_key = key


def find_price(product_id: str, interval: str, amount: int):
    prices = stripe.Price.list(product=product_id, active=True)
    for p in prices.auto_paging_iter():
        if (
            p.recurring
            and p.recurring.interval == interval
            and p.unit_amount == amount
            and p.currency == "usd"
        ):
            return p
    return None


def get_or_create_product(name: str, description: str, metadata: dict):
    products = stripe.Product.search(query=f"name:'{name}'")
    if products.data:
        p = products.data[0]
        print(f"  Found existing product: {p.id} ({name})")
        return p
    p = stripe.Product.create(name=name, description=description, metadata=metadata)
    print(f"  Created product: {p.id} ({name})")
    return p


def get_or_create_price(product_id: str, amount: int, interval: str, nickname: str):
    existing = find_price(product_id, interval, amount)
    if existing:
        print(f"  Found existing price: {existing.id} ({nickname})")
        return existing
    pr = stripe.Price.create(
        product=product_id,
        unit_amount=amount,
        currency="usd",
        recurring={"interval": interval},
        nickname=nickname,
    )
    print(f"  Created price: {pr.id} ({nickname})")
    return pr


print("\n=== Credanta — Stripe Product Seed ===\n")

print("Creating Premium product...")
premium = get_or_create_product(
    name="Credanta Premium",
    description="Email reminders, calendar sync, AI document parsing, and readiness checklist.",
    metadata={"tier": "premium"},
)

print("Creating Premium price — monthly ($5/mo)...")
premium_monthly = get_or_create_price(premium.id, 500, "month", "Premium Monthly")

print("Creating Premium price — yearly ($50/yr)...")
premium_yearly = get_or_create_price(premium.id, 5000, "year", "Premium Yearly")

print("\nCreating Premium+ product...")
premium_plus = get_or_create_product(
    name="Credanta Premium+",
    description="Everything in Premium plus recruiter share links, credential packet generation, and priority support.",
    metadata={"tier": "premium_plus"},
)

print("Creating Premium+ price — monthly ($10/mo)...")
premium_plus_monthly = get_or_create_price(premium_plus.id, 1000, "month", "Premium+ Monthly")

print("Creating Premium+ price — yearly ($80/yr)...")
premium_plus_yearly = get_or_create_price(premium_plus.id, 8000, "year", "Premium+ Yearly")

print("\n=== Done! Add these to your Replit Secrets ===\n")
print(f"STRIPE_PRICE_PREMIUM_MONTHLY={premium_monthly.id}")
print(f"STRIPE_PRICE_PREMIUM_YEARLY={premium_yearly.id}")
print(f"STRIPE_PRICE_PREMIUM_PLUS_MONTHLY={premium_plus_monthly.id}")
print(f"STRIPE_PRICE_PREMIUM_PLUS_YEARLY={premium_plus_yearly.id}")
print()
