---
name: Pre-deployment audit findings
description: Summary of critical gaps found in the June 2026 audit; what must be fixed before launch
---

# Critical Gaps (code fixes needed)
1. No global `Exception` handler (only `HTTPException` caught) → unhandled errors may leak stack traces
2. No CSRF middleware — SameSite=Lax only; mutating routes are exposed
3. `TWILIO_FROM_NUMBER` accessed via `os.environ[]` (not `.get()`) → KeyError crashes SMS sends

# High-Risk Config Issues
- SESSION_SECRET missing → random key on startup, sessions die on restart, MFA broken
- STRIPE_WEBHOOK_SECRET missing → all subscription events silently rejected
- BETA_MODE=true grants free Premium Plus to everyone — must not be set in production
- Turnstile fails open if CLOUDFLARE_TURNSTILE_SECRET_KEY not set
- ADMIN_EMAILS not set → admin panel 403-locked in production

# What Passes Well
- Document upload security (magic bytes, threat scan, dedup, path traversal, 25MB cap)
- Share link tokens (144-bit entropy, HMAC download tokens, revocation)
- Stripe webhook signature verification
- No hardcoded API keys anywhere
- Mobile responsiveness (10 breakpoints)
- Analytics (internal only, no external tracking)

# Missing Env Vars for Production
SESSION_SECRET, ADMIN_ROUTE, ADMIN_EMAILS, STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET,
STRIPE_PRICE_* (×4), RESEND_FROM_EMAIL, TWILIO_FROM_NUMBER, APP_BASE_URL, APP_ENV=production
BETA_MODE must NOT be set.

**Why:** Recorded so future sessions know the specific gaps without re-auditing from scratch.
