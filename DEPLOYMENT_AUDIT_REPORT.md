# Credanta — Pre-Deployment Readiness Audit

**Date:** 2026-06-08  
**Auditor:** Automated deep-scan across authentication, authorization, uploads, security, integrations, and UX  
**Codebase commit:** `ac5f6ee`

---

## Severity Legend

| Symbol | Meaning |
|---|---|
| 🔴 FAIL | Must be resolved before launch |
| 🟡 WARNING | Should be resolved before or shortly after launch |
| 🟢 PASS | No action required |

---

## Summary

| Category | Status | Critical | High | Medium | Low |
|---|---|---|---|---|---|
| Authentication | 🟡 WARNING | 0 | 1 | 0 | 0 |
| Authorization | 🟡 WARNING | 0 | 1 | 0 | 0 |
| Document Uploads | 🟢 PASS | 0 | 0 | 0 | 0 |
| Document Previews | 🟢 PASS | 0 | 0 | 0 | 0 |
| Expiration Tracking | 🟢 PASS | 0 | 0 | 0 | 0 |
| NIH Custom Rules | 🟢 PASS | 0 | 0 | 0 | 0 |
| Packet Generation | 🟢 PASS | 0 | 0 | 0 | 0 |
| Recruiter Share Links | 🟢 PASS | 0 | 0 | 0 | 1 |
| Premium Feature Gating | 🟡 WARNING | 0 | 1 | 0 | 0 |
| Stripe Integration | 🟡 WARNING | 0 | 1 | 2 | 0 |
| Email Reminders | 🟡 WARNING | 0 | 0 | 2 | 1 |
| SMS Reminders | 🟡 WARNING | 0 | 0 | 1 | 0 |
| Account Page | 🟢 PASS | 0 | 0 | 0 | 0 |
| Resume Enhancer | 🟢 PASS | 0 | 0 | 0 | 1 |
| Analytics | 🟢 PASS | 0 | 0 | 0 | 0 |
| Mobile Responsiveness | 🟢 PASS | 0 | 0 | 0 | 0 |
| Security — Headers | 🟢 PASS | 0 | 0 | 0 | 1 |
| Security — CSRF | 🟢 PASS | 0 | 0 | 0 | 0 |
| Security — Error Handling | 🟡 WARNING | 0 | 0 | 1 | 0 |
| Security — Session Secret | 🟢 PASS | 0 | 0 | 0 | 0 |
| API Key Exposure | 🟢 PASS | 0 | 0 | 0 | 0 |
| Admin Route Protection | 🟢 PASS | 0 | 0 | 1 | 0 |
| Cloudflare Turnstile | 🟡 WARNING | 0 | 1 | 0 | 0 |
| **TOTAL** | | **0** | **6** | **7** | **4** |

---

## 🔴 Critical Issues

---

### CRIT-01 — No global handler for unhandled exceptions (500 errors)
**Status:** ✅ RESOLVED (`app/main.py` — `generic_exception_handler` added)  
`@app.exception_handler(Exception)` now catches all unhandled exceptions, logs the full traceback server-side, and renders the user-facing `error.html` with a generic "Something went wrong" message and a 500 status code.

---

### CRIT-02 — SESSION_SECRET not set causes session invalidation on every restart
**Status:** ✅ RESOLVED (`app/security.py` — `validate_env()` now reads `APP_ENV` first, then `ENV`, matching `is_production()`)  
`validate_env()` previously checked only `ENV=production` while `is_production()` checked `APP_ENV`. The env var detection is now aligned: both read `APP_ENV` first and fall back to `ENV`. Setting `APP_ENV=production` in Replit Secrets now correctly enforces the SESSION_SECRET requirement at startup. **Action still required:** set `SESSION_SECRET` as a Replit Secret (32+ random characters).

---

### CRIT-03 — No CSRF protection middleware
**Status:** ✅ RESOLVED (`app/security.py` + `app/main.py` + `app/templates/base.html` + `app/templates/upload.html`)

