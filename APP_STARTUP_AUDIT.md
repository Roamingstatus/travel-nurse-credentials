# APP_STARTUP_AUDIT

**Date:** 2026-06-24  
**App:** Credanta (`travel-nurse-credentials`)

---

## Summary

| Check | Status |
|---|---|
| Backend starts locally | **PASS** |
| Frontend build (production) | **PASS** (Jinja2 SSR — no separate build step) |
| Mockup sandbox (Vite) | **WARNING** (dev artifact only; not production) |
| Missing env vars crash app | **PASS** (dev warns; prod fatals only Turnstile/OpenAI/session) |
| Railway start command | **PASS** (`python run.py` — no Procfile in repo) |
| Binds `0.0.0.0` | **PASS** (`run.py`) |
| Uses `PORT` env | **PASS** (default `5000`) |
| PostgreSQL via `DATABASE_URL` | **PASS** (added in this audit) |
| Health route | **PASS** (`GET /healthz`) |

---

## Backend entry

| File | Role |
|---|---|
| `run.py` | Loads `.env`, runs `uvicorn.run("app.main:app", host="0.0.0.0", port=PORT)` |
| `start.sh` | Requires `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `SESSION_SECRET` |
| `app/main.py` | FastAPI app, middleware, routes |

**Local start:** `.venv\Scripts\python.exe run.py`  
**Health check:** `GET http://localhost:5000/healthz` → `{"status":"ok"}`

---

## Frontend

Production UI is **server-rendered**:
- Templates: `app/templates/` (41 HTML files)
- Static assets: `app/static/` (CSS/JS/images)
- No webpack/Vite build required for deployment

Dev-only React mockups: `artifacts/mockup-sandbox/` (`npm run build` available but not wired to prod).

---

## Environment variables at startup

`validate_env()` in `app/security.py` runs on startup.

| Severity | Variables |
|---|---|
| Fatal in production | `SESSION_SECRET`, `CLOUDFLARE_TURNSTILE_*`, `OPENAI_API_KEY` |
| Error (feature disabled) | Google OAuth, Stripe, Resend, Twilio, admin config |
| Optional | `APP_BASE_URL`, `RAILWAY_PUBLIC_DOMAIN`, `REQUIRE_TURNSTILE_FOR_UPLOADS` |

Missing Google OAuth does **not** crash the app — email/password login remains available.

---

## Database

| Mode | Config |
|---|---|
| SQLite (local default) | `CREDANTA_DB_PATH` or `app/data/app.db` |
| PostgreSQL (Railway) | `DATABASE_URL` (supports `postgres://` and `postgresql://`) |

SQLite pragmas (WAL, foreign keys) apply only on SQLite connections.

**Dependency added:** `psycopg2-binary` in `requirements.txt`.

---

## OAuth startup diagnostics

`log_google_oauth_diagnostics()` logs (no secrets):
- Client ID configured YES/NO
- Client secret configured YES/NO
- Client ID suffix (last 12 chars)
- Expected callback URL

---

## Test run (startup-related)

```
pytest tests/ → 431 passed, 20 failed (pre-existing template/tier/recruiter test env issues)
pytest tests/test_post_launch_security.py → 2 passed
```

---

## Recommendations

1. Set `APP_BASE_URL` on Railway for OAuth callback diagnostics.
2. Mount persistent volume or use PostgreSQL + object storage on Railway (SQLite alone loses data on ephemeral disks).
3. Extend `/healthz` with DB connectivity check for Railway readiness probes (optional).
