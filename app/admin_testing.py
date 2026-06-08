"""
Admin testing dashboard — run pytest, persist results, build export report.
"""
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session
from sqlalchemy import text

TESTS_DIR = Path(__file__).parent.parent / "tests"
XML_OUTPUT = Path("/tmp/credanta_test_results.xml")

# ---------------------------------------------------------------------------
# Card groupings — maps display name → list of test file substrings
# ---------------------------------------------------------------------------

CARD_GROUPS = {
    "Application Health": [
        "test_categories", "test_expiration_rules", "test_expiration",
        "test_recruiter_feedback",
    ],
    "Security Tests": ["test_mfa", "test_privacy", "test_tiers"],
    "Premium Feature Tests": ["test_tiers"],
    "Document Tests": ["test_uploads", "test_file_validation", "test_packets"],
    "Share Link Tests": ["test_share_links"],
    "Reminder Tests": ["test_reminders"],
}

CARD_ORDER = [
    "Application Health",
    "Security Tests",
    "Premium Feature Tests",
    "Document Tests",
    "Share Link Tests",
    "Reminder Tests",
]

CARD_ICONS = {
    "Application Health":   "🏥",
    "Security Tests":       "🔒",
    "Premium Feature Tests":"⭐",
    "Document Tests":       "📄",
    "Share Link Tests":     "🔗",
    "Reminder Tests":       "🔔",
}


# ---------------------------------------------------------------------------
# DB helpers (raw SQL — tables are raw-SQL managed in db._ensure_sqlite_columns)
# ---------------------------------------------------------------------------

def _ensure_test_tables(db: Session) -> None:
    db.execute(text(
        "CREATE TABLE IF NOT EXISTS test_runs ("
        "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  total_tests INTEGER NOT NULL DEFAULT 0,"
        "  passed_tests INTEGER NOT NULL DEFAULT 0,"
        "  failed_tests INTEGER NOT NULL DEFAULT 0,"
        "  duration_ms INTEGER NOT NULL DEFAULT 0,"
        "  created_at DATETIME DEFAULT (datetime('now'))"
        ")"
    ))
    db.execute(text(
        "CREATE TABLE IF NOT EXISTS test_failures ("
        "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  run_id INTEGER NOT NULL REFERENCES test_runs(id) ON DELETE CASCADE,"
        "  test_name VARCHAR NOT NULL,"
        "  error_message TEXT,"
        "  created_at DATETIME DEFAULT (datetime('now'))"
        ")"
    ))
    db.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_test_failures_run_id ON test_failures (run_id)"
    ))
    db.commit()


def get_latest_run(db: Session) -> dict | None:
    try:
        row = db.execute(text(
            "SELECT id, total_tests, passed_tests, failed_tests, duration_ms, created_at "
            "FROM test_runs ORDER BY id DESC LIMIT 1"
        )).fetchone()
    except Exception:
        return None
    if not row:
        return None
    return {
        "id": row[0],
        "total": row[1],
        "passed": row[2],
        "failed": row[3],
        "duration_ms": row[4],
        "created_at": row[5],
    }


def get_run_failures(db: Session, run_id: int) -> list[dict]:
    try:
        rows = db.execute(text(
            "SELECT test_name, error_message FROM test_failures "
            "WHERE run_id = :r ORDER BY id"
        ), {"r": run_id}).fetchall()
    except Exception:
        return []
    return [{"test_name": r[0], "error_message": r[1] or ""} for r in rows]