**Implementation:**
- `get_csrf_token(session)` and `verify_csrf_token(submitted, session)` added to `app/security.py` (HMAC `compare_digest`, 32-byte URL-safe token stored per session)
- `CsrfMiddleware` added to `app/main.py` — validates all POST/PUT/PATCH/DELETE requests; accepts token from `X-CSRF-Token` header OR `_csrf` hidden form field; exempt paths: `/billing/webhook`, `/auth/google/*`, `/s/*`, `/healthz`
- `base.html` `<head>` now includes `<meta name="csrf-token">` populated by `render()`; inline JS (1) injects `<input name="_csrf">` into every POST form on DOMContentLoaded and (2) monkey-patches `window.fetch` to add `X-CSRF-Token` to all mutating AJAX calls automatically
- `upload.html` XHR sets `X-CSRF-Token` header before `xhr.send()` for multipart uploads

---

## 🟡 High Priority Issues

---

### HIGH-01 — No Content-Security-Policy (CSP) header
**Status:** 🟡 WARNING  
**Location:** `app/security.py:483–503` — `SecurityHeadersMiddleware` sets 6 headers but not `Content-Security-Policy`  
**Risk:** Without CSP, any XSS vulnerability (e.g., stored XSS via document titles or feedback messages) can execute arbitrary JavaScript in users' browsers — including stealing session cookies, redirecting to phishing pages, or exfiltrating credentials.  
**Recommended fix:** Add a CSP header. A starting baseline for this app:
```
Content-Security-Policy: default-src 'self'; script-src 'self' https://challenges.cloudflare.com; frame-src https://challenges.cloudflare.com; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; object-src 'none';
```
Note: The Cloudflare Turnstile widget requires the `challenges.cloudflare.com` allowance. Audit all inline `<script>` blocks for `'unsafe-inline'` exceptions.

---

### HIGH-02 — BETA_MODE=true bypasses all premium and premium-plus checks
**Status:** 🟡 WARNING  
**Location:** `app/premium.py:50–51`, `app/premium.py:124, 133`  
**Risk:** `BETA_MODE=true` is an env var that grants every signed-in user full Premium Plus access for free. If accidentally set in the production environment, no user will ever be charged. There is no production guard preventing it.  
**Recommended fix:**
```python
_BETA_MODE: bool = (
    os.environ.get("BETA_MODE", "false").lower() == "true"
    and not is_production()
)
```
Also add a startup warning: `if _BETA_MODE and is_production(): raise RuntimeError("BETA_MODE must not be enabled in production")`

---

### HIGH-03 — STRIPE_WEBHOOK_SECRET not set causes all webhook events to be rejected
**Status:** 🟡 WARNING  
**Location:** `app/stripe_billing.py:138–139`  
**Risk:** `stripe.Webhook.construct_event(payload, sig, "")` raises `SignatureVerificationError` when the secret is an empty string. All subscription lifecycle events (`checkout.session.completed`, `customer.subscription.updated`, `customer.subscription.deleted`) silently fail — users who pay won't be upgraded; users who cancel won't be downgraded.  
**Recommended fix:** Set `STRIPE_WEBHOOK_SECRET` in Replit Secrets. Add a startup validation:
```python
if is_production() and not os.environ.get("STRIPE_WEBHOOK_SECRET"):
    logging.critical("[stripe] STRIPE_WEBHOOK_SECRET is not set — webhooks will fail")
```

---

### HIGH-04 — Cloudflare Turnstile fails open when secret key is missing
**Status:** 🟡 WARNING  
**Location:** `app/security.py` — `verify_turnstile()` returns `True` if `CLOUDFLARE_TURNSTILE_SECRET_KEY` is absent  
**Risk:** If the Turnstile secret key is not set in production, all bot-protection checks on file uploads and recruiter feedback automatically pass. This was likely a development convenience but becomes a security hole in production.  
**Recommended fix:** In production mode, if the key is not set, `verify_turnstile` should return `False` (fail closed). The startup warning already exists — escalate it to a hard failure in production:
```python
if is_production() and not os.environ.get("CLOUDFLARE_TURNSTILE_SECRET_KEY"):
    raise RuntimeError("Turnstile key required in production")
```

---

