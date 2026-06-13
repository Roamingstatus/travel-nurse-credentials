---
name: Multi-provider OAuth architecture
description: How Microsoft, Apple, and Google OAuth are implemented — identifiers, DB columns, callback patterns, and the _finish_oauth_login helper.
---

## Rule
Each OAuth provider has its own stable-identifier column. The legacy `google_sub` column is reused as a unique placeholder (`"provider:uuid"`) for non-Google accounts so the NOT NULL unique constraint isn't broken.

**Why:** Adding proper per-provider columns (microsoft_id, apple_id) while keeping google_sub intact avoids a risky schema migration on existing data. New providers get their own column; google_sub stays as the "primary unique key" for the row.

**How to apply:** When adding a fourth OAuth provider, add a new nullable unique column (e.g. `facebook_id`), set `google_sub = "facebook:uuid"` on new rows, and follow the same link-by-email pattern in the callback.

## Provider details

### Google
- Library: authlib `oauth.google.authorize_access_token()`
- Stable ID: `google_sub` (the `sub` claim)
- Callback: GET `/auth/google/callback`

### Microsoft
- Library: authlib OIDC registered as `"microsoft"` in `_LazyOAuth._get()`
- Server metadata: `https://login.microsoftonline.com/common/v2.0/.well-known/openid-configuration`
- Stable ID: `microsoft_id` = `oid` claim (not `sub` — `sub` is tenant-scoped). Falls back to decoding the raw id_token if `oid` isn't in userinfo.
- Callback: GET `/auth/microsoft/callback`
- Env vars needed: `MICROSOFT_CLIENT_ID`, `MICROSOFT_CLIENT_SECRET`

### Apple
- Library: **manual OIDC** — Apple uses a POST callback, not GET, so authlib's `authorize_access_token` cannot be used directly.
- `GET /auth/apple` stores a random `state` in `request.session["_apple_oauth_state"]` and redirects to Apple with `response_mode=form_post`.
- `POST /auth/apple/callback` validates state, calls `https://appleid.apple.com/auth/token` via httpx, fetches JWKs, and verifies the id_token with `authlib.jose.JsonWebKey + jwt.decode`.
- Apple sends the user's name **only on the first sign-in** in the `user` form field (JSON string).
- Apple may return a private-relay email (`*@privaterelay.appleid.com`) — handled by creating a synthetic placeholder email if no real email is provided.
- `generate_apple_client_secret()` in `auth.py` creates a 6-month ES256 JWT from `APPLE_PRIVATE_KEY` (handle `\\n` literal escaping). Called fresh per callback.
- Stable ID: `apple_id` = `sub` claim from the id_token.
- Env vars needed: `APPLE_CLIENT_ID`, `APPLE_TEAM_ID`, `APPLE_KEY_ID`, `APPLE_PRIVATE_KEY`. Optional: `APPLE_REDIRECT_URI` (defaults to `url_for("apple_callback")` with https coercion).

## Account linking
All three OAuth callbacks link to existing accounts by email before creating a new row. This means a user who registered with email/password can later sign in with any OAuth provider using the same address without getting a duplicate account.

## Shared helper
`_finish_oauth_login(request, db, user, is_new)` in `main.py` handles:
- Trial eligibility grant for new users
- Banner-seen-days increment (up to 3)
- MFA redirect if `mfa_enabled`
- Session setup and flash message
