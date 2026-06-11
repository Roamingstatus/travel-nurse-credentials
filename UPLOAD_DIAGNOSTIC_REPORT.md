# Upload Diagnostic Report — Credanta Production
**Date:** June 11, 2026  
**Environment:** Production (`credantaapp.com`)  
**Status:** Upload path fully audited — 1 confirmed blocking defect, 4 secondary issues

---

## Executive Summary

Every document upload attempt by a non-premium user fails in production with a silent bounce back to the upload page. The root cause is a **field-name mismatch between Cloudflare Turnstile and FastAPI** that has always existed in production. A code fix has been written and merged into the local codebase but **has not yet been deployed** to production. Additionally, four secondary issues were found ranging from a UX silencing bug to a HEIC format rejection mismatch and data persistence concerns.

---

## 1. Root Cause Identified

### Cloudflare Turnstile field name mismatch

**Severity:** CRITICAL — blocks 100% of non-premium uploads  
**Component:** `POST /documents/upload` → Turnstile server-side verification  
**Status:** Code fix written; **awaiting production deployment**

#### What happens

Cloudflare's Turnstile widget injects a hidden form field named exactly `cf-turnstile-response` (hyphenated) into the DOM form. The frontend sends this in the `FormData` payload via XHR.

The FastAPI route previously declared the parameter as:
```python
cf_turnstile_response: str = Form("")
```

Python function parameters cannot contain hyphens. FastAPI's `Form()` dependency looks for a field literally named `cf_turnstile_response` (underscore). The browser sends `cf-turnstile-response` (hyphen). **These are two different keys.** The FastAPI parameter always received an empty string `""`.

`verify_turnstile("", ip)` then executes:
```python
if not response_token:          # "" is falsy
    logger.warning("[security] Turnstile: missing response token from client")
    return False                # ← upload is rejected
```

Because `CLOUDFLARE_TURNSTILE_SECRET_KEY` **is set** in production (but not locally), the guard is live only in production. The mismatch is silent in development and lethal in production.

#### Evidence from production logs

Every single upload attempt produced this exact sequence — no exceptions:

```
WARNING:credanta.security:[security] Turnstile: missing response token from client
POST /documents/upload HTTP/1.1  →  302 Found
GET  /documents/upload HTTP/1.1  →  200 OK     ← bounced back
```

No upload ever reached the storage or database layer.

#### Files involved

| File | Line | Issue |
|------|------|-------|
| `app/main.py` | 827 (old) | `cf_turnstile_response: str = Form("")` — wrong key |
| `app/security.py` | 535–537 | Empty token → returns `False` → upload blocked |
| `app/templates/upload.html` | 4–6, 79–80 | Widget renders for non-premium users only |

#### The fix (already in codebase, not yet deployed)

```python
# app/main.py — upload route
if not has_premium(user):
    _form = await request.form()
    cf_turnstile_response = str(_form.get("cf-turnstile-response", "") or "")
    ...
    if not verify_turnstile(cf_turnstile_response, ip):
        ...
```

`request.form()` is cached by Starlette after the first parse, so calling it here does not double-consume the ASGI receive stream (the CSRF middleware already buffered and replayed it). The fix reads the token with the exact hyphenated key that Cloudflare sends.

---

## 2. Additional Issues Found

### 2a. XHR redirect transparency silences upload errors

**Severity:** HIGH — hides failures from the user  
**Component:** `app/templates/upload.html` lines 534–542  

The upload is submitted via `XMLHttpRequest`. When the server rejects the upload and responds `302 → GET /documents/upload`, the browser automatically follows the redirect. `xhr.status` resolves to `200` (the final GET response), not the intermediate 302.

The XHR load handler checks:
```javascript
if (xhr.status >= 200 && xhr.status < 400) {
    window.location.href = "/documents";   // ← runs even on failure
}
```

On a failed upload, the user is navigated to `/documents` (the empty portfolio) rather than staying on the upload page to see the error. The flash message set in the session appears briefly on `/documents` but the scan overlay shows "Uploading your document…" right before the redirect — the visual feedback is wrong.

**Recommended fix:** Instead of a server-side `RedirectResponse`, return a JSON error payload for the XHR path. Check `request.headers.get("X-Requested-With")` or the `Accept` header to distinguish XHR from browser form submissions, then return `{"ok": false, "error": "..."}` with HTTP 400, which the JS can display in the scan overlay.

---

### 2b. `APP_ENV` not set → app runs as "development" in production

**Severity:** MEDIUM — degrades security posture  
**Component:** `app/premium.py` line 28, `app/security.py` line 61, `app/main.py` line 310  

`is_production()` returns `_APP_ENV == "production"`. Because `APP_ENV` is not set as a secret, `_APP_ENV` defaults to `"development"` and `is_production()` returns `False`.

Consequences:
- **Session cookies:** `https_only=False` (line 310 of `app/main.py`) — session cookie is not restricted to HTTPS, exposing it to potential interception if any HTTP resource is loaded.
- **Env validation:** Missing `CLOUDFLARE_TURNSTILE_*` or `SESSION_SECRET` logs a warning instead of blocking startup. A misconfigured deployment could silently start in a broken state.
- **Admin route:** Defaults to the predictable path `/admin-dev` instead of a randomized secret path. Admin dashboard is reachable by anyone who knows or guesses this path.
- **Dev-only tier toggle:** `/toggle-tier` is accessible (line 1914 of `app/main.py`).

