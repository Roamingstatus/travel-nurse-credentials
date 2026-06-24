# RAILWAY_STORAGE_SETUP

Configure Credanta on Railway with **PostgreSQL** for app data and a **Volume** for uploaded files.

---

## Architecture

| Layer | Technology | Stores |
|---|---|---|
| App data | Railway PostgreSQL (`DATABASE_URL`) | Users, documents metadata, share links, sessions |
| File bytes | Railway Volume (`/data/uploads`) | PDFs, images, DOCX, resumes, feedback screenshots |

PostgreSQL stores **metadata only** (`documents.stored_filename`, `mime_type`, `content_hash`, etc.).  
File contents are **never** in the database and **never** exposed as public static URLs.

---

## Required Railway variables

| Variable | Value | Notes |
|---|---|---|
| `DATABASE_URL` | Auto-injected | Add **PostgreSQL** plugin to the service |
| `CREDANTA_UPLOAD_DIR` | `/data/uploads` | Optional — this is the default |
| `APP_ENV` | `production` | Enables production checks |
| `SESSION_SECRET` | Random 48+ chars | Required |
| `APP_BASE_URL` | `https://your-app.up.railway.app` | OAuth + email links |

Startup logs (no secrets):

```
[startup] Database: Connected (postgresql)
[startup] Upload Storage: Ready (/data/uploads)
[storage] Upload directory ready: /data/uploads
```

---

## Volume mount

1. In Railway → your Credanta service → **Volumes**
2. Create a volume and mount it at:

```
/data
```

3. The app writes uploads to:

```
/data/uploads/{user_id}/{uuid}.pdf
/data/uploads/feedback/{uuid}.png
```

4. Redeploy after attaching the volume.

Directory layout:

```
/data/
  uploads/
    42/                          ← user_id
      a1b2c3d4....pdf            ← UUID filename
      e5f6g7h8....docx
    feedback/
      screenshot-....png
```

---

## Local development

Without a Railway volume, override the upload path:

```env
CREDANTA_UPLOAD_DIR=app/uploads
```

Omit `DATABASE_URL` to use SQLite at `app/data/app.db`.

---

## Security (built-in)

| Control | Implementation |
|---|---|
| Safe filenames | UUID hex + sanitised extension |
| Path traversal | Basename-only; resolved path must stay under user dir |
| Ownership | Routes check `doc.user_id == user.id`; `verify_upload_ownership()` |
| MIME validation | `validate_upload()` + magic bytes on upload routes |
| Size limits | 25 MB documents; 10 MB resume files |
| Public access | Files served only through authenticated routes or signed share links |

---

## Migration notes

### From SQLite on Railway (ephemeral)

1. Add Railway **PostgreSQL** — Railway sets `DATABASE_URL`
2. Deploy — `init_db()` creates tables on Postgres
3. **Data migration:** export/import users and documents if needed (manual or pgloader); document files must be copied to the volume separately

### From Replit Object Storage

Replit SDK support was **removed**. Files with `storage_provider = 'replit_object_storage'` in the DB will be read from:

1. `/data/uploads/{user_id}/{filename}` (volume)
2. `app/uploads/{user_id}/{filename}` (legacy local fallback)

If files exist **only** in a Replit bucket:

1. Download from Replit bucket to local machine
2. Upload to Railway volume preserving `{user_id}/{stored_filename}` paths
3. Update `documents.storage_provider` to `'local'` if needed

### From local `app/uploads` (pre-volume)

Copy existing files into the volume:

```bash
# Example: rsync or Railway shell
mkdir -p /data/uploads
cp -a app/uploads/* /data/uploads/
```

Existing DB rows keep the same `stored_filename` — no document record changes required.

---

## Rollback notes

### Roll back volume only

1. Keep PostgreSQL — metadata unchanged
2. Remove volume mount → new uploads fail startup writability check in production
3. To rollback safely: re-attach volume or set `CREDANTA_UPLOAD_DIR` to a writable path

### Roll back to SQLite (not recommended for production)

1. Remove `DATABASE_URL` from Railway variables
2. App falls back to SQLite on ephemeral disk
3. **You will lose DB data on redeploy** unless `CREDANTA_DB_PATH` points to the volume

### Roll back Replit storage code

Previous `storage_service.py` used Replit Object Storage. Current code is volume-only. To restore Replit, revert `app/services/storage_service.py` from git history and reinstall `replit-object-storage`.

---

## Verification checklist

After deploy:

- [ ] Logs show `Database: Connected (postgresql)`
- [ ] Logs show `Upload Storage: Ready (/data/uploads)`
- [ ] Upload a PDF as a logged-in user
- [ ] Redeploy the service
- [ ] Same document still previews/downloads (proves volume persistence)
- [ ] Second user cannot access first user's document

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `DATABASE_URL is required in production` | Attach Railway PostgreSQL plugin |
| `Upload directory is not writable` | Mount volume at `/data` or set writable `CREDANTA_UPLOAD_DIR` |
| Files missing after redeploy | Volume not mounted — uploads were on ephemeral disk |
| `replit_object_storage` docs 404 | Copy files from Replit bucket to volume (see migration) |

---

## Files changed for Railway storage

| File | Role |
|---|---|
| `app/db.py` | Reads `DATABASE_URL`, PostgreSQL engine, connection check |
| `app/storage.py` | Volume paths, UUID saves, ownership verification |
| `app/services/storage_service.py` | Volume-only adapter (Replit removed) |
| `app/security.py` | Production validation for `DATABASE_URL` + upload dir |
| `app/main.py` | Startup logging; feedback on volume |

Do **not** mount uploads as a public static route. All access goes through authenticated app routes.
