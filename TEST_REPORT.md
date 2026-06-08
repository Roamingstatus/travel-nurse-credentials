# Credanta — Test Report

## Summary

| Category | Test File | Tests | Status |
|---|---|---|---|
| Expiration status logic | `test_expiration.py` | 19 | ✅ Passing |
| Custom expiration rules (NIH) | `test_expiration_rules.py` | 9 | ✅ Passing |
| Category detection | `test_categories.py` | 29 | ✅ Passing |
| Subscription tier gating | `test_tiers.py` | 37 | ✅ Passing |
| File storage & deduplication | `test_uploads.py` | 18 | ✅ Passing |
| Share link lifecycle | `test_share_links.py` | 12 | ✅ Passing |
| ZIP packet generation | `test_packets.py` | 14 | ✅ Passing |
| MFA / TOTP / recovery codes | `test_mfa.py` | 21 | ✅ Passing |
| File upload validation | `test_file_validation.py` | 28 | ✅ Passing |
| Multi-user data isolation | `test_privacy.py` | 16 | ✅ Passing |
| Reminder scheduler & services | `test_reminders.py` | 22 | ✅ Passing |
| Recruiter feedback API | `test_recruiter_feedback.py` | 27 | ✅ Passing |

---

## How to Run Tests

### All tests
```bash
pytest tests/ -v
```

### A specific file
```bash
pytest tests/test_privacy.py -v
pytest tests/test_reminders.py -v
```

### With coverage (requires pytest-cov)
```bash
pip install pytest-cov
pytest tests/ --cov=app --cov-report=term-missing
```

### Quiet mode (dots only)
```bash
pytest tests/ -q
```

---

## What Each File Tests

### `test_expiration.py`
Unit tests for the expiration status engine (`app/dashboard.py`).
- `status_for()` — expired / expiring / current / no-expiry transitions
- `ui_status_label()` — maps internal status to display labels
- `days_until()` — positive, negative, zero edge cases
- `summarize()` — aggregate counts, recent cap

### `test_expiration_rules.py`
Unit tests for `app/expiration_rules.py`.
- NIH/NIHSS keyword variants all trigger the rule
- Issue date used as base when present; falls back to upload date
- Existing expiry date is never overridden
- Unrelated documents are not matched

### `test_categories.py`
Unit tests for `app/smart_categorize.py`.
- Keyword matching for Identity, Licenses, Health & Compliance, Education, Other
- Case-insensitive detection
- Date extraction (ISO, slash, month-name formats)
- `extract_document_metadata()` output shape

### `test_tiers.py`
Integration + unit tests for premium gating (`app/premium.py` + routes).
- `has_premium()` / `has_premium_plus()` — all tier combinations
- HTTP route tests: free → 403, premium → allowed, premium+ → allowed
- Checklist readiness score logic
- Agency packet autofill logic

### `test_uploads.py`
Unit tests for `app/storage.py`.
- `user_dir()`, `save_upload()`, `file_path()`, `delete_file()`
- SHA-256 content hash deduplication
- Same hash for different users is not a duplicate

### `test_share_links.py`
Unit tests for `app/main._resolve_share()`.
- Valid / revoked / expired / missing token behaviour
- Token uniqueness constraint
- Owner returned correctly

### `test_packets.py`
Unit tests for `app/packet.build_zip()`.
- Always returns valid ZIP bytes
- MANIFEST.txt always present with user name and document titles
- Missing files skipped gracefully
- Real files appear inside the archive
- Files organised by category folder

### `test_mfa.py`
Unit tests for `app/mfa.py`.
- TOTP generation, verification, wrong-code rejection
- Secret encrypt/decrypt round-trip
- Recovery code generation, hashing, consumption, reuse prevention

### `test_file_validation.py`  *(new)*
Unit tests for `app/security.validate_upload()`.
- All accepted types: PDF, JPEG, PNG, GIF, TIFF, WEBP, DOCX, XLSX, DOC, TXT
- All blocked extensions: `.exe`, `.dll`, `.sh`, `.bat`, `.js`, `.html`, `.py`, `.svg`, etc.
- Empty file rejection
- Magic-byte detection overrides wrong claimed MIME
- EXE magic bytes rejected even with `.pdf` extension

### `test_privacy.py`  *(new)*
HTTP-level cross-user isolation tests.
- User A cannot download, preview, edit, or delete User B's documents (404 returned)
- Reorder endpoint silently ignores doc IDs not owned by the requester
- Packet ZIP only contains the requesting user's documents
- Free users cannot create share links (403)
- Share link ownership is always scoped to the authenticated user

### `test_reminders.py`  *(new)*
Tests for `app/services/reminder_scheduler.py`, `email_service.py`, `sms_service.py`.
- `ReminderSettings.get_days_list()` — parses comma-separated threshold days
- Threshold days (30, 14, 7, 0) match; non-thresholds (29, 13, 6, 1, -1) do not
- `_send_if_not_duplicate()` — calls send_fn once; skips on duplicate log today
- Different reminder types / different day values are not considered duplicates
- `send_expiration_email()` returns `provider_not_configured` when `RESEND_API_KEY` absent
- `send_expiration_sms()` returns `provider_not_configured` when Twilio keys absent
- Neither service raises an exception when keys are missing
- Scheduler survives broken DB connections without propagating exceptions

### `test_recruiter_feedback.py`  *(new)*
Integration tests for `POST /api/recruiter-feedback` and `POST /api/recruiter-feedback/opened`.
- `opened` endpoint: 200 for all inputs including unknown tokens and malformed JSON
- Valid payload with every allowed role/timing/agency type returns 200
- Missing required fields return 422
- Invalid field values (not in allow-lists) return 422
- Unknown document names are silently filtered, request still succeeds
- Document list capped at 50 without crashing
- Turnstile failure returns 403 with appropriate message
- Empty `cf_token` when Turnstile is enforced returns 403
- Allow-list constants are non-empty and have no duplicates

---

## Known Gaps

### Not yet automated
| Gap | Reason | Recommended next step |
|---|---|---|
| Full upload route (multipart POST) | Requires file bytes + session mock; complex integration | Add with httpx multipart + patched auth |
| Resume enhancer scoring | Requires OpenAI key in test environment | Mock `enhance_resume` / `rewrite_resume`; test input/output shape |
| Stripe webhook handling | Requires signed payloads | Test with `stripe.WebhookSignature` test fixtures |
| Calendar `.ics` feed | Requires `calendar_token` in DB | Add as integration test alongside share link tests |
| Browser / Playwright | Playwright not installed in this environment | See `TESTING_CHECKLIST.md` for manual steps |
| Accessibility automated scan | No axe-core or pa11y configured | Add `npm install --save-dev axe-playwright` if Playwright is added |
| Load / rate-limit testing | `upload_limiter`, `feedback_limiter`, `preview_limiter` | Use `locust` or `k6` to verify limiter thresholds |
| Admin route auth | Admin routes need user-level auth check | Verify non-admin users cannot access `/admin/*` |

---

## Recommended Next Tests

1. **Full upload integration** — multipart form submission through the full route stack to verify duplicate detection, MIME validation, and DB record creation end-to-end.
2. **Calendar feed** — verify the `.ics` file at `/calendar/feed/{token}.ics` contains valid RFC 5545 events with correct DTSTART/DTEND.
3. **Resume enhancer** — mock the AI service and verify score structure, weak-word detection, and keyword coverage.
4. **Admin route access control** — confirm non-admin users receive 403 on all `/admin/*` routes.
5. **Rate limiter behaviour** — send 6+ rapid requests to feedback/upload routes and confirm the 6th returns 429.
