# BETA_AUTH_AND_ACCESS_REPORT

**Date:** 2026-06-12
**Scope:** Beta authentication architecture, email/password auth, brute-force protection, bot protection, CSV injection hardening, and the `BETA_UNLOCK_ALL_FEATURES` flag.

---

## 1. Authentication Methods

### 1a. Google OAuth (pre-existing)

| Property | Detail |
|---|---|
| Provider | Google OAuth 2.0 via Authlib |
| Callback URL | `/auth/google/callback` |
| Session | Starlette signed cookie session |
| Required secrets | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` |
| Availability | Optional. App functions fully with email/password if Google is not configured. |

When `GOOGLE_CLIENT_ID` or `GOOGLE_CLIENT_SECRET` are absent the app logs a warning at startup (previously fatal — **downgraded** to non-fatal in `app/security.py: validate_env()`). The Google sign-in button is hidden from the login/register pages.

### 1b. Email / Password (new)

| Property | Detail |
|---|---|
| Hashing | bcrypt, cost factor 12 |
| Storage | `users.password_hash` column (added migration) |
| Provider tag | `users.auth_provider = 'email'` |
| `google_sub` field | Populated with `email:<uuid4>` placeholder to satisfy unique constraint |
| Timing safety | Dummy bcrypt check runs even when email is unregistered |
| Password minimum | 12 characters; blocked against a common-password list |

**New routes:**

| Method | Path | Purpose |
|---|---|---|
| GET | `/auth/register` | Registration form |
| POST | `/auth/register` | Create account |
| POST | `/auth/login-email` | Login with email + password |
| GET | `/auth/forgot-password` | Forgot-password form |
| POST | `/auth/forgot-password` | Initiate password reset |
| GET | `/auth/reset-password?token=<tok>` | Set-new-password form |
| POST | `/auth/reset-password` | Apply new password |

---

## 2. Login Page Redesign

The login page (`/login`) was redesigned to a **centered card layout** (Cloudflare-style) replacing the previous two-column hero layout.

**Key elements:**

- Credanta logo at top center
- `Sign in to Credanta` heading + one-line pitch subtitle
- **OAuth buttons** row — Google (live), Apple (greyed out, "Soon"), GitHub (greyed out, "Soon")
- `or` divider
- Email + password fields with show/hide password toggle
- Cloudflare Turnstile widget (below password field)
- `Continue with Email` submit button
- `Create account · Forgot password?` secondary links
- Beta note: "Credanta is currently in beta. All features are available while we improve the platform."
- Footer: Privacy · Security · Contact · Theme toggle · nexusGarden link
- Flash message area (error/success/info styles)
- Body class: `auth-pg` — hides sidebar, topbar, footer, and trial pill

Same card layout is used for `/auth/register`, `/auth/forgot-password`, and `/auth/reset-password`.

---

## 3. Brute-Force Protection

### 3a. Per-IP Rate Limiting

All new auth endpoints apply sliding-window IP-based limits using `_RateLimiter` (in `app/security.py`):

| Limiter | Endpoint | Limit | Window |
|---|---|---|---|
| `login_email_limiter` | `POST /auth/login-email` | 10 req | 15 min |
| `register_limiter` | `POST /auth/register` | 5 req | 1 hour |
| `forgot_pw_limiter` | `POST /auth/forgot-password` | 5 req | 1 hour |

Returns HTTP 429 on breach.

### 3b. Per-Email Rate Limiting

`_EmailRateLimiter` (added to `app/security.py`) applies limits keyed by the submitted email address, regardless of IP:

| Limiter | Endpoint | Limit | Window |
|---|---|---|---|
| `login_email_by_email_limiter` | `POST /auth/login-email` | 5 attempts | 15 min |
| `forgot_pw_by_email_limiter` | `POST /auth/forgot-password` | 3 attempts | 1 hour |

Both limiters log to the security audit trail (`log_security_event`). On breach the user sees a generic "Too many attempts" message; the forgot-password endpoint always returns a generic success message regardless of whether the email exists.

### 3c. Account-Level Lockout

Tracked in `app/email_auth.py` and the `users` table:

| Column | Purpose |
|---|---|
| `failed_login_count` | Consecutive failures in the current window |
| `failed_login_reset_at` | Start of the current failure window (60-min window) |
| `lockout_until` | UTC timestamp when account lock expires |

- **Threshold:** 10 failures within 60 minutes → 15-minute account lockout
- Lockout is checked **before** the password verify step
- On successful login all failure counters are cleared
- Password reset via `/auth/reset-password` also clears the lockout

---

## 4. Bot Protection (Turnstile + Honeypot)

### 4a. Cloudflare Turnstile

Turnstile (`cf-turnstile-response`) is verified server-side on every auth POST using `verify_turnstile()` from `app/security.py`. The Turnstile widget uses `data-theme="auto"` so it inherits the user's light/dark preference.

Turnstile failures are logged as `turnstile_failed` security events and redirect back to the form with an error message. The site key is injected from `CLOUDFLARE_TURNSTILE_SITE_KEY` (already set).

### 4b. Honeypot Field

A hidden `<input name="website">` field is included in the registration and email-login forms:

```html
<div class="auth-honeypot" aria-hidden="true">
  <input type="text" name="website" tabindex="-1" autocomplete="off" />