def get_all_runs(db: Session, limit: int = 10) -> list[dict]:
    try:
        rows = db.execute(text(
            "SELECT id, total_tests, passed_tests, failed_tests, duration_ms, created_at "
            "FROM test_runs ORDER BY id DESC LIMIT :l"
        ), {"l": limit}).fetchall()
    except Exception:
        return []
    return [
        {
            "id": r[0], "total": r[1], "passed": r[2], "failed": r[3],
            "duration_ms": r[4], "created_at": r[5],
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

def run_test_suite(db: Session) -> dict:
    """Execute pytest, parse JUnit XML, persist to DB. Returns summary dict."""
    _ensure_test_tables(db)

    start = time.time()

    if XML_OUTPUT.exists():
        try:
            XML_OUTPUT.unlink()
        except Exception:
            pass

    cmd = [
        sys.executable, "-m", "pytest",
        str(TESTS_DIR),
        "--junit-xml", str(XML_OUTPUT),
        "--tb=short",
        "-q",
        "--no-header",
    ]

    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        pass
    except Exception:
        pass

    duration_ms = int((time.time() - start) * 1000)
    total, passed, failed = 0, 0, 0
    failures: list[dict] = []

    if XML_OUTPUT.exists():
        try:
            tree = ET.parse(XML_OUTPUT)
            root = tree.getroot()
            for suite in root.iter("testsuite"):
                total   += int(suite.get("tests",    0))
                failed  += int(suite.get("failures", 0)) + int(suite.get("errors", 0))
            passed = total - failed

            for case in root.iter("testcase"):
                classname = case.get("classname", "")
                name = case.get("name", "")
                full_name = f"{classname}::{name}" if classname else name
                for child in case:
                    if child.tag in ("failure", "error"):
                        msg = (child.get("message") or child.text or "").strip()
                        failures.append({
                            "test_name": full_name,
                            "error_message": msg[:2000],
                        })
        except Exception:
            pass

    now = datetime.utcnow()
    db.execute(text(
        "INSERT INTO test_runs (total_tests, passed_tests, failed_tests, duration_ms, created_at) "
        "VALUES (:t, :p, :f, :d, :c)"
    ), {"t": total, "p": passed, "f": failed, "d": duration_ms, "c": now})
    db.flush()
    run_id = db.execute(text("SELECT last_insert_rowid()")).scalar()

    for fail in failures:
        db.execute(text(
            "INSERT INTO test_failures (run_id, test_name, error_message, created_at) "
            "VALUES (:r, :n, :e, :c)"
        ), {"r": run_id, "n": fail["test_name"], "e": fail["error_message"], "c": now})

    db.commit()

    return {
        "run_id": run_id,
        "total": total,
        "passed": passed,
        "failed": failed,
        "duration_ms": duration_ms,
    }


# ---------------------------------------------------------------------------
# Card builder
# ---------------------------------------------------------------------------

def _card_status(failures_in_card: int, run: dict) -> str:
    if run is None:
        return "unknown"
    if failures_in_card == 0:
        return "pass"
    if failures_in_card <= 2:
        return "warn"
    return "fail"


def build_cards(run: dict | None, failures: list[dict]) -> list[dict]:
    cards = []
    for card_name in CARD_ORDER:
        keywords = CARD_GROUPS[card_name]
        card_failures = []
        for fail in failures:
            tn = fail["test_name"].lower()
            if any(kw in tn for kw in keywords):
                card_failures.append(fail)
        cards.append({
            "name": card_name,
            "icon": CARD_ICONS.get(card_name, ""),
            "status": _card_status(len(card_failures), run),
            "failure_count": len(card_failures),
            "failures": card_failures,
        })
    return cards


# ---------------------------------------------------------------------------
# Report generator
# ---------------------------------------------------------------------------

def generate_report_md(run: dict, failures: list[dict], all_runs: list[dict]) -> str:
    ts = run["created_at"]
    ts_str = ts.strftime("%Y-%m-%d %H:%M UTC") if hasattr(ts, "strftime") else str(ts)[:19] + " UTC"
    pct = (run["passed"] / run["total"] * 100) if run["total"] else 0
    dur_s = (run["duration_ms"] or 0) / 1000

    lines = [
        "# Credanta Test Report",
        "",
        f"**Generated:** {ts_str}  ",
        f"**Run ID:** #{run['id']}  ",
        f"**Duration:** {dur_s:.1f}s  ",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total Tests | {run['total']} |",
        f"| Passed | {run['passed']} ✅ |",
        f"| Failed | {run['failed']} {'❌' if run['failed'] else '✅'} |",
        f"| Pass Rate | {pct:.1f}% |",
        f"| Duration | {dur_s:.1f}s |",
        "",
    ]

    cards = build_cards(run, failures)
    lines += [
        "## Test Categories",
        "",
        "| Category | Status | Failures |",
        "|----------|--------|----------|",
    ]
    status_label = {"pass": "✅ Pass", "warn": "⚠️ Warning", "fail": "❌ Fail", "unknown": "— Unknown"}
    for c in cards:
        lines.append(f"| {c['icon']} {c['name']} | {status_label.get(c['status'], c['status'])} | {c['failure_count']} |")
    lines.append("")

    if failures:
        lines += [
            "## Failed Tests",
            "",
            "| Test | Error |",
            "|------|-------|",
        ]
        for f in failures:
            msg = (f["error_message"] or "").replace("\n", " ").replace("|", "\\|")[:250]
            lines.append(f"| `{f['test_name']}` | {msg} |")
        lines.append("")
    else:
        lines += ["## Failed Tests", "", "✅ All tests passed.", ""]

    if len(all_runs) > 1:
        lines += [
            "## Run History",
            "",
            "| Run | Date | Total | Passed | Failed | Pass % |",
            "|-----|------|-------|--------|--------|--------|",
        ]
        for r in all_runs:
            r_ts = r["created_at"]
            r_ts_str = r_ts.strftime("%Y-%m-%d %H:%M") if hasattr(r_ts, "strftime") else str(r_ts)[:16]
            r_pct = (r["passed"] / r["total"] * 100) if r["total"] else 0
            lines.append(
                f"| #{r['id']} | {r_ts_str} | {r['total']} | {r['passed']} | {r['failed']} | {r_pct:.0f}% |"
            )
        lines.append("")

    lines += [
        "---",
        "_Generated by Credanta Admin Testing Dashboard_",
    ]
    return "\n".join(lines)
