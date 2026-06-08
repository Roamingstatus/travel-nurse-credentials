---
name: Admin route hardening
description: How the Credanta admin system is secured — configurable route, audit logging, anti-discovery.
---

## Rule
All admin routes live at `{ADMIN_ROUTE}/*` (env var, no default in prod). `/admin` and `/admin/{path}` always return 404.

**Why:** The spec requires route obscurity as an additional layer only — real security is the ADMIN_EMAILS allowlist + rate limit + audit log.

## How to apply
- `ADMIN_ROUTE` is a module-level constant in `app/main.py`, evaluated at startup from `os.environ.get("ADMIN_ROUTE")`. Logs a warning and disables in prod if unset.
- All 11 admin route decorators use `f"{ADMIN_ROUTE}/..."` or bare `ADMIN_ROUTE`.
- Every admin handler calls `_admin_gate(request, user, db, "route-name")` which: applies `admin_limiter` (30/15 min), calls `require_admin`, writes an `AdminAccessLog` row for both success and denial.
- `admin_render()` wraps `render()` and adds `X-Robots-Tag: noindex, nofollow`.
- Templates use `{{ admin_route }}` — injected into all templates via `render()` context default (`ctx.setdefault("admin_route", ADMIN_ROUTE)`).
- `AdminAccessLog` ORM model is in `app/db.py`; `_ensure_sqlite_columns` handles the SQLite migration.
- 28 tests in `tests/test_admin_security.py` cover all security properties.