</div>
```

CSS: `position: absolute; left: -9999px; top: -9999px; opacity: 0; pointer-events: none;`

Bots that fill all visible fields will populate `website`. The server checks this field first; if non-empty it returns a **fake success response** (redirects to `/login` with a "Account created" flash) so bots cannot detect the honeypot. The event is logged as `auth_honeypot_triggered`.

---

## 5. Input Validation

All validation helpers live in `app/security.py`:

| Function | Purpose |
|---|---|
| `validate_email_format(email)` | RFC-5321 format check, max 254 chars, lowercase normalise |
| `validate_name(name)` | Strip HTML tags, max 80 chars |
| `validate_password_strength(plain)` | Min 12 chars; common-password blocklist |
| `is_common_password(plain)` | Returns True if password appears in blocklist |

Suspicious payload check (XSS probing) on name and email fields in registration — logs `suspicious_auth_payload` and returns a generic error.

---

## 6. CSV Injection Protection

`sanitize_csv_cell(value: str) -> str` (added to `app/security.py`) prefixes any value beginning with `=`, `+`, `-`, `@`, `\t`, or `\r` with an apostrophe (`'`), preventing formula injection when CSV data is opened in Excel or Google Sheets.

**Dangerous prefixes blocked:** `= + - @ \t \r`

Apply to every user-controlled string written into CSV exports (e.g., admin export, document name fields).

---

## 7. `BETA_UNLOCK_ALL_FEATURES` Flag

### Behaviour

When the environment variable `BETA_UNLOCK_ALL_FEATURES=true` (or the existing `BETA_MODE=true`) is set:

1. **`app/premium.py`** — `_BETA_MODE` returns `True`, causing `has_premium()` and `has_premium_plus()` to return `True` for **all** users regardless of their `subscription_tier`. No Stripe session is checked.
2. **`app/main.py: render()`** — injects `beta_unlock=True` into every Jinja2 template context. Templates can use `{% if beta_unlock %}` to suppress upgrade banners, premium badges, or paywall modals.
3. Stripe code, subscription models, and all premium feature logic are **preserved unchanged** — only the gating is bypassed. Removing the flag restores standard tier-based access immediately with no migration.

### Template usage example

```jinja2
{% if not beta_unlock %}
  <a href="/upgrade" class="upgrade-cta">Upgrade to Premium</a>
{% else %}
  <span class="beta-badge">Beta</span>
{% endif %}
```

### Security note

`BETA_UNLOCK_ALL_FEATURES` is a server-side environment variable. It does not appear in any client-side output and cannot be set by users.

---

## 8. DB Schema Changes

The following columns were added to the `users` table via `_ensure_sqlite_columns()` in `app/db.py` (safe, additive-only ALTER TABLE migrations):

| Column | Type | Purpose |
|---|---|---|
| `password_hash` | TEXT | bcrypt hash for email-auth users |
| `auth_provider` | TEXT (default `'google'`) | `'google'` or `'email'` |
| `failed_login_count` | INTEGER (default 0) | Consecutive login failures |
| `failed_login_reset_at` | DATETIME | Window start for failure counting |
| `lockout_until` | DATETIME | Account lockout expiry |
| `password_reset_token` | TEXT | Raw reset token (stored plaintext; short-lived) |
| `password_reset_expires_at` | DATETIME | Reset token expiry (1 hour TTL) |

`google_sub` column nullable constraint was softened; email-auth users populate it with `email:<uuid4>`.

---

## 9. Password Reset Flow

1. User submits email at `POST /auth/forgot-password`
2. Per-IP and per-email rate limits are enforced
3. Turnstile is verified
4. A 48-byte `secrets.token_urlsafe` token is generated and stored in `users.password_reset_token` with a 1-hour TTL
5. `send_password_reset_email()` in `app/services/email_service.py` sends the reset link via Resend (graceful no-op if `RESEND_API_KEY` is not set)
6. A **generic success message** is always shown regardless of whether the email is registered (prevents email enumeration)
7. User clicks reset link → `GET /auth/reset-password?token=<tok>`
8. User submits new password → `POST /auth/reset-password`
9. `consume_reset_token()` verifies the token, checks TTL, updates `password_hash`, clears the token, clears lockout state, and commits

---

## 10. Files Changed / Added

| File | Change |
|---|---|
| `app/security.py` | Added `login_email_limiter`, `register_limiter`, `forgot_pw_limiter`, `_EmailRateLimiter`, `login_email_by_email_limiter`, `forgot_pw_by_email_limiter`, `validate_email_format`, `validate_name`, `validate_password_strength`, `is_common_password`, `sanitize_csv_cell`; Google OAuth downgraded from fatal to error in `validate_env()` |
| `app/email_auth.py` | **New.** bcrypt hash helpers, `register_email_user`, `authenticate_email_user` with lockout, `create_reset_token`, `consume_reset_token` |
| `app/db.py` | 7 new `users` columns + `_ensure_sqlite_columns()` migrations |
| `app/premium.py` | `_BETA_MODE` now also checks `BETA_UNLOCK_ALL_FEATURES` env var |
| `app/main.py` | New security + email_auth imports; 4 new auth route pairs; `beta_unlock` injected in `render()` |
| `app/services/email_service.py` | Added `send_password_reset_email()` |
| `app/templates/login.html` | **Redesigned.** Centered card, OAuth buttons, email form, Turnstile, honeypot |
| `app/templates/register.html` | **New.** Registration form with all validations |
| `app/templates/forgot_password.html` | **New.** Forgot-password form |
| `app/templates/reset_password.html` | **New.** New-password form |
| `app/static/style.v5.css` | Appended auth page styles (`auth-pg`, `auth-center`, `auth-card`, all sub-components) |
| `requirements.txt` | `bcrypt>=4.0` added |
| `BETA_AUTH_AND_ACCESS_REPORT.md` | **This file** |
