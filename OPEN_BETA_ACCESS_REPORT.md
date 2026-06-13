# OPEN_BETA_ACCESS_REPORT

**Date:** 2026-06-12
**Scope:** Open-beta access model — premium UI hidden, all features unlocked, Feature Hub page added.

---

## 1. Premium UI — Hidden (not deleted)

All premium-upgrade-facing UI is hidden during the open beta. **No files were deleted.** Code is preserved with the comment *"Preserved for future monetization. Disabled during open beta."*

| Element | Status |
|---|---|
| Sidebar "Premium" link | Hidden when `beta_unlock=true`; replaced with Feature Hub |
| Sidebar "Premium+" link | Hidden when `beta_unlock=true` |
| Mobile bottom nav "Premium" item | Hidden when `beta_unlock=true`; replaced with Feature Hub |
| 7-day trial banner / pill | Hidden when `beta_unlock=true` (wrapped in `{% if show_trial_banner and not beta_unlock %}`) |
| Trial "Start Trial" button | Not shown (banner suppressed) |
| Trial modal | Not shown (banner suppressed) |

The trial banner HTML + JS + modal + CSS remains fully intact in the codebase — re-enable by setting `BETA_UNLOCK_ALL_FEATURES=false`.

---

## 2. Features Unlocked

With `BETA_UNLOCK_ALL_FEATURES=true`, every logged-in user has full access to:

| Feature | Backend gate | Status |
|---|---|---|
| Packet generation (`/packet`) | `require_premium(user)` → passes (beta flag) | ✅ Unlocked |
| Recruiter share links (`/share`) | `require_premium_plus(user)` → passes (beta flag) | ✅ Unlocked |
| Calendar feed (`/premium/calendar`) | `require_premium_plus(user)` → passes (beta flag) | ✅ Unlocked |
| Expiration reminders (`/premium/reminders/*`) | `require_premium(user)` → passes (beta flag) | ✅ Unlocked |
| Resume enhancer (`/premium/resume/enhance`) | `require_premium(user)` → passes (beta flag) | ✅ Unlocked |
| Document preview | Available to all users | ✅ Unlocked |
| Export/download | Available to all users | ✅ Unlocked |
| Account/security settings | Available to all users | ✅ Unlocked |

**How it works:** `app/premium.py: _BETA_MODE` returns `True` when either `BETA_UNLOCK_ALL_FEATURES=true` or `BETA_MODE=true`. `has_premium()` and `has_premium_plus()` both return `True` for any logged-in user when `_BETA_MODE` is active. All `require_premium()` / `require_premium_plus()` calls then pass without raising 403.

Admin pages (`/admin/*`, admin-route via `ADMIN_ROUTE` env var) still require the user's email to be in `ADMIN_EMAILS` — the beta flag does not bypass admin access.

---

## 3. New Navigation

### Sidebar (when `beta_unlock=true`)
```
Dashboard
Portfolio
Resume Enhancer
Shared Links        ← unlocked for all
Download Packet     ← unlocked for all
Feature Hub         ← new
Account
Security
Feedback            ← sidebar button triggers feedback modal
Sign out
```

### Sidebar (when `beta_unlock=false`)
Original premium-tier conditional logic is preserved intact.

### Mobile bottom nav
`Feature Hub` replaces the `Premium` item when `beta_unlock=true`. Original Premium item preserved in the `{% else %}` branch.

---

## 4. Feature Hub Page

**Route:** `GET /feature-hub`

**Template:** `app/templates/feature_hub.html`

Displays six feature cards with on/off toggles. User preferences are stored per-user in the database (see Section 5). All features default to **enabled** for new users.

| # | Feature key | Title |
|---|---|---|
| 1 | `expiration_reminders` | Expiration Reminders |
| 2 | `submission_packets` | Submission Packets |
| 3 | `recruiter_share_links` | Recruiter Share Links |
| 4 | `resume_enhancer` | Resume Enhancer |
| 5 | `smart_checklist` | Smart Checklist |
| 6 | `feedback_mode` | Feedback Mode |

Toggle changes are saved via `POST /feature-hub/toggle` (JSON, requires CSRF token). The toggle saves immediately with optimistic UI and reverts on server error.

