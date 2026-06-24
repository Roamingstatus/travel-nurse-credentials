# RAILWAY_POST_LAUNCH_CHECK

**Date:** 2026-06-24  
**Production URL:** `https://travel-nurse-credentials-production.up.railway.app`

---

## Deployment configuration

| Check | Status | Notes |
|---|---|---|
| Start command | **PASS** | `python run.py` (Nixpacks auto-detect) |
| Bind address | **PASS** | `0.0.0.0` in `run.py` |
| PORT | **PASS** | `int(os.environ.get("PORT", "5000"))` |
| Health route | **PASS** | `GET /healthz` (liveness only) |
| Procfile in repo | **WARNING** | Not committed — configure in Railway dashboard |
| Gunicorn multi-worker | **WARNING** | Not used; single uvicorn + in-process scheduler |

---

## Required Railway variables

| Variable | Purpose | Status |
|---|---|---|
| `SESSION_SECRET` | Signed cookies | Required |
| `APP_ENV=production` | Production mode | Required |
| `APP_BASE_URL` | OAuth/email links | Recommended |
| `DATABASE_URL` | PostgreSQL | **Required for persistent data** |
| `GOOGLE_CLIENT_ID` | OAuth | Required for Google login |
| `GOOGLE_CLIENT_SECRET` | OAuth (`GOCSPX-...`) | Required for Google login |
| `CLOUDFLARE_TURNSTILE_SITE_KEY` | Bot protection | Required in prod |
| `CLOUDFLARE_TURNSTILE_SECRET_KEY` | Bot protection | Required in prod |
| `OPENAI_API_KEY` | Resume AI | Required in prod startup |
| `ADMIN_ROUTE` | Secret admin path | Required |
| `ADMIN_EMAILS` | Admin allowlist | Required |
| `RESEND_API_KEY` / `RESEND_FROM_EMAIL` | Email | Recommended |
| `STRIPE_*` | Billing | Required for paid tiers |
| `REQUIRE_TURNSTILE_FOR_UPLOADS=false` | Skip upload Turnstile | Optional |

---

## OAuth callback URLs (Google Cloud Console)

Must include **exact** URIs:

```
https://travel-nurse-credentials-production.up.railway.app/auth/google/callback
http://localhost:5000/auth/google/callback
```

Startup logs show expected callback via `[oauth] Expected callback URL:`.

---

## PostgreSQL

App now reads `DATABASE_URL` when set (`app/db.py`). Railway Postgres plugin injects this automatically.

Without PostgreSQL or a mounted volume, SQLite on ephemeral disk **will lose data on redeploy**.

---

## Logging safety

| Item | Status |
|---|---|
| Passwords in logs | **PASS** — not logged |
| API keys in logs | **PASS** — masked in security monitor |
| Resume text in logs | **PASS** — tested in `test_resume_ai_endpoint.py` |
| OAuth secrets in logs | **PASS** — suffix-only diagnostics |

Check deploy logs for:
```
[oauth] Google Client ID configured: YES | Google Client Secret configured: YES
[db] Using DATABASE_URL backend (PostgreSQL)
```

---

## Post-deploy smoke test

1. `GET /healthz` → 200
2. `GET /login` → Google button visible (if OAuth configured)
3. Email login + logout
4. Upload PDF as logged-in user
5. Resume enhancer (premium user)
6. Share link create → view → download (with `dl` token)
7. Admin route returns 404 at `/admin`; works at secret `ADMIN_ROUTE`

---

## Known Railway risks

| Risk | Severity |
|---|---|
| Wrong `GOOGLE_CLIENT_SECRET` (Client ID pasted) | **CRITICAL** — `401 invalid_client` |
| Missing `DATABASE_URL` | **HIGH** — data loss on redeploy |
| In-memory rate limits | **MEDIUM** — per-instance only |
| Turnstile fail-open on network error | **MEDIUM** — see security audit |

See also: `OAUTH_DEBUG_REPORT.md`, `POST_LAUNCH_FULL_APP_AUDIT.md`
