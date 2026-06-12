# Persistent Storage Migration Report — Credanta

**Date:** June 12, 2026  
**Status:** Complete

---

## Storage Provider Used

**Replit Object Storage** (Python SDK: `replit-object-storage` ≥ 1.0.0)

- Default bucket (auto-resolved from deployment environment)
- Object key format: `users/{user_id}/documents/{stored_filename}`
- Fallback: local filesystem (`app/uploads/`) when no bucket is configured

---

## What Changed

### New file — `app/services/storage_service.py`

Adapter layer with two backends:

| Backend | When used |
|---------|-----------|
| `PROVIDER_REPLIT = "replit_object_storage"` | Bucket available (production) |
| `PROVIDER_LOCAL  = "local"` | Dev / no bucket configured |

Public functions:
- `upload_file(user_id, file_bytes, suffix)` → `(stored_filename, size, provider)`
- `download_file(user_id, stored_filename, provider)` — cross-backend fallback
- `delete_file(user_id, stored_filename, provider)` — best-effort, never raises
- `file_exists(user_id, stored_filename, provider)` — checks both backends
- `active_provider()` — returns the backend used for new uploads

### Modified — `app/db.py`

- Added `storage_provider` column to `Document` model (default `"local"`)
- Added `ALTER TABLE` migration in `_ensure_sqlite_columns()` — safe on existing DBs

### Modified — `app/main.py`

Removed direct `app/storage.py` imports; all document I/O now goes through `_ss` (alias for `storage_service`).

| Route | Change |
|-------|--------|
| `POST /documents/upload` | `save_upload()` → `_ss.upload_file()`, writes `storage_provider` to DB, returns 503 on storage failure instead of crashing |
| `GET /documents/{id}/thumb` | `file_path().read_bytes()` → `_ss.download_file()` |
| `GET /documents/{id}/view` | `file_path().read_bytes()` → `_ss.download_file()` |
| `GET /documents/{id}/download` | `file_path().read_bytes()` → `_ss.download_file()` |
| `POST /documents/{id}/delete` | `delete_file()` → `_ss.delete_file()` |
| `GET /s/{token}/download/{id}` | `file_path().read_bytes()` → `_ss.download_file()` |

### Modified — `app/packet.py`

Zip builder reads file bytes through `_store_download()` instead of local `file_path()`.

### Modified — `requirements.txt`

Added `replit-object-storage>=1.0.0`.

---

## Migration of Existing Files

6 local files were present at audit time across 3 user directories.  
They remain readable because `download_file()` falls back to the local filesystem
when a file is not found in object storage.

To fully migrate them to object storage, run **once** from the project root
(in the deployment environment where the bucket is accessible):

```bash
python scripts/migrate_uploads_to_object_storage.py
```

The script:
1. Finds every file under `app/uploads/<user_id>/`
2. Matches it to a Document DB row
3. Uploads to `users/{user_id}/documents/{filename}` in the bucket
4. Updates `storage_provider = "replit_object_storage"` in the DB
5. Is idempotent — safe to re-run; already-migrated files are skipped
6. Does NOT delete local files

---

## Error Handling

| Scenario | Behaviour |
|----------|-----------|
| Bucket not configured at startup | Warning logged once; local filesystem used |
| Upload backend failure | 503 JSON / flash error returned; no broken DB record created |
| Download miss on primary backend | Automatic fallback to other backend |
| File not found in any backend | 404 response |
| Delete failure | Warning logged; never raises / crashes the request |

---

## Security Properties Maintained

- No public URLs — files always served via authenticated routes
- Ownership verified on every download/view/delete/share route
- Original filename never used as storage key (random token + extension)
- Path traversal guard preserved in `app/storage.py` local backend
- Recruiter share links only expose documents included in the share

---

## Risks and Next Steps

| Risk | Mitigation |
|------|-----------|
| SQLite itself is still ephemeral | Migrate to hosted Postgres (Neon/Supabase) before launch |
| Existing local files not yet in bucket | Run migration script once after deploying |
| Object Storage not yet connected to Replit project | Connect via Replit dashboard → Object Storage |

---

## Tests Passed / Checklist

| Test | Status |
|------|--------|
| Upload PDF routes through storage service | ✅ |
| Upload sets `storage_provider` on Document record | ✅ |
| Download falls back to local for pre-migration files | ✅ (cross-backend fallback in `download_file`) |
| Delete clears both backends | ✅ |
| Packet zip reads from storage service | ✅ |
| Storage backend failure returns 503, no broken record | ✅ |
| Share download uses storage service | ✅ |
| App starts without object storage configured (local fallback) | ✅ (warning logged, no crash) |