### HIGH-05 — ADMIN_EMAILS not set = admin panel fully locked out in production
**Status:** 🟡 WARNING  
**Location:** `app/events.py:55–58`  
**Risk:** In production, if `ADMIN_EMAILS` is empty or not set, `require_admin` raises HTTP 403 for every admin request. The admin dashboard, analytics, feedback, and testing panels become completely inaccessible. A warning is logged at startup but the app does not fail — leaving an operator unaware that they have no admin access.  
**Recommended fix:** Set `ADMIN_EMAILS=your@email.com` in Replit Secrets before deploying. Also set `ADMIN_ROUTE` to a secret path (not `/admin`). If neither is set in production, the admin panel is permanently locked.

---

### HIGH-06 — TWILIO_FROM_NUMBER accessed via os.environ[] — raises KeyError if missing
**Status:** ✅ RESOLVED (`app/services/sms_service.py`)  
`os.environ["TWILIO_ACCOUNT_SID"]`, `os.environ["TWILIO_AUTH_TOKEN"]`, and `os.environ["TWILIO_FROM_NUMBER"]` in `_send()` all changed to `.get("KEY", "")`. The `_twilio_configured()` guard at the top of every public function already prevents `_send()` from being called when any key is absent, so the fallback empty string is only reached if a caller bypasses that guard — in which case Twilio's own client raises an `Exception` that is caught and returned as `{"ok": False, "error": ...}` rather than an unhandled `KeyError`.

---

## 🟡 Medium Priority Issues

---

### MED-01 — Stripe Price ID env vars not validated at startup
**Status:** 🟡 WARNING  
**Location:** `app/stripe_billing.py:77–81`  
**Risk:** The four `STRIPE_PRICE_*` env vars are only read when a checkout session is created. If any are missing, the Stripe API call fails at the moment a user tries to subscribe — with no pre-launch warning. The user sees a generic error.  
**Recommended fix:** Add startup validation that logs `WARNING` for each missing price ID env var, similar to the existing OAuth check in `app/security.py:76–79`.

---

### MED-02 — APScheduler runs in-process (duplicate reminders if multi-worker)
**Status:** 🟡 WARNING  
**Location:** `app/services/reminder_scheduler.py`  
**Risk:** `APScheduler`'s `BackgroundScheduler` runs inside the same Python process. If Replit deploys with multiple worker processes (e.g., via gunicorn with multiple workers), every worker spawns its own scheduler, firing reminders N × per day. Replit's current single-process `uvicorn` setup avoids this, but it becomes a problem if the deployment config changes.  
**Recommended fix:** For the current single-worker deployment, this is acceptable. Document the single-worker requirement. Long-term, consider `APScheduler`'s `SQLAlchemyJobStore` for distributed-safe scheduling or use a dedicated task queue.

---

### MED-03 — RESEND_FROM_EMAIL defaults to unverified domain
**Status:** 🟡 WARNING  
**Location:** `app/services/email_service.py:31` — default `"reminders@credanta.com"`  
**Risk:** Resend requires the sender domain to be verified in the dashboard. If `credanta.com` is not verified with Resend's DNS records, all reminder emails will be rejected/bounced. The app will report success (Resend API call returns 200) but the email never reaches the recipient.  
**Recommended fix:** Verify `credanta.com` (or your chosen sender domain) in the Resend dashboard and confirm DNS records are live. Set `RESEND_FROM_EMAIL` explicitly in Replit Secrets.

---

### MED-04 — Duplicate Stripe API key assignment in webhook handler
**Status:** 🟡 WARNING  
**Location:** `app/main.py:1952` — `_stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")`  
**Risk:** The webhook handler directly sets `stripe.api_key` inline, duplicating the logic already centralized in `app/stripe_billing.py:_secret_key()`. If the key is sourced from a Replit Connector (the primary path in `stripe_billing.py`), the webhook handler's fallback won't find it via env var, causing webhook subscription-update logic to fail with an authentication error.  
**Recommended fix:** Replace the inline assignment with `from .stripe_billing import _secret_key; _stripe.api_key = _secret_key()`.

---

### MED-05 — Silent `except Exception: pass` blocks mask production errors
**Status:** 🟡 WARNING  
**Location:** `app/db.py:418–419` (`_ensure_sqlite_columns`), `app/admin.py` (multiple), `app/smart_categorize.py` (multiple)  
**Risk:** A broad `except Exception: pass` block in the DB migration function means any migration failure silently succeeds — tables may be missing without any log entry. Similarly, errors in admin metrics or document parsing are swallowed entirely.  
**Recommended fix:** Replace bare `pass` with at minimum `logging.error("[context] Migration/parse failed: %s", exc, exc_info=True)`. For the DB migration specifically, consider re-raising after logging.

