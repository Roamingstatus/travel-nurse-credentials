# Playwright Test Report

## Files Created

- `playwright.config.ts`
- `tests/e2e/credanta.spec.ts`
- `PLAYWRIGHT_TEST_REPORT.md`

## Files Updated

- `package.json`
- `app/db.py`
- `app/storage.py`
- `app/services/storage_service.py`
- `app/security.py`
- `app/static/style.v5.css`
- `.gitignore`

## Coverage

The Playwright suite covers:

- Registration
- Login
- Document Upload
- Resume Enhancer
- Packet Generation
- Share Links
- Mobile Navigation
- Logout

## Test Accounts

- Uses generated `@example.com` test accounts only.
- Each run generates a unique email address.
- No production credentials are used.

## Runtime Isolation

The Playwright web server is configured with:

- `APP_ENV=development`
- `BETA_UNLOCK_ALL_FEATURES=true`
- `CREDANTA_DISABLE_RATE_LIMITS=true`
- `CREDANTA_FORCE_LOCAL_STORAGE=true`
- `CREDANTA_DB_PATH=/tmp/credanta-playwright/app.db`
- `CREDANTA_UPLOAD_DIR=/tmp/credanta-playwright/uploads`

This keeps E2E data separate from the normal local app database and uploads.

## Failure Artifacts

Configured in `playwright.config.ts`:

- Screenshots on failure
- Trace on failure
- Video on failure
- HTML report in `playwright-report`
- Raw artifacts in `test-results/playwright`

These artifact directories are ignored by Git.

## Final Verification

Verified on 2026-06-15 with the current workspace state using:

```bash
npm run test:e2e
```

Result:

```text
8 passed (24.4s)
```

## Notes

- The Playwright suite uses generated `@example.com` test accounts only; no production credentials are used.
- Failure capture is enabled via screenshots, traces, and videos in `playwright.config.ts`.
- The current E2E suite is verified and ready to rerun with `npm run test:e2e`.

## How To Run

```bash
npm run test:e2e
```

To view the HTML report after a run:

```bash
npx playwright show-report
```
