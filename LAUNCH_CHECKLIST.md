# Credanta — Launch Checklist

**Based on:** DEPLOYMENT_AUDIT_REPORT.md (2026-06-08)  
**Commit audited:** `ac5f6ee`

---

## 🚦 Go / No-Go Recommendation

> ### ⛔ NO-GO — 3 critical code fixes + 7 environment variables required before launch
>
> The app is feature-complete and architecturally sound. Document uploads, expiration tracking, share links, Stripe billing, and admin hardening are all well-built. However, three code-level gaps (no 500 handler, no CSRF protection, SESSION_SECRET not enforced) and several unconfigured production secrets create real risks that must be resolved before exposing the app to real users.
>
> **Estimated effort to reach GO:** 1–2 days of focused work.

---

## Phase 1 — Must-Do Before Any User Touches the App

These items block launch. Complete all of them first.

---

### 🔐 Secrets & Environment Variables

Set each of these in **Replit Secrets** (lock icon → Secrets). None should be hardcoded in code or `.env` files.

| # | Secret Name | Status | Notes |
|---|---|---|---|
| 1 | `SESSION_SECRET` | ⬜ Set it | Min 32 random characters. Use: `python3 -c "import secrets; print(secrets.token_urlsafe(48))"` |
| 2 | `GOOGLE_CLIENT_ID` | ⬜ Verify | Must match the callback URL registered in Google Cloud Console |
| 3 | `GOOGLE_CLIENT_SECRET` | ⬜ Verify | Must match Google Cloud Console |
| 4 | `ADMIN_ROUTE` | ⬜ Set it | Use a secret path e.g. `/portal-credanta-9f3k2m7x` — NOT `/admin` |
| 5 | `ADMIN_EMAILS` | ⬜ Set it | Comma-separated admin email addresses |
| 6 | `STRIPE_SECRET_KEY` | ⬜ Verify | Use live key (`sk_live_...`) for production |
| 7 | `STRIPE_WEBHOOK_SECRET` | ⬜ Set it | Get from Stripe Dashboard → Webhooks → signing secret |
| 8 | `STRIPE_PRICE_PREMIUM_MONTHLY` | ⬜ Set it | From `scripts/seed_stripe_products.py` output |
| 9 | `STRIPE_PRICE_PREMIUM_YEARLY` | ⬜ Set it | From `scripts/seed_stripe_products.py` output |
| 10 | `STRIPE_PRICE_PREMIUM_PLUS_MONTHLY` | ⬜ Set it | From `scripts/seed_stripe_products.py` output |
| 11 | `STRIPE_PRICE_PREMIUM_PLUS_YEARLY` | ⬜ Set it | From `scripts/seed_stripe_products.py` output |
| 12 | `CLOUDFLARE_TURNSTILE_SITE_KEY` | ⬜ Verify | Public key — shown in Cloudflare dashboard |
| 13 | `CLOUDFLARE_TURNSTILE_SECRET_KEY` | ⬜ Verify | Private key — used server-side |
| 14 | `RESEND_API_KEY` | ⬜ Verify | From Resend dashboard |
| 15 | `RESEND_FROM_EMAIL` | ⬜ Set it | Must be a **verified sender domain** in Resend |
| 16 | `TWILIO_ACCOUNT_SID` | ⬜ Verify | From Twilio console |
| 17 | `TWILIO_AUTH_TOKEN` | ⬜ Verify | From Twilio console |
| 18 | `TWILIO_FROM_NUMBER` | ⬜ Set it | Your Twilio phone number in E.164 format (e.g. `+15551234567`) |
| 19 | `APP_BASE_URL` | ⬜ Set it | Your public URL e.g. `https://credanta.replit.app` — used in email/SMS links |
| 20 | `APP_ENV` | ⬜ Set it | Set to `production` |
| 21 | `BETA_MODE` | ⬜ Verify NOT set | Must **not** be set to `true` in production — bypasses all billing |

---

### 🛠 Code Fixes Required