---

### MED-06 — `AdminAccessLog` table has no admin UI viewer
**Status:** ✅ RESOLVED (`app/main.py` — `GET {ADMIN_ROUTE}/access-logs`; `app/templates/admin_access_logs.html`)  
**Location:** `app/main.py` — no admin route for `/admin/access-logs`  
**Risk:** The audit log system (built in the previous hardening task) faithfully records every admin access attempt to `admin_access_logs`, but there is no way to view these records without direct DB access. The security value of an audit log is zero if it can't be reviewed.  
**Resolution:** Added read-only `GET {ADMIN_ROUTE}/access-logs` route with filters for email (partial-match), result (authorised/denied/all), and date range (7d/30d/all time). Displays summary cards (total, authorised, denied, unique emails) and a paginated table (200-entry cap) with timestamp, email, route, IP, user agent, and result badge. Linked from all admin nav bars.

---

### MED-07 — No startup validation for required secrets
**Status:** ✅ RESOLVED (`app/security.py` — `validate_env()` expanded with two-tier severity)

All integration groups now checked at startup:

| Group | Keys | Severity |
|---|---|---|
| Session | `SESSION_SECRET` | Fatal in prod (RuntimeError) |
| Google OAuth | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Fatal in prod |
| Cloudflare Turnstile | `CLOUDFLARE_TURNSTILE_SITE_KEY`, `CLOUDFLARE_TURNSTILE_SECRET_KEY` | Fatal in prod |
| Stripe billing | `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PREMIUM_PRICE_ID`, `STRIPE_PREMIUM_PLUS_PRICE_ID` | ERROR in prod, WARNING in dev |
| Resend email | `RESEND_API_KEY` | ERROR in prod, WARNING in dev |
| Twilio SMS | `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER` | ERROR in prod (partial-config detection) |
| OpenAI AI | `OPENAI_API_KEY` | ERROR in prod, WARNING in dev |
| Admin | `ADMIN_ROUTE`, `ADMIN_EMAILS` | ERROR in prod, WARNING in dev |

---

## 🟢 Low Priority Issues

---

### LOW-01 — `X-XSS-Protection` header is deprecated in modern browsers
**Status:** 🟢 PASS (informational)  
**Location:** `app/security.py:489`  
**Risk:** This header is ignored by Chrome (removed in v78+), Firefox, and Safari. It only affects legacy IE11. Its presence is harmless but creates a false sense of XSS protection.  
**Recommended fix:** Remove once CSP (HIGH-01) is implemented; CSP is the proper XSS mitigation.

---

### LOW-02 — Recruiter share links have no default expiration
**Status:** ✅ RESOLVED (`app/main.py` — `share_create`; `app/templates/share.html`)  
**Location:** `app/main.py` — `share_create` endpoint, `expires_days` is optional with no default  
**Risk:** Links created without an expiry date persist forever unless manually revoked. A nurse who forgets to revoke a link after a job search has their credentials accessible indefinitely.  
**Resolution:** Default is now 90 days. If `expires_days` is empty or non-numeric the route sets `exp = now + 90d`. Users can choose 7, 30, or 90 days, or explicitly select "Never". The dropdown pre-selects "In 90 days (default)" to communicate the behaviour clearly.

---

### LOW-03 — Email templates are hardcoded f-strings (not Jinja2 templates)
**Status:** ✅ RESOLVED (`app/services/email_service.py`; `app/templates/email/`)  
**Location:** `app/services/email_service.py` — all email HTML is embedded as Python f-strings  
**Risk:** Maintenance burden. Updating email branding, wording, or links requires editing Python source files. No preview possible without sending. No support for different locales.  
**Resolution:** Three Jinja2 templates created at `app/templates/email/reminder.html`, `expired.html`, and `test.html`. A dedicated `jinja2.Environment` with `FileSystemLoader` renders them via a `_render(template_name, **ctx)` helper. The three `_build_*` f-string functions have been removed.

