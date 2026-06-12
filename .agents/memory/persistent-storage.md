---
name: Persistent storage migration
description: Document uploads migrated from local filesystem to Replit Object Storage via storage_service adapter
---

## Rule
All document file I/O must go through `app/services/storage_service._ss` — never call `app/storage.py` directly from routes or packet builder.

**Why:** Replit containers have an ephemeral filesystem; direct local writes are wiped on every deployment.

## How to apply
- Upload: `_ss.upload_file(user_id, bytes, suffix)` → `(stored_filename, size, provider)`
- Download: `_ss.download_file(user_id, stored_filename, doc.storage_provider)`
- Delete: `_ss.delete_file(user_id, stored_filename, doc.storage_provider)`
- Exists check: `_ss.file_exists(user_id, stored_filename, doc.storage_provider)`
- Object key format: `users/{user_id}/documents/{stored_filename}`
- Provider values: `"local"` | `"replit_object_storage"` (constants in storage_service.py)

## Cross-backend fallback
`download_file()` tries the recorded provider first, then falls back to the other backend — existing local files remain readable after migration without running the migration script.

## DB column
`documents.storage_provider` VARCHAR DEFAULT 'local'. Added via `_ensure_sqlite_columns()` in db.py — safe on existing databases.

## Migration script
`scripts/migrate_uploads_to_object_storage.py` — idempotent, run once in the deployment environment to copy pre-migration local files to the bucket.

## Replit Object Storage Python SDK
Package: `replit-object-storage>=1.0.0`  
Client: `from replit.object_storage import Client; client = Client()`  
Key methods: `upload_from_bytes(key, data)`, `download_as_bytes(key)`, `exists(key)`, `delete(key, ignore_not_found=True)`  
No bucket_id needed — default bucket auto-resolved from deployment environment.