---

## 5. Database — New Table

**`user_feature_preferences`**

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | Auto-increment |
| `user_id` | INTEGER FK → users | Cascade delete |
| `feature_key` | VARCHAR | e.g. `expiration_reminders` |
| `enabled` | INTEGER (bool) | Default 1 (true) |
| `created_at` | DATETIME | Auto |
| `updated_at` | DATETIME | Auto |

Unique index on `(user_id, feature_key)`. Table created via `_ensure_sqlite_columns()` in `app/db.py` — safe, additive-only, no data migration required. `UserFeaturePreference` SQLAlchemy model added to `app/db.py`; relationship added to `User.feature_preferences`.

Missing rows default to `enabled=True` in `_get_feature_prefs()` — no migration needed for existing users.

---

## 6. Stripe Code — Preserved

Nothing in the Stripe integration was touched:

| Area | Status |
|---|---|
| `/billing/webhook` route | Unchanged |
| `/billing/start-trial` route | Unchanged |
| `app/premium.py` `has_premium()` / `has_premium_plus()` | Preserved — beta flag is a thin override |
| `app/db.py` `subscription_tier`, `stripe_customer_id`, `stripe_subscription_id` | Unchanged |
| Premium page files (`/premium`, `premium.html`) | Not deleted — just not linked from nav during beta |
| Pricing logic `tier_for_price_id()` | Unchanged |
| Stripe webhook subscription update / cancellation | Unchanged |

Removing `BETA_UNLOCK_ALL_FEATURES=true` immediately restores full Stripe-based gating with no migration.

---

## 7. Copy Updates

| Old text | New / hidden |
|---|---|
| "Upgrade to Premium" | Hidden behind `beta_unlock` flag in templates |
| "Premium required" | Not shown (gate passes in beta) |
| "Start Trial" | Not shown (trial banner hidden) |
| Beta note | Added to Feature Hub page: *"Credanta is currently in open beta. All features are available while we improve reliability, usability, and workflows."* |

---

## 8. Files Changed / Added

| File | Change |
|---|---|
| `app/db.py` | Added `UserFeaturePreference` model + `user_feature_preferences` table migration in `_ensure_sqlite_columns()` + `feature_preferences` relationship on `User` |
| `app/main.py` | Imported `UserFeaturePreference`; added `_FEATURE_HUB_FEATURES` constant, `_get_feature_prefs()` helper, `GET /feature-hub`, `POST /feature-hub/toggle` routes |
| `app/templates/base.html` | Sidebar: added `beta_unlock` branch (Feature Hub + unlocked links), Feedback sidebar button, preserved premium block in `else`. Trial banner: wrapped in `{% if not beta_unlock %}`. Mobile nav: Feature Hub replaces Premium when `beta_unlock=true` |
| `app/templates/feature_hub.html` | **New.** Feature Hub page with 6 toggle cards |
| `app/static/style.v5.css` | Added `.sidebar-link--btn` + full Feature Hub page styles (`.fh-*`) |
| `OPEN_BETA_ACCESS_REPORT.md` | **This file** |

---

## 9. Remaining Monetization Code Locations

For future re-enablement:

| Location | What it contains |
|---|---|
| `app/premium.py` | `has_premium()`, `has_premium_plus()`, `require_premium()`, `require_premium_plus()`, feature lists |
| `app/main.py` lines ~2770–2830 | Stripe webhook handler, tier assignment, `tier_for_price_id()` |
| `app/main.py` `/billing/*` routes | `/billing/start-trial`, `/billing/checkout`, `/billing/webhook`, `/billing/portal` |
| `app/main.py` `/premium*` routes | All premium feature routes |
| `app/templates/premium.html` | Premium upgrade page (not deleted) |
| `app/templates/base.html` | Trial pill HTML + JS + modal (wrapped in `{% if not beta_unlock %}`) |
| `app/static/style.v5.css` `.trial-*` | Trial banner and modal styles |
| `app/db.py` `subscription_tier`, `stripe_*` columns | Subscription state |

Re-enable monetization: set `BETA_UNLOCK_ALL_FEATURES=false` (or remove the env var) and the full premium/Stripe experience returns immediately.