| # | Issue | Reference | Fix |
|---|---|---|---|
| C1 | ~~Add global 500 error handler~~ | CRIT-01 | ✅ Done — `generic_exception_handler` added to `app/main.py` |
| C2 | ~~Fix TWILIO_FROM_NUMBER KeyError~~ | HIGH-06 | ✅ Done — `os.environ["KEY"]` → `.get()` in `sms_service.py` |
| C3 | ~~Add CSRF protection~~ | CRIT-03 | ✅ Done — `CsrfMiddleware` + per-session tokens + JS auto-injection |
| C4 | ~~Fix SESSION_SECRET env var mismatch~~ | CRIT-02 | ✅ Done — `validate_env()` now reads `APP_ENV` first (matches `is_production()`) |
| C5 | Guard BETA_MODE in production | HIGH-02 | Add `is_production()` check in `app/premium.py` |
| C6 | Fix Stripe API key in webhook handler | MED-04 | Use `_secret_key()` instead of inline `os.environ.get` in `app/main.py:1952` |

---

### ☁️ Google OAuth — Callback URL

- [ ] Open [Google Cloud Console](https://console.cloud.google.com) → Your OAuth app → Credentials
- [ ] Add your production callback URL: `https://your-domain.replit.app/auth/google/callback`
- [ ] Confirm test users list includes all beta testers (if app is in "Testing" mode)
- [ ] If publishing publicly: submit for OAuth verification (required for non-test users)

---

### 💳 Stripe Setup

- [ ] Run `python scripts/seed_stripe_products.py` to create products and price IDs
- [ ] Copy output price IDs into Replit Secrets (items 8–11 above)
- [ ] Create a webhook endpoint in Stripe Dashboard pointing to: `https://your-domain.replit.app/billing/webhook`
- [ ] Enable these webhook events: `checkout.session.completed`, `customer.subscription.updated`, `customer.subscription.deleted`
- [ ] Copy the webhook signing secret into `STRIPE_WEBHOOK_SECRET`
- [ ] Test with Stripe CLI: `stripe listen --forward-to your-domain.replit.app/billing/webhook`
- [ ] Confirm a test purchase upgrades the user tier in the database

---

### 📧 Email Setup (Resend)

- [ ] Add `credanta.com` (or your domain) to Resend → Domains
- [ ] Add the required DNS records (SPF, DKIM, DMARC) to your DNS provider
- [ ] Verify domain status is **Verified** in Resend dashboard
- [ ] Send a test reminder email and confirm delivery (not spam folder)

---

### 📱 SMS Setup (Twilio)

- [ ] Confirm Twilio account is fully verified (not trial — trial accounts have restrictions)
- [ ] Set `TWILIO_FROM_NUMBER` in Replit Secrets
- [ ] Send a test SMS and confirm delivery

---

### 🔒 Cloudflare Turnstile

- [ ] Create a Turnstile widget in [Cloudflare Dashboard](https://dash.cloudflare.com) for your production domain
- [ ] Copy Site Key → `CLOUDFLARE_TURNSTILE_SITE_KEY`
- [ ] Copy Secret Key → `CLOUDFLARE_TURNSTILE_SECRET_KEY`
- [ ] Test the upload flow as a free user — confirm the challenge appears and passes

---

### 🔑 Admin Panel

- [ ] Set `ADMIN_ROUTE` to a secret path (e.g. `/portal-credanta-9f3k2m7x`)
- [ ] Set `ADMIN_EMAILS` to your admin email address
- [ ] Confirm `https://your-domain/admin` returns **404** (not the admin dashboard)
- [ ] Confirm `https://your-domain/{your-secret-route}` loads the admin dashboard after Google sign-in

---

## Phase 2 — Strongly Recommended Before Launch

These are not launch blockers but meaningfully reduce risk.

| # | Item | Reference |
|---|---|---|
| P1 | ~~Add `Content-Security-Policy` header~~ | HIGH-01 | ✅ Done |
| P2 | ~~Add CSRF protection~~ | CRIT-03 | ✅ Done |
| P3 | ~~Add startup validation for all integration env vars~~ | MED-07 | ✅ Done |
| P4 | ~~Enable SQLite WAL mode~~ | LOW-04 | ✅ Done — WAL + synchronous=NORMAL + foreign_keys=ON on every connection |
| P5 | Replace `except Exception: pass` blocks with logging | MED-05 |

---

## Phase 3 — Post-Launch Improvements

Address these in the first sprint after launch.

| # | Item | Reference |
|---|---|---|
| ~~A1~~ | ~~Add admin UI for `AdminAccessLog` viewer~~ | ~~MED-06~~ | ✅ Done |
| ~~A2~~ | ~~Add default 90-day expiry to new share links~~ | ~~LOW-02~~ | ✅ Done |
| ~~A3~~ | ~~Move email HTML to Jinja2 templates~~ | ~~LOW-03~~ | ✅ Done |
| A4 | Add Stripe Price ID startup validation warnings | MED-01 |
| A5 | Remove deprecated `X-XSS-Protection` header once CSP is live | LOW-01 |
| A6 | Plan PostgreSQL migration path | LOW-04 |

---

## Final Pre-Launch Smoke Tests

Run these manually after completing Phase 1.

### Authentication
- [ ] Sign in with Google → redirected to dashboard ✅
- [ ] Sign out → session cleared → redirect to login ✅
- [ ] Visit `/dashboard` without login → 401 / redirect to login ✅

### Document Flow
- [ ] Upload a PDF → appears in document list with correct category ✅
- [ ] Upload a `.exe` file → rejected with error message ✅
- [ ] Upload a file > 25 MB → rejected with error message ✅
- [ ] Preview a PDF → loads inline ✅
- [ ] Download a document → correct file served ✅
- [ ] Delete a document → removed from list and storage ✅

### Expiration Tracking
- [ ] Upload a document with a future expiration → status shows "Valid" ✅
- [ ] Edit expiration to today → status shows "Expiring Soon" ✅
- [ ] Edit expiration to yesterday → status shows "Expired" ✅
- [ ] NIH document without explicit date → expiration auto-calculated ✅

### Share Links
- [ ] Create a share link → public URL accessible without login ✅
- [ ] Revoke the share link → public URL returns 404/error ✅
- [ ] Download a file via share link → requires signed `dl` token ✅

### Premium / Billing
- [ ] Free user sees upgrade prompt for premium features ✅
- [ ] Complete Stripe test checkout → user tier upgrades in DB ✅
- [ ] Cancel subscription via Stripe portal → user tier downgrades ✅
- [ ] Confirm `BETA_MODE` is NOT set (free user cannot access premium features) ✅

### Reminders
- [ ] Enable email reminders in account settings → `ReminderSettings` saved ✅
- [ ] Upload expired document → immediate alert email sent ✅
- [ ] Check Resend dashboard for delivery confirmation ✅

### Admin
- [ ] `GET /admin` → returns 404 ✅
- [ ] `GET /admin/anything` → returns 404 ✅
- [ ] `GET {ADMIN_ROUTE}` while logged out → redirected to login ✅
- [ ] `GET {ADMIN_ROUTE}` as non-admin user → 403 ✅
- [ ] `GET {ADMIN_ROUTE}` as admin user → dashboard loads ✅

### Error Handling
- [ ] Visit non-existent page → friendly 404 error page ✅
- [ ] Trigger a premium gate → upgrade prompt shown, not raw 403 ✅

---

## Environment Checklist Summary

```
Required for launch:
  SESSION_SECRET         ← CRITICAL: must be 32+ random chars
  GOOGLE_CLIENT_ID       ← Auth
  GOOGLE_CLIENT_SECRET   ← Auth
  ADMIN_ROUTE            ← Admin security
  ADMIN_EMAILS           ← Admin security
  APP_ENV=production     ← Enables HTTPS cookies, HSTS, MFA enforcement

Required for payments:
  STRIPE_SECRET_KEY
  STRIPE_WEBHOOK_SECRET
  STRIPE_PRICE_PREMIUM_MONTHLY
  STRIPE_PRICE_PREMIUM_YEARLY
  STRIPE_PRICE_PREMIUM_PLUS_MONTHLY
  STRIPE_PRICE_PREMIUM_PLUS_YEARLY

Required for email reminders:
  RESEND_API_KEY
  RESEND_FROM_EMAIL      ← Must be a verified Resend sender domain

Required for SMS reminders:
  TWILIO_ACCOUNT_SID
  TWILIO_AUTH_TOKEN
  TWILIO_FROM_NUMBER

Required for bot protection:
  CLOUDFLARE_TURNSTILE_SITE_KEY
  CLOUDFLARE_TURNSTILE_SECRET_KEY

Required for correct links in emails/SMS:
  APP_BASE_URL           ← e.g. https://credanta.replit.app

Must NOT be set in production:
  BETA_MODE              ← Bypasses all billing
```

---

*Based on audit commit `ac5f6ee` · Updated 2026-06-08*
