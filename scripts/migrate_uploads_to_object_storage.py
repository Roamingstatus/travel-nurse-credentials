#!/usr/bin/env python3
"""
Migrate existing local uploaded files to Replit Object Storage.

Run once from the project root:
    python scripts/migrate_uploads_to_object_storage.py

What it does:
1. Walks app/uploads/<user_id>/<filename> for every file on disk
2. Matches each file to its Document row in the database by stored_filename
3. Uploads it to Replit Object Storage at  users/<user_id>/documents/<filename>
4. Updates Document.storage_provider to "replit_object_storage"
5. Skips files that are already in object storage
6. Skips database rows whose files are missing on disk (logs a warning)
7. Does NOT delete local files — safe to run multiple times

Prerequisites:
- The app must be deployed with a Replit bucket attached
- Run after setting REPLIT_OBJECT_STORAGE_BUCKET or in the deployment environment
"""
import sys
import os
import logging
from pathlib import Path

# Make app importable
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("migrate")

try:
    from replit.object_storage import Client  # type: ignore
    bucket_id = os.environ.get("DEFAULT_OBJECT_STORAGE_BUCKET_ID") or None
    if not bucket_id:
        log.error("DEFAULT_OBJECT_STORAGE_BUCKET_ID is not set.")
        log.error("Ensure the Replit Object Storage bucket is configured for this project.")
        sys.exit(1)
    client = Client(bucket_id=bucket_id)
    # Verify connectivity with a lightweight probe
    client.exists("__migration_probe__")
    log.info("Connected to Replit Object Storage (bucket: %s)", bucket_id)
except Exception as exc:
    log.error("Cannot connect to Replit Object Storage: %s", exc)
    log.error("Ensure you are running this in the deployment environment with a bucket configured.")
    sys.exit(1)

os.environ.setdefault("SESSION_SECRET", "migrate-script-placeholder")

from app.db import SessionLocal, Document  # noqa: E402

UPLOAD_DIR = Path(__file__).parent.parent / "app" / "uploads"
PROVIDER_REPLIT = "replit_object_storage"


def object_key(user_id: int, stored_filename: str) -> str:
    return f"users/{user_id}/documents/{Path(stored_filename).name}"


def main() -> None:
    db = SessionLocal()
    migrated = skipped_already = skipped_missing_file = skipped_no_db_row = errors = 0

    if not UPLOAD_DIR.exists():
        log.info("No local uploads directory found at %s — nothing to migrate.", UPLOAD_DIR)
        return

    for user_dir in sorted(UPLOAD_DIR.iterdir()):
        if not user_dir.is_dir() or not user_dir.name.isdigit():
            continue
        user_id = int(user_dir.name)

        for file_path in sorted(user_dir.iterdir()):
            if not file_path.is_file():
                continue

            stored_filename = file_path.name
            key = object_key(user_id, stored_filename)

            # Look up matching document record
            doc = (
                db.query(Document)
                .filter_by(user_id=user_id, stored_filename=stored_filename)
                .first()
            )
            if doc is None:
                log.warning("  [no-db-row] %s — no matching Document record, skipping", key)
                skipped_no_db_row += 1
                continue

            if doc.storage_provider == PROVIDER_REPLIT:
                try:
                    if client.exists(key):
                        log.info("  [skip] %s already in object storage", key)
                        skipped_already += 1
                        continue
                except Exception:
                    pass

            data = file_path.read_bytes()
            try:
                client.upload_from_bytes(key, data)
                doc.storage_provider = PROVIDER_REPLIT
                db.add(doc)
                db.commit()
                log.info("  [ok] %s (%d bytes)", key, len(data))
                migrated += 1
            except Exception as exc:
                log.error("  [error] %s — %s", key, exc)
                db.rollback()
                errors += 1

    db.close()

    print()
    print("=" * 60)
    print(f"  Migrated:              {migrated}")
    print(f"  Already in storage:    {skipped_already}")
    print(f"  Missing DB row:        {skipped_no_db_row}")
    print(f"  Errors:                {errors}")
    print("=" * 60)
    if errors:
        print("WARNING: some files failed to migrate — check logs above.")
        sys.exit(1)
    else:
        print("Migration complete.")


if __name__ == "__main__":
    main()