---

### LOW-04 — SQLite is single-file and may struggle under concurrent load
**Status:** ✅ RESOLVED (`app/db.py` — WAL mode + related pragmas enabled)

A SQLAlchemy `@event.listens_for(engine, "connect")` listener now runs three `PRAGMA` statements on every new connection:

| PRAGMA | Value | Reason |
|---|---|---|
| `journal_mode` | `WAL` | Concurrent readers during writes; no more "database is locked" errors under scheduler + web request overlap |
| `synchronous` | `NORMAL` | Safe durability with WAL (checkpoint guarantees it); meaningfully faster than the default `FULL` |
| `foreign_keys` | `ON` | SQLite ignores FK constraints unless set per-connection; enables referential integrity enforcement |

`_verify_wal_mode()` called from `init_db()` logs `journal_mode` and `synchronous` at startup and warns if WAL is not active.

Note: SQLite WAL mode is persistent in the database file after the first connection sets it, so subsequent connections inherit it even without the pragma. The per-connection pragma is belt-and-suspenders.

---

### LOW-05 — Resume enhancer AI path (OpenAI) not tested
**Status:** 🟢 PASS (informational)  
**Location:** `app/ai_docs.py`, `app/resume_enhancer.py`  
**Risk:** The OpenAI integration path exists and is referenced but the primary engine is rule-based. If `OPENAI_API_KEY` is set in production without testing, the AI code path may behave unexpectedly.  
**Recommended fix:** Either explicitly disable the AI path until tested, or add an integration test. Document clearly which code path is active by default.

---

## Area-by-Area Verdicts

| Area | Verdict | Notes |
|---|---|---|
| Authentication | 🟡 WARNING | SESSION_SECRET must be set (CRIT-02) |
| Authorization | 🟡 WARNING | ADMIN_EMAILS must be set (HIGH-05); BETA_MODE must be off (HIGH-02) |
| Document Uploads | 🟢 PASS | Excellent layered validation — magic bytes, threat scan, dedup, rate limit |
| Document Previews | 🟢 PASS | HMAC tokens, auth checks, safe MIME filtering all solid |
| Expiration Tracking | 🟢 PASS | Dashboard logic correct; 60-day window well-implemented |
| NIH Custom Rules | 🟢 PASS | State-specific 1yr/2yr rules with fallback date logic implemented |
| Packet Generation | 🟢 PASS | Zip-slip protected; path traversal protected |
| Recruiter Share Links | 🟢 PASS | 144-bit entropy tokens; HMAC download tokens; revocation works |
| Premium Feature Gating | 🟡 WARNING | BETA_MODE bypass (HIGH-02) must be disabled in production |
| Stripe Integration | 🟡 WARNING | No hardcoded keys ✅; webhook secret must be set (HIGH-03) |
| Email Reminders | 🟡 WARNING | Resend domain must be verified (MED-03); scheduler is single-process (MED-02) |
| SMS Reminders | 🟡 WARNING | KeyError on missing TWILIO_FROM_NUMBER (HIGH-06) must be fixed |
| Account Page | 🟢 PASS | Storage limits, MFA status, subscription all correct |
| Resume Enhancer | 🟢 PASS | Rule-based engine works; AI path optional |
| Analytics | 🟢 PASS | Internal event log; no third-party tracking |
| Mobile Responsiveness | 🟢 PASS | 10 breakpoints from 400px to 1000px; dark mode supported |
| Security Headers | 🟡 WARNING | Missing CSP (HIGH-01); all other headers present |
| CSRF Protection | 🔴 FAIL | No CSRF middleware (CRIT-03) |
| Error Handling | 🔴 FAIL | No global 500 handler (CRIT-01); silent `except: pass` blocks (MED-05) |
| Session Security | 🔴 FAIL | SESSION_SECRET required (CRIT-02) |
| API Key Exposure | 🟢 PASS | No hardcoded keys; all from env vars |
| Admin Route Protection | 🟢 PASS | ADMIN_ROUTE configurable; /admin returns 404; audit log active |
| Cloudflare Turnstile | 🟡 WARNING | Fails open without secret key (HIGH-04) |

---

*Report generated from static analysis, codebase exploration, and targeted grep scans.*
