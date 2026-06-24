# OAUTH_DEBUG_REPORT

**Date:** 2026-06-24  
**Issue:** Google login returns `Error 401: invalid_client` — "The OAuth client was not found"  
**Environment:** Railway production (`travel-nurse-credentials-production.up.railway.app`)

---

## 1. Environment variable names (code audit)

The app uses **exactly two** variables for Google OAuth. No aliases or fallbacks exist.

| Variable | Used? | Files |
|---|---|---|
| `GOOGLE_CLIENT_ID` | **Yes** | `app/auth.py`, `app/security.py`, `start.sh`, `.env.example` |
| `GOOGLE_CLIENT_SECRET` | **Yes** | `app/auth.py`, `app/security.py`, `start.sh`, `.env.example` |
| `GOOGLE_OAUTH_CLIENT_ID` | No | — |
| `GOOGLE_OAUTH_CLIENT_SECRET` | No | — |
| `GOOGLE_CLIENTID` | No | — |
| `GOOGLE_SECRET` | No | — |

**Related (optional):**

| Variable | Purpose |
|---|---|
| `APP_BASE_URL` | Startup callback URL hint for logs (e.g. `https://travel-nurse-credentials-production.up.railway.app`) |
| `RAILWAY_PUBLIC_DOMAIN` | Fallback for callback URL hint if `APP_BASE_URL` unset |

---

## 2. Hardcoded credentials

**None found.** Grep across the repo found no hardcoded `googleusercontent.com` or `GOCSPX-` values. All Google OAuth config is read from environment variables at runtime.

---

## 3. Root cause of `invalid_client`

Google returns `401 invalid_client` when the **client ID + client secret pair** sent to Google's token endpoint is wrong.

**Most likely cause on Railway:** `GOOGLE_CLIENT_SECRET` is set to the **Client ID** instead of the actual **Client secret**.

Evidence:
- Local `.env` had `GOOGLE_CLIENT_SECRET` identical to `GOOGLE_CLIENT_ID` (both ending in `.apps.googleusercontent.com`).
- Google Client secrets always start with `GOCSPX-`, never with a numeric project prefix or `.apps.googleusercontent.com`.
- The login button still appears when both vars are non-empty (`google_configured()` only checks presence, not validity).

**Secondary checks if secret is correct:**
1. Client ID in Railway must match the OAuth 2.0 Web client in Google Cloud Console exactly.
2. Authorized redirect URI in Google Console must include:
   `https://travel-nurse-credentials-production.up.railway.app/auth/google/callback`
3. OAuth client must not be deleted or from a different Google Cloud project.

---

## 4. Callback URL behavior

| Step | URL |
|---|---|
| OAuth start route | `GET /auth/google` |
| OAuth callback route | `GET /auth/google/callback` |
| Production callback (expected) | `https://travel-nurse-credentials-production.up.railway.app/auth/google/callback` |
| Local callback | `http://localhost:5000/auth/google/callback` |

**How redirect URI is built (`app/main.py`):**
- Uses `request.url_for("google_callback")` from the incoming request Host header.
- Upgrades `http://` → `https://` for non-localhost hosts (Railway-safe).
- Does **not** use a hardcoded client ID or callback.

---

## 5. Safe startup logging added

On every startup, `log_google_oauth_diagnostics()` in `app/auth.py` now logs:

```
[oauth] Google Client ID configured: YES/NO | Google Client Secret configured: YES/NO | Client ID suffix: ...<last 12 chars>
[oauth] Expected callback URL: <url or hint>
```

If misconfigured, also logs (no secrets):

```
[oauth] GOOGLE_CLIENT_SECRET equals GOOGLE_CLIENT_ID — causes Google error 401 invalid_client
[oauth] GOOGLE_CLIENT_SECRET looks like a Client ID, not a secret — causes 401 invalid_client
```

On OAuth start (`GET /auth/google`), logs:

```
[oauth] redirect_uri sent to Google: <exact URL>
[oauth] APP_BASE_URL callback hint: <expected URL>
```

---

## 6. Values present (local dev, no secrets)

| Check | Result |
|---|---|
| `GOOGLE_CLIENT_ID` present | YES |
| `GOOGLE_CLIENT_SECRET` present | **NO** (cleared locally — was incorrectly set to Client ID) |
| Hardcoded OAuth values | None |
| Email/password login | Unchanged |

---

## 7. Files changed

| File | Change |
|---|---|
| `app/auth.py` | Added `_oauth_env()`, `google_client_id()`, `google_client_secret()`, `expected_google_callback_url()`, `log_google_oauth_diagnostics()`; OAuth registration uses normalized env readers |
| `app/security.py` | `validate_env()` uses normalized readers + calls diagnostics at startup |
| `app/main.py` | OAuth start logs callback URL + APP_BASE_URL hint |
| `.env.example` | Documented correct secret format (`GOCSPX-`) and production callback URI |
| `.env` | Removed incorrect `GOOGLE_CLIENT_SECRET` (was duplicate of Client ID) |
| `OAUTH_DEBUG_REPORT.md` | This report |

---

## 8. Exact fix to apply on Railway

1. Open **Google Cloud Console** → APIs & Services → Credentials → your OAuth 2.0 Web client.
2. Copy the **Client ID** → set Railway variable `GOOGLE_CLIENT_ID`.
3. Copy the **Client secret** (starts with `GOCSPX-`) → set Railway variable `GOOGLE_CLIENT_SECRET`.
   - Do **not** paste the Client ID into the secret field.
4. Under **Authorized redirect URIs**, confirm this exact URL is listed:
   ```
   https://travel-nurse-credentials-production.up.railway.app/auth/google/callback
   ```
5. (Recommended) Set Railway variable:
   ```
   APP_BASE_URL=https://travel-nurse-credentials-production.up.railway.app
   ```
6. Redeploy / restart the Railway service.
7. Check deploy logs for:
   ```
   [oauth] Google Client ID configured: YES | Google Client Secret configured: YES | Client ID suffix: ...<suffix>
   [oauth] Expected callback URL: https://travel-nurse-credentials-production.up.railway.app/auth/google/callback
   ```
   If you see the `GOOGLE_CLIENT_SECRET equals GOOGLE_CLIENT_ID` error, the secret is still wrong.

---

## 9. Email/password login

No changes to email/password auth routes or logic. Google OAuth remains optional; missing or invalid Google config does not block other sign-in methods.
