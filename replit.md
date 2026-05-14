# Travel Nurse Credentials

## Overview
A web app that helps travel nurses keep licenses, certifications, and other onboarding documents in one place. Nurses sign in with Google, upload documents with expiration dates, see what's expired or expiring, and share a clean read-only view (or a downloadable .zip packet) with recruiters.

## Stack
- **Backend**: Python 3.11 + FastAPI (uvicorn)
- **Frontend**: Server-rendered Jinja2 templates + plain CSS
- **Database**: SQLite (file at `app/data/app.db`)
- **Auth**: Google OAuth via Authlib + Starlette session middleware
- **Storage**: Local filesystem under `app/uploads/<user_id>/`
- **Packet generation**: stdlib `zipfile`

## Layout
```
app/
  main.py          # FastAPI app, all routes
  auth.py          # Google OAuth + session helpers
  db.py            # SQLAlchemy models, SQLite engine
  storage.py       # File upload/save/delete helpers
  dashboard.py     # Status (expired/expiring/current) + missing-cred logic
  packet.py        # Zip packet builder
  categories.py    # Predefined credential categories + required checklist
  templates/       # Jinja2 templates
  static/style.css # All styles
  data/            # SQLite db (gitignored)
  uploads/         # Uploaded files (gitignored)
run.py             # Uvicorn entrypoint, reads $PORT (defaults to 5000)
```

## Required secrets
- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `SESSION_SECRET` (already provided)

The Google OAuth client must list the app's callback URL (`https://<your-domain>/auth/google/callback`) as an authorized redirect URI.

## Routes
- `/` — redirects based on auth
- `/login`, `/auth/google`, `/auth/google/callback`, `/logout`
- `/dashboard` — overview with expired/expiring/missing checklist
- `/documents`, `/documents/upload`, `/documents/{id}/download`, `/documents/{id}/delete`
- `/packet` — owner downloads a zip of all docs + manifest
- `/share`, `/share/create`, `/share/{id}/revoke`
- `/s/{token}` — public read-only recruiter view
- `/s/{token}/download/{doc_id}`, `/s/{token}/packet`
- `/healthz`