**Recommended fix:** Add `APP_ENV=production` to the deployment secrets.

---

### 2c. HEIC files advertised but silently rejected

**Severity:** MEDIUM — affects iPhone users  
**Component:** `app/templates/upload.html` line 24, `app/security.py` lines 199–213  

The file input's `accept` attribute includes `.heic`:
```html
accept=".pdf,.png,.jpg,.jpeg,.gif,.heic,.webp,.doc,.docx"
```

The server-side MIME allow-list (`ALLOWED_MIME_TYPES`) does not include `image/heic` or `image/heif`. iOS devices store photos in HEIC format. The magic-byte table also has no HEIC entry, so the detected MIME falls through to `claimed_mime` or `application/octet-stream`, both of which fail the allow-list check.

The user experience: the file browser accepts the file, the scan overlay runs, then the upload is rejected with "File type not permitted." The `.heic` entry in `accept` creates a false promise.

**Recommended fix (option A — reject cleanly):** Remove `.heic` from the `accept` attribute.  
**Recommended fix (option B — support it):** Add `image/heic` and `image/heif` to `ALLOWED_MIME_TYPES` and add HEIC magic bytes (`\x00\x00\x00\x?ftyp`) to `_MAGIC_TABLE`.

---

### 2d. Ephemeral filesystem and SQLite — data not persisted across deployments

**Severity:** HIGH — production data loss on every redeploy  
**Component:** `app/storage.py` line 7, `app/db.py` line 25  

```python
UPLOAD_DIR = Path(__file__).parent / "uploads"   # app/uploads/
DB_PATH    = DATA_DIR / "app.db"                  # app/data/app.db
```

Replit's deployment containers run on an ephemeral filesystem. Every new deployment wipes `app/uploads/` (all uploaded files) and `app/data/app.db` (all users, documents, sessions, share links). Existing users lose all their data on every code push.

This is not the cause of the current upload failure (uploads never succeed to reach storage in the first place due to issue 1), but it is a critical production readiness blocker for a live app.

**Recommended fix:** 
- Files → migrate to an object storage service (e.g. AWS S3, Cloudflare R2, or Backblaze B2) using pre-signed URLs for upload and download.
- Database → migrate to a hosted PostgreSQL service (e.g. Neon, Supabase, or Replit's hosted Postgres) by swapping the SQLAlchemy connection string.

---

## 3. Items Confirmed Clear

| Check | Status | Notes |
|-------|--------|-------|
| Authentication (Google OAuth) | ✅ Working | OAuth callbacks succeed; sessions established correctly |
| CSRF protection | ✅ Working | XHR sends `X-CSRF-Token` header; pure-ASGI middleware validates it without consuming the body stream |
| Rate limiter | ✅ Appropriate | 10 uploads / 60 s per IP; no evidence of abuse triggering it |
| File size limit | ✅ Working | `_read_limited()` enforces 25 MB before any processing |
| MIME validation | ✅ Working | Magic-byte detection + allow-list; no bypass observed |
| Duplicate detection | ✅ Working | SHA-256 content hash dedup on the user's own documents |
| Database schema | ✅ Correct | All required columns present; WAL mode active |
| Storage path logic | ✅ Correct | Path-traversal guard in `file_path()`; `mkdir(exist_ok=True)` at module load |
| Cloudflare interference | ✅ No evidence | Requests reach the app server; 35.191.x.x IPs are Google's LB, not CF blocking |
| Session secrets | ✅ Set | `SESSION_SECRET` (64 chars), `GOOGLE_CLIENT_ID/SECRET` present |
| Turnstile secrets | ✅ Set | Both `CLOUDFLARE_TURNSTILE_SITE_KEY` and `CLOUDFLARE_TURNSTILE_SECRET_KEY` present |

---

## 4. Production Readiness Assessment

| Category | Grade | Blocker? |
|----------|-------|----------|
| Upload functionality | ❌ Broken | Yes — Turnstile fix not deployed |
| Authentication | ✅ Functional | No |
| Security posture | ⚠️ Degraded | No (`APP_ENV` not set; session cookies not Secure-only) |
| Data persistence | ❌ Ephemeral | Yes (long-term) — data wiped on every deploy |
| Error UX | ⚠️ Misleading | No (XHR silences errors) |
| HEIC support | ⚠️ Broken | No (minor — affects iPhone users) |

---

## 5. Recommended Fix Order

1. **Deploy the existing Turnstile fix** — unblocks 100% of uploads immediately. The code is in `app/main.py` (already committed). Click **Publish** in Replit to push it to `credantaapp.com`.

2. **Set `APP_ENV=production`** in Replit Secrets — restores secure session cookies, correct admin route, proper env validation at startup.

3. **Fix XHR error handling** in `upload.html` — return JSON 4xx on upload failures so the scan overlay can display the actual error instead of navigating the user to an empty /documents page.

4. **Remove `.heic` from `accept`** in `upload.html` (or add HEIC to the server allow-list).

5. **Migrate to persistent storage** before launch — object storage for files, hosted Postgres for the database.
