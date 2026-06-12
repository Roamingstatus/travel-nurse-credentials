# Storage Audit Report — Credanta

**Date:** June 12, 2026  
**Status:** Audit complete — migration implemented

---

## Current Storage Method

All uploaded documents are written to the **local container filesystem**:

```
app/uploads/<user_id>/<random_token>.<ext>
```

| Component | Location | Module |
|-----------|----------|--------|
| Upload write | `app/uploads/{user_id}/{token}.ext` | `app/storage.py` → `save_upload()` |
| Download/view reads | `app/uploads/{user_id}/{token}.ext` | `app/storage.py` → `file_path()` |
| Delete | `app/uploads/{user_id}/{token}.ext` | `app/storage.py` → `delete_file()` |
| Packet zip builder | reads local path via `file_path()` | `app/packet.py` |
| Thumbnail | reads local path via `file_path()` | `app/main.py` `/documents/{id}/thumb` |
| Document view | reads local path via `file_path()` | `app/main.py` `/documents/{id}/view` |
| Document download | reads local path via `file_path()` | `app/main.py` `/documents/{id}/download` |
| Share download | reads local path via `file_path()` | `app/main.py` `/s/{token}/download/{id}` |

Document **metadata** (filename, MIME type, expiry, category) is stored in SQLite at `app/data/app.db`.

---

## Why Local Storage Is Unsafe for Production

Replit deployment containers use an **ephemeral filesystem**. Every new deployment:

1. Spins up a fresh container image
2. Mounts no persistent volume at `app/uploads/`
3. Discards all files written in the previous deployment

**Consequence:** every code push deletes 100% of uploaded documents. Users log in to find an empty portfolio. This makes the app unusable as a live service.

The SQLite database (`app/data/app.db`) has the same problem — all user accounts, document metadata, sessions, and share links are wiped too.

---

## Files / Routes Affected by This Audit

| File | Change needed |
|------|--------------|
| `app/storage.py` | Keep for local fallback; no deletion |
| `app/main.py` | 6 sites: upload, thumb, view, download, delete, share_download |
| `app/packet.py` | Read bytes through new service |
| `app/db.py` | Add `storage_provider` column to documents table |

---

## Recommended Migration Path

**Phase 1 (this PR):** Migrate file storage to Replit Object Storage.
- New uploads go to `users/{user_id}/documents/{filename}` in the default bucket
- Reads fall back to local filesystem for files uploaded before migration
- `storage_provider` column added to `documents` table (`"local"` | `"replit_object_storage"`)

**Phase 2 (follow-up):** Migrate SQLite to hosted PostgreSQL (Neon / Supabase / Replit Postgres).
- Replace the SQLAlchemy connection string in `app/db.py`
- Run a one-time data migration from the existing SQLite file

---

## Existing Files to Migrate

At audit time, 5 files existed across 3 user directories:

| Path | Status |
|------|--------|
| `app/uploads/1/xJjdTVVpGo5wO7XK3TFFOQ.pdf` | Needs migration |
| `app/uploads/2/E-NQRAzy36WIa9OXyFcAdg.pdf` | Needs migration |
| `app/uploads/2/g_tbYBEbcpjfn7zk4eqyrA.pdf` | Needs migration |
| `app/uploads/2/gwMcbDBWV7RtYESAhocXMw.pdf` | Needs migration |
| `app/uploads/3/bSMarDYITbw2Bhb0hkF6Hg.pdf` | Needs migration |
| `app/uploads/3/MUH3gitnJ47f5yXN57wD6A.pdf` | Needs migration |

Run `python scripts/migrate_uploads_to_object_storage.py` to copy these to object storage and update their `storage_provider` column.
