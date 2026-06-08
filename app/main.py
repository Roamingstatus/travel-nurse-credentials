import hashlib
import json
import os
import secrets
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware

from collections import defaultdict

from .ai_docs import ai_enabled, ai_refine_category_expiry, extract_text_sample
from .auth import current_user, google_configured, oauth, require_user
from .stripe_billing import (
    construct_webhook_event,
    create_checkout_session,
    create_portal_session,
    price_ids,
    stripe_configured,
    tier_for_price_id,
)
from .categories import CATEGORY_ORDER, CREDENTIAL_CATEGORIES, US_STATES, normalized_effective_category
from .dashboard import days_until, status_for, summarize, ui_status_label
from .services.email_service import get_email_status, send_test_email
from .services.sms_service import get_sms_status, send_test_sms
from .services.reminder_scheduler import start_scheduler, stop_scheduler
from .db import (
    ChecklistResult,
    Document,
    Event,
    ReminderLog,
    ReminderSettings,
    SessionLocal,
    ShareLink,
    User,
    get_session,
    init_db,
)
from .events import log_event, require_admin
from .packet import build_zip
from .packet_pdf import build_manifest_pdf
from .premium import (
    PREMIUM_FEATURES,
    PREMIUM_PLUS_FEATURES,
    has_premium,
    has_premium_plus,
    require_premium,
    require_premium_plus,
    user_has_premium,
)
from .reminders import build_expiring_ics
from .expiration_rules import apply_custom_expiration_rules
from .smart_categorize import extract_document_metadata, extract_document_text, infer_category, infer_expiry_from_text
from .storage import delete_file, file_path, save_upload
from .security import (
    SecurityHeadersMiddleware,
    INLINE_SAFE_MIMES,
    validate_env,
    validate_upload,
    upload_limiter,
    auth_limiter,
    share_limiter,
    preview_limiter,
    feedback_limiter,
    verify_turnstile,
    make_download_token,
    verify_download_token,
)
import itsdangerous as _itsd
from .mfa import (
    decrypt_totp_secret,
    encrypt_totp_secret,
    generate_recovery_codes,
    generate_totp_secret,
    get_totp_uri,
    encode_recovery_hashes,
    hash_recovery_code,
    verify_totp,
    consume_recovery_code,
)

AUTO_CATEGORY = "__auto__"

BASE_DIR = Path(__file__).parent

app = FastAPI(title="Credanta")

_MFA_EXEMPT_PREFIXES = (
    "/login",
    "/auth/",
    "/logout",
    "/static/",
    "/healthz",
    "/s/",
    "/security/mfa/setup",
    "/security/mfa/confirm",
    "/security/mfa/challenge",
    "/security/mfa/verify-recovery",
)


class EnforceMFAMiddleware(BaseHTTPMiddleware):
    """Redirect authenticated users without MFA set up to the MFA setup page."""

    async def dispatch(self, request: Request, call_next):
        if not _is_production:
            return await call_next(request)
        path = request.url.path
        if path == "/" or any(path.startswith(p) for p in _MFA_EXEMPT_PREFIXES):
            return await call_next(request)
        user_id = request.session.get("user_id")
        if user_id:
            db = SessionLocal()
            try:
                user = db.get(User, user_id)
                if user and not getattr(user, "mfa_enabled", False):
                    return RedirectResponse("/security/mfa/setup", status_code=302)
            finally:
                db.close()
        return await call_next(request)


_is_production = os.environ.get("ENV", "").lower() == "production"
app.add_middleware(EnforceMFAMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("SESSION_SECRET", secrets.token_urlsafe(32)),
    same_site="lax",
    https_only=_is_production,
)

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> HTMLResponse:
    detail = str(exc.detail or "")
    is_premium_gate = exc.status_code == 403 and "upgrade" in detail.lower()
    ctx = {
        "status_code": exc.status_code,
        "message": detail,
        "is_premium_gate": is_premium_gate,
    }
    resp = render(request, "error.html", **ctx)
    resp.status_code = exc.status_code
    return resp


@app.on_event("startup")
def _startup() -> None:
    validate_env()
    init_db()
    start_scheduler()


@app.on_event("shutdown")
def _shutdown() -> None:
    stop_scheduler()


def _format_dt(value):
    if not value:
        return "—"
    if isinstance(value, datetime):
        return value.strftime("%b %d, %Y")
    return str(value)


def _format_size(value):
    try:
        n = float(value or 0)
    except (TypeError, ValueError):
        return "—"
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _days_from_now(value) -> int:
    if not value or not isinstance(value, datetime):
        return 0
    return (value.date() - datetime.utcnow().date()).days


def _end_of_month(value) -> str:
    """Return the last day of the month for a given date, formatted like 'May 31, 2026'."""
    if not value or not isinstance(value, datetime):
        return "—"
    import calendar
    last_day = calendar.monthrange(value.year, value.month)[1]
    eom = value.replace(day=last_day)
    return eom.strftime("%b %d, %Y")


templates.env.filters["dt"] = _format_dt
templates.env.filters["filesize"] = _format_size
templates.env.filters["days_from_now"] = _days_from_now
templates.env.filters["end_of_month"] = _end_of_month


def render(request: Request, template: str, **ctx) -> HTMLResponse:
    ctx.setdefault("user", current_user(request))
    ctx.setdefault("flash", request.session.pop("flash", None))
    u = ctx.get("user")
    is_prem = has_premium(u)
    is_prem_plus = has_premium_plus(u)
    ctx.setdefault("is_premium", is_prem)
    ctx.setdefault("is_premium_plus", is_prem_plus)
    ctx.setdefault("subscription_tier", getattr(u, "subscription_tier", "free") if u else "free")
    ctx.setdefault("premium_features", PREMIUM_FEATURES)
    ctx.setdefault("premium_plus_features", PREMIUM_PLUS_FEATURES)
    if u is not None:
        ctx.setdefault("ai_features_enabled", is_prem and ai_enabled())
    else:
        ctx.setdefault("ai_features_enabled", False)
    ctx.setdefault("is_dev", not _is_production)
    ctx.setdefault("cf_turnstile_site_key", os.environ.get("CLOUDFLARE_TURNSTILE_SITE_KEY", ""))
    return templates.TemplateResponse(request, template, ctx)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    if current_user(request):
        return RedirectResponse("/dashboard", status_code=302)
    return RedirectResponse("/login", status_code=302)


@app.get("/login", response_class=HTMLResponse)
def login(request: Request):
    if current_user(request):
        return RedirectResponse("/dashboard", status_code=302)
    return render(
        request,
        "login.html",
        google_ready=google_configured(),
    )


@app.get("/auth/google")
async def google_start(request: Request):
    auth_limiter.check(request)
    if not google_configured():
        raise HTTPException(503, "Google sign-in is not configured yet.")
    redirect_uri = str(request.url_for("google_callback"))
    if redirect_uri.startswith("http://") and "localhost" not in redirect_uri and "127.0.0.1" not in redirect_uri:
        redirect_uri = "https://" + redirect_uri[len("http://"):]
    import logging
    logging.warning(f"[OAuth] redirect_uri being sent to Google: {redirect_uri}")
    return await oauth.google.authorize_redirect(request, redirect_uri)


@app.get("/auth/google/callback", name="google_callback")
async def google_callback(request: Request, db: Session = Depends(get_session)):
    auth_limiter.check(request)
    try:
        token = await oauth.google.authorize_access_token(request)
    except Exception as e:
        import logging
        logging.warning(f"[OAuth] callback error: {e}")
        request.session["flash"] = f"Google sign-in failed: {e}"
        return RedirectResponse("/login", status_code=302)
    info = token.get("userinfo") or {}
    sub = info.get("sub")
    email = info.get("email")
    if not sub or not email:
        raise HTTPException(400, "Google did not return a profile.")
    user = db.query(User).filter_by(google_sub=sub).one_or_none()
    if not user:
        user = User(
            google_sub=sub,
            email=email,
            name=info.get("name"),
            picture=info.get("picture"),
            subscription_tier="free",
        )
        db.add(user)
    else:
        user.email = email
        user.name = info.get("name") or user.name
        user.picture = info.get("picture") or user.picture
    is_new = user.id is None
    db.commit()
    log_event("user_signup" if is_new else "user_login", user_id=user.id, db=db)
    request.session["user_id"] = user.id
    request.session["flash"] = f"Signed in as {user.email}"
    if _is_production and not getattr(user, "mfa_enabled", False):
        return RedirectResponse("/security/mfa/setup", status_code=302)
    return RedirectResponse("/dashboard", status_code=302)


@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_session)):
    user = require_user(request)
    docs = (
        db.query(Document)
        .filter_by(user_id=user.id)
        .order_by(Document.expires_at.is_(None), Document.expires_at.asc())
        .all()
    )
    summary = summarize(docs)
    share_links = (
        db.query(ShareLink)
        .filter_by(user_id=user.id)
        .filter(ShareLink.revoked_at.is_(None))
        .order_by(ShareLink.created_at.desc())
        .limit(5)
        .all()
    )
    return render(
        request,
        "dashboard.html",
        summary=summary,
        docs=docs,
        share_links=share_links,
        status_for=status_for,
        days_until=days_until,
        ui_status_label=ui_status_label,
    )


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------

@app.get("/documents", response_class=HTMLResponse)
def documents_list(
    request: Request,
    q: Optional[str] = None,
    db: Session = Depends(get_session),
):
    user = require_user(request)
    docs = (
        db.query(Document)
        .filter_by(user_id=user.id)
        .order_by(Document.sort_order.asc(), Document.category.asc(), Document.title.asc())
        .all()
    )
    if q and q.strip():
        needle = q.strip().lower()
        docs = [
            d
            for d in docs
            if needle in (d.title or "").lower()
            or needle in (d.original_filename or "").lower()
            or needle in (d.category or "").lower()
        ]
    by_cat: dict[str, list[Document]] = defaultdict(list)
    for d in docs:
        bucket = normalized_effective_category(d.category)
        by_cat[bucket].append(d)
    for c in CATEGORY_ORDER:
        by_cat.setdefault(c, [])

    return render(
        request,
        "documents.html",
        docs=docs,
        docs_by_category=by_cat,
        vault_tabs=CATEGORY_ORDER,
        q=q or "",
        status_for=status_for,
        days_until=days_until,
        ui_status_label=ui_status_label,
    )


@app.post("/documents/analyze")
async def analyze_document(
    request: Request,
    file: UploadFile = File(...),
):
    require_user(request)
    raw = await file.read(5 * 1024 * 1024)
    meta = extract_document_metadata(raw, file.content_type, file.filename or "")
    return JSONResponse(meta)


@app.get("/documents/upload", response_class=HTMLResponse)
def upload_form(request: Request, category: Optional[str] = None):
    user = require_user(request)
    return render(
        request,
        "upload.html",
        categories=CREDENTIAL_CATEGORIES,
        us_states=US_STATES,
        preset_category=category or "",
        advanced_ai_available=user_has_premium(user) and ai_enabled(),
        cf_turnstile_site_key=os.environ.get("CLOUDFLARE_TURNSTILE_SITE_KEY", ""),
    )


def _parse_date(value: str) -> Optional[datetime]:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return None


@app.post("/documents/scan")
async def scan_upload(
    request: Request,
    file: UploadFile = File(...),
):
    """Pre-upload threat scan. Returns JSON so the client can animate the result."""
    require_user(request)
    from .security import scan_file, validate_upload
    raw = await file.read()
    if not raw:
        from fastapi.responses import JSONResponse
        return JSONResponse({"clean": False, "threat": "Empty file.", "checks": []})
    fname = file.filename or ""
    try:
        effective_mime = validate_upload(raw, fname, file.content_type)
    except HTTPException as exc:
        from fastapi.responses import JSONResponse
        return JSONResponse({"clean": False, "threat": exc.detail, "checks": []})
    result = scan_file(raw, fname, effective_mime)
    from fastapi.responses import JSONResponse
    return JSONResponse(result)


@app.post("/documents/upload")
async def upload_submit(
    request: Request,
    title: str = Form(...),
    category: str = Form(...),
    issued_at: str = Form(""),
    expires_at: str = Form(""),
    notes: str = Form(""),
    issuing_state: str = Form(""),
    file: UploadFile = File(...),
    cf_turnstile_response: str = Form(""),
    db: Session = Depends(get_session),
):
    user = require_user(request)
    upload_limiter.check(request)
    if not has_premium(user):
        ip = (request.headers.get("X-Forwarded-For", "") or "").split(",")[0].strip() or (request.client.host if request.client else "")
        if not verify_turnstile(cf_turnstile_response, ip):
            log_event("upload_blocked_turnstile", user_id=user.id, ok=False, db=db)
            request.session["flash"] = "Bot-protection check failed — please try again."
            return RedirectResponse("/documents/upload", status_code=302)
    raw = await file.read()
    if not raw:
        request.session["flash"] = "Please choose a file to upload."
        return RedirectResponse("/documents/upload", status_code=302)
    if len(raw) > 25 * 1024 * 1024:
        request.session["flash"] = "Files must be 25 MB or smaller."
        return RedirectResponse("/documents/upload", status_code=302)

    content_hash = hashlib.sha256(raw).hexdigest()
    dup = (
        db.query(Document)
        .filter_by(user_id=user.id, content_hash=content_hash)
        .first()
    )
    if dup:
        request.session["flash"] = "Duplicate file: this upload matches an existing document (same contents)."
        return RedirectResponse("/documents", status_code=302)

    fname = file.filename or ""
    # Validate file type against allow-list using magic bytes + extension check.
    # Returns the effective (trusted) MIME type to store.
    try:
        effective_mime = validate_upload(raw, fname, file.content_type)
    except HTTPException as exc:
        request.session["flash"] = exc.detail
        return RedirectResponse("/documents/upload", status_code=302)
    title_clean = title.strip()
    cat = category.strip()
    if cat == AUTO_CATEGORY or not cat:
        cat = infer_category(fname, title_clean)
    elif cat == "Other":
        suggested = infer_category(fname, title_clean)
        if suggested != "Other":
            cat = suggested

    exp = _parse_date(expires_at)
    if not exp:
        hinted = infer_expiry_from_text(fname, title_clean)
        if hinted:
            exp = hinted

    if user_has_premium(user) and ai_enabled():
        sample = extract_text_sample(raw, effective_mime, fname)
        ai_cat, ai_exp = ai_refine_category_expiry(fname, title_clean, sample, cat or "Other", exp)
        if ai_cat:
            cat = ai_cat
        if ai_exp:
            exp = ai_exp

    # Apply custom expiration rules (e.g. NIHSS → 1 year) when no expiry is set yet.
    doc_text = extract_document_text(raw, effective_mime, fname)
    state_clean = issuing_state.strip().upper() or None
    exp, rule_applied, rule_source = apply_custom_expiration_rules(
        filename=fname,
        title=title_clean,
        text=doc_text,
        issue_date=_parse_date(issued_at),
        upload_date=datetime.utcnow(),
        existing_expires=exp,
        state=state_clean,
    )

    suffix = Path(fname).suffix
    stored, size = save_upload(user.id, raw, suffix)
    doc = Document(
        user_id=user.id,
        profile_id=None,
        category=cat or "Other",
        title=title_clean,
        notes=notes.strip() or None,
        issued_at=_parse_date(issued_at),
        expires_at=exp,
        stored_filename=stored,
        original_filename=fname or stored,
        mime_type=effective_mime,
        size_bytes=size,
        content_hash=content_hash,
        expiration_rule_applied=rule_applied,
        expiration_source=rule_source,
        issuing_state=state_clean,
    )
    db.add(doc)
    db.commit()
    log_event("document_upload", user_id=user.id, meta={"filename": doc.original_filename, "title": doc.title, "category": doc.category, "mime": doc.mime_type}, db=db)
    request.session["flash"] = f"Saved \"{doc.title}\"."
    return RedirectResponse("/documents", status_code=302)


@app.get("/documents/{doc_id}/thumb")
def document_thumb(doc_id: int, request: Request, db: Session = Depends(get_session)):
    user = require_user(request)
    doc = db.get(Document, doc_id)
    if not doc or doc.user_id != user.id:
        log_event("document_access_denied", user_id=user.id, ok=False, meta={"doc_id": doc_id, "route": "thumb"}, db=db)
        raise HTTPException(404)
    mime = doc.mime_type or ""
    if not mime.startswith("image/"):
        raise HTTPException(404, "No thumbnail for this file type.")
    p = file_path(user.id, doc.stored_filename)
    if not p.exists():
        raise HTTPException(404, "File missing.")
    return Response(
        content=p.read_bytes(),
        media_type=mime,
        headers={"Cache-Control": "private, max-age=86400"},
    )


@app.post("/documents/reorder")
async def reorder_documents(request: Request, db: Session = Depends(get_session)):
    user = require_user(request)
    data = await request.json()
    ids = data.get("ids", [])
    for position, doc_id in enumerate(ids):
        doc = db.get(Document, int(doc_id))
        if doc and doc.user_id == user.id:
            doc.sort_order = position
    db.commit()
    return JSONResponse({"ok": True})


@app.get("/documents/{doc_id}/edit", response_class=HTMLResponse)
def edit_document_form(doc_id: int, request: Request, db: Session = Depends(get_session)):
    user = require_user(request)
    doc = db.get(Document, doc_id)
    if not doc or doc.user_id != user.id:
        log_event("document_access_denied", user_id=user.id, ok=False, meta={"doc_id": doc_id, "route": "edit"}, db=db)
        raise HTTPException(404)
    return render(request, "edit_document.html", doc=doc, categories=CREDENTIAL_CATEGORIES, us_states=US_STATES)


@app.post("/documents/{doc_id}/edit")
def edit_document_submit(
    doc_id: int,
    request: Request,
    title: str = Form(...),
    category: str = Form(...),
    issued_at: str = Form(""),
    expires_at: str = Form(""),
    notes: str = Form(""),
    issuing_state: str = Form(""),
    db: Session = Depends(get_session),
):
    user = require_user(request)
    doc = db.get(Document, doc_id)
    if not doc or doc.user_id != user.id:
        log_event("document_access_denied", user_id=user.id, ok=False, meta={"doc_id": doc_id, "route": "edit_post"}, db=db)
        raise HTTPException(404)
    doc.title = title.strip() or doc.title
    doc.category = category if category in CREDENTIAL_CATEGORIES else doc.category
    doc.notes = notes.strip() or None
    doc.issued_at = _parse_date(issued_at)
    doc.expires_at = _parse_date(expires_at)
    doc.issuing_state = issuing_state.strip().upper() or None
    db.commit()
    request.session["flash"] = "Document updated."
    return RedirectResponse("/documents", status_code=302)


@app.post("/documents/{doc_id}/delete")
def delete_document(doc_id: int, request: Request, db: Session = Depends(get_session)):
    user = require_user(request)
    mfa_check = _mfa_gate(request, user)
    if mfa_check:
        return mfa_check
    doc = db.get(Document, doc_id)
    if not doc or doc.user_id != user.id:
        log_event("document_access_denied", user_id=user.id, ok=False, meta={"doc_id": doc_id, "route": "delete"}, db=db)
        raise HTTPException(404)
    delete_file(user.id, doc.stored_filename)
    db.delete(doc)
    db.commit()
    request.session["flash"] = f"Deleted {doc.title}."
    return RedirectResponse("/documents", status_code=302)


@app.get("/documents/{doc_id}/view")
def view_document(doc_id: int, request: Request, db: Session = Depends(get_session)):
    user = require_user(request)
    preview_limiter.check(request)
    doc = db.get(Document, doc_id)
    if not doc or doc.user_id != user.id:
        log_event("document_access_denied", user_id=user.id, ok=False, meta={"doc_id": doc_id, "route": "view"}, db=db)
        raise HTTPException(404)
    p = file_path(user.id, doc.stored_filename)
    if not p.exists():
        raise HTTPException(404, "File missing.")
    mime = doc.mime_type or "application/octet-stream"
    disposition = "inline" if mime in INLINE_SAFE_MIMES else "attachment"
    return Response(
        content=p.read_bytes(),
        media_type=mime,
        headers={
            "Content-Disposition": f'{disposition}; filename="{doc.original_filename}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@app.get("/documents/{doc_id}/download")
def download_document(doc_id: int, request: Request, db: Session = Depends(get_session)):
    user = require_user(request)
    preview_limiter.check(request)
    doc = db.get(Document, doc_id)
    if not doc or doc.user_id != user.id:
        log_event("document_access_denied", user_id=user.id, ok=False, meta={"doc_id": doc_id, "route": "download"}, db=db)
        raise HTTPException(404)
    p = file_path(user.id, doc.stored_filename)
    if not p.exists():
        raise HTTPException(404, "File missing.")
    return Response(
        content=p.read_bytes(),
        media_type=doc.mime_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{doc.original_filename}"'},
    )


# ---------------------------------------------------------------------------
# Packet (Premium)
# ---------------------------------------------------------------------------

@app.get("/packet")
def packet(request: Request, db: Session = Depends(get_session)):
    user = require_user(request)
    if not has_premium(user):
        request.session["flash"] = "Packet download is a Premium feature — upgrade to unlock it."
        return RedirectResponse("/premium", status_code=302)
    docs = db.query(Document).filter_by(user_id=user.id).all()
    if not docs:
        request.session["flash"] = "Upload at least one document before building a packet."
        return RedirectResponse("/dashboard", status_code=302)
    blob = build_zip(user, docs)
    log_event("packet_download", user_id=user.id, meta={"doc_count": len(docs)}, db=db)
    fname = f"credentials-packet-{datetime.utcnow().strftime('%Y%m%d')}.zip"
    return Response(
        content=blob,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@app.get("/packet/pdf")
def packet_pdf(request: Request, db: Session = Depends(get_session)):
    user = require_user(request)
    if not has_premium(user):
        request.session["flash"] = "Manifest PDF is a Premium feature — upgrade to unlock it."
        return RedirectResponse("/premium", status_code=302)
    docs = db.query(Document).filter_by(user_id=user.id).order_by(Document.category.asc(), Document.title.asc()).all()
    if not docs:
        request.session["flash"] = "Upload at least one document before building a packet."
        return RedirectResponse("/dashboard", status_code=302)
    blob = build_manifest_pdf(user, docs)
    log_event("packet_pdf", user_id=user.id, meta={"doc_count": len(docs)}, db=db)
    fname = f"credentials-manifest-{datetime.utcnow().strftime('%Y%m%d')}.pdf"
    return Response(
        content=blob,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


# ---------------------------------------------------------------------------
# Calendar (Premium)
# ---------------------------------------------------------------------------

@app.get("/calendar/expiring.ics")
def calendar_expiring_ics(request: Request, db: Session = Depends(get_session)):
    user = require_user(request)
    require_premium_plus(user)
    docs = db.query(Document).filter_by(user_id=user.id).all()
    body = build_expiring_ics(docs, calendar_name="Expiring credentials")
    return Response(
        content=body,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="credential-expirations.ics"'},
    )


# ---------------------------------------------------------------------------
# Share links (Premium+)
# ---------------------------------------------------------------------------

@app.get("/share", response_class=HTMLResponse)
def share_index(request: Request, db: Session = Depends(get_session)):
    user = require_user(request)
    if not has_premium_plus(user):
        request.session["flash"] = "Shared Links is a Premium Plus feature — upgrade to create recruiter-ready share links."
        return RedirectResponse("/premium", status_code=302)
    links = (
        db.query(ShareLink)
        .filter_by(user_id=user.id)
        .order_by(ShareLink.created_at.desc())
        .all()
    )
    base = str(request.base_url).rstrip("/")
    return render(request, "share.html", links=links, base_url=base)


@app.post("/share/create")
def share_create(
    request: Request,
    label: str = Form(""),
    expires_days: str = Form(""),
    db: Session = Depends(get_session),
):
    user = require_user(request)
    require_premium_plus(user)
    share_limiter.check(request)
    mfa_check = _mfa_gate(request, user)
    if mfa_check:
        return mfa_check
    exp: datetime | None = None
    if expires_days and expires_days.strip().isdigit():
        exp = datetime.utcnow() + timedelta(days=int(expires_days.strip()))
    link = ShareLink(
        user_id=user.id,
        token=secrets.token_urlsafe(24),
        label=label.strip() or "Recruiter share",
        profile_id=None,
        expires_at=exp,
    )
    db.add(link)
    db.commit()
    log_event("share_link_created", user_id=user.id, meta={"label": link.label}, db=db)
    request.session["flash"] = "Share link created."
    return RedirectResponse("/share", status_code=302)


@app.post("/share/{link_id}/revoke")
def share_revoke(link_id: int, request: Request, db: Session = Depends(get_session)):
    user = require_user(request)
    require_premium_plus(user)
    link = db.get(ShareLink, link_id)
    if not link or link.user_id != user.id:
        raise HTTPException(404)
    link.revoked_at = datetime.utcnow()
    db.commit()
    request.session["flash"] = "Share link revoked."
    return RedirectResponse("/share", status_code=302)


def _resolve_share(token: str, db: Session) -> tuple[ShareLink, User]:
    link = db.query(ShareLink).filter_by(token=token).one_or_none()
    if not link or link.revoked_at is not None:
        raise HTTPException(404, "This share link is no longer active.")
    if link.expires_at is not None and link.expires_at < datetime.utcnow():
        raise HTTPException(404, "This share link has expired.")
    user = db.get(User, link.user_id)
    if not user:
        raise HTTPException(404)
    return link, user


# ---------------------------------------------------------------------------
# Recruiter template feedback (public, no auth)
# ---------------------------------------------------------------------------

_RTF_ROLE_TYPES = [
    "Travel Nurse", "Per Diem Nurse", "Staff Nurse",
    "Allied Health", "CNA/LVN/LPN", "Other Healthcare",
]
_RTF_DOCUMENTS = [
    "Resume", "State License", "Compact License", "BLS", "ACLS", "PALS",
    "NIHSS", "TNCC", "ENPC", "Skills Checklist", "Physical Exam", "TB Test",
    "Fit Test", "Immunization Records", "COVID Vaccine", "Flu Vaccine", "Hep B",
    "MMR", "Varicella", "Tdap", "Drug Screen", "Background Check", "I-9", "W-4",
    "Direct Deposit", "References", "Driver License", "Social Security Card",
    "CPR Card", "Nursys Verification", "Unit Competency Exam",
]
_RTF_TIMINGS = [
    "Before submission", "After offer", "Before start date", "Varies by facility",
]
_RTF_AGENCY_TYPES = [
    "Travel agency", "Per diem registry", "Hospital HR",
    "Credentialing team", "MSP/VMS", "Other",
]


@app.post("/api/recruiter-feedback/opened")
async def recruiter_feedback_opened(request: Request, db: Session = Depends(get_session)):
    """Log that a recruiter opened the feedback modal (fire-and-forget, never errors)."""
    try:
        body = await request.json()
        share_token = (body.get("share_token") or "").strip()
        sl = db.query(ShareLink).filter_by(token=share_token).first() if share_token else None
        log_event("recruiter_feedback_opened", user_id=sl.user_id if sl else None,
                  meta={"share_token_id": sl.id if sl else None}, db=db)
    except Exception:
        pass
    return JSONResponse({"ok": True})


@app.post("/api/recruiter-feedback")
async def recruiter_feedback_submit(request: Request, db: Session = Depends(get_session)):
    feedback_limiter.check(request)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON")

    role_type    = (body.get("role_type") or "").strip()
    timing       = (body.get("timing") or "").strip()
    agency_type  = (body.get("agency_type") or "").strip()
    docs_raw     = body.get("required_documents") or []
    opt_email    = (body.get("optional_email") or "").strip() or None
    share_token  = (body.get("share_token") or "").strip()
    cf_token     = (body.get("cf_token") or "").strip()

    if not role_type or not timing or not agency_type:
        raise HTTPException(422, "Missing required fields")
    if role_type not in _RTF_ROLE_TYPES:
        raise HTTPException(422, "Invalid role_type")
    if timing not in _RTF_TIMINGS:
        raise HTTPException(422, "Invalid timing")
    if agency_type not in _RTF_AGENCY_TYPES:
        raise HTTPException(422, "Invalid agency_type")

    docs_clean = [d for d in docs_raw if d in _RTF_DOCUMENTS][:50]

    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "")
    if not verify_turnstile(cf_token, ip):
        raise HTTPException(403, "Bot protection check failed")

    link_id: int | None = None
    if share_token:
        sl = db.query(ShareLink).filter_by(token=share_token).first()
        link_id = sl.id if sl else None

    import json as _json
    row = text(
        "INSERT INTO recruiter_template_feedback "
        "(share_token_id, role_type, required_documents, timing, agency_type, optional_email, user_agent) "
        "VALUES (:stid, :rt, :rd, :tm, :at, :oe, :ua)"
    )
    with db.begin_nested():
        db.execute(row, {
            "stid": link_id,
            "rt": role_type,
            "rd": _json.dumps(docs_clean),
            "tm": timing,
            "at": agency_type,
            "oe": opt_email,
            "ua": request.headers.get("user-agent", "")[:500],
        })
    db.commit()

    owner_id: int | None = None
    if link_id:
        sl2 = db.get(ShareLink, link_id)
        owner_id = sl2.user_id if sl2 else None

    log_event("recruiter_feedback_submitted", user_id=owner_id, meta={
        "role_type": role_type,
        "document_count_selected": len(docs_clean),
        "agency_type": agency_type,
        "timing": timing,
        "has_optional_email": bool(opt_email),
        "share_token_id": link_id,
    }, db=db)

    return JSONResponse({"ok": True})


@app.get("/admin/recruiter-feedback", response_class=HTMLResponse)
def admin_recruiter_feedback(request: Request, db: Session = Depends(get_session)):
    user = require_user(request)
    require_admin(user)
    import json as _json
    rows = db.execute(text(
        "SELECT id, role_type, required_documents, timing, agency_type, optional_email, created_at "
        "FROM recruiter_template_feedback ORDER BY created_at DESC LIMIT 200"
    )).fetchall()

    total = db.execute(text("SELECT COUNT(*) FROM recruiter_template_feedback")).scalar() or 0

    doc_counts: dict[str, int] = {}
    role_counts: dict[str, int] = {}
    timing_counts: dict[str, int] = {}
    for r in rows:
        role_counts[r.role_type] = role_counts.get(r.role_type, 0) + 1
        timing_counts[r.timing] = timing_counts.get(r.timing, 0) + 1
        try:
            for d in _json.loads(r.required_documents or "[]"):
                doc_counts[d] = doc_counts.get(d, 0) + 1
        except Exception:
            pass

    top_docs  = sorted(doc_counts.items(), key=lambda x: x[1], reverse=True)[:15]
    top_roles = sorted(role_counts.items(), key=lambda x: x[1], reverse=True)
    top_timing = sorted(timing_counts.items(), key=lambda x: x[1], reverse=True)

    submissions = []
    for r in rows:
        try:
            doc_list = _json.loads(r.required_documents or "[]")
        except Exception:
            doc_list = []
        submissions.append({
            "id": r.id,
            "created_at": r.created_at,
            "role_type": r.role_type,
            "agency_type": r.agency_type,
            "timing": r.timing,
            "docs": doc_list,
            "has_email": bool(r.optional_email),
        })

    return render(request, "admin_recruiter_feedback.html",
        total=total,
        top_docs=top_docs,
        top_roles=top_roles,
        top_timing=top_timing,
        submissions=submissions,
    )


@app.get("/admin/recruiter-feedback/export.csv")
def admin_recruiter_feedback_csv(request: Request, db: Session = Depends(get_session)):
    user = require_user(request)
    require_admin(user)
    import csv, io as _io, json as _json
    rows = db.execute(text(
        "SELECT id, role_type, required_documents, timing, agency_type, optional_email, created_at "
        "FROM recruiter_template_feedback ORDER BY created_at DESC"
    )).fetchall()
    buf = _io.StringIO()
    w = csv.writer(buf)
    w.writerow(["ID", "Date", "Role Type", "Agency Type", "Timing", "Documents", "Email Present"])
    for r in rows:
        try:
            docs = ", ".join(_json.loads(r.required_documents or "[]"))
        except Exception:
            docs = ""
        w.writerow([r.id, r.created_at, r.role_type, r.agency_type, r.timing, docs, "Yes" if r.optional_email else "No"])
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="recruiter-feedback.csv"'},
    )


@app.get("/s/{token}", response_class=HTMLResponse)
def share_view(token: str, request: Request, db: Session = Depends(get_session)):
    share_limiter.check(request)
    link, owner = _resolve_share(token, db)
    docs = db.query(Document).filter_by(user_id=owner.id).order_by(Document.category.asc(), Document.title.asc()).all()
    summary = summarize(docs)
    dl_tokens = {d.id: make_download_token(d.id, token) for d in docs}
    return render(
        request,
        "share_view.html",
        link=link,
        owner=owner,
        docs=docs,
        summary=summary,
        status_for=status_for,
        days_until=days_until,
        ui_status_label=ui_status_label,
        public_view=True,
        dl_tokens=dl_tokens,
    )


@app.get("/s/{token}/download/{doc_id}")
def share_download(token: str, doc_id: int, request: Request, dl: str = "", db: Session = Depends(get_session)):
    preview_limiter.check(request)
    link, owner = _resolve_share(token, db)
    if dl and not verify_download_token(dl, doc_id, token):
        log_event("share_download_denied", user_id=owner.id, ok=False,
                  meta={"doc_id": doc_id, "reason": "invalid_dl_token"}, db=db)
        raise HTTPException(403, "This download link has expired. Reload the share page to get a fresh link.")
    doc = db.get(Document, doc_id)
    if not doc or doc.user_id != owner.id:
        log_event("share_download_denied", user_id=owner.id, ok=False,
                  meta={"doc_id": doc_id, "reason": "wrong_owner"}, db=db)
        raise HTTPException(404)
    p = file_path(owner.id, doc.stored_filename)
    if not p.exists():
        raise HTTPException(404)
    log_event("share_download", user_id=owner.id, meta={"doc_id": doc_id, "share_token": token[:8]}, db=db)
    return Response(
        content=p.read_bytes(),
        media_type=doc.mime_type or "application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{doc.original_filename}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@app.get("/s/{token}/packet")
def share_packet(token: str, db: Session = Depends(get_session)):
    link, owner = _resolve_share(token, db)
    docs = db.query(Document).filter_by(user_id=owner.id).all()
    if not docs:
        raise HTTPException(404, "No documents to package.")
    blob = build_zip(owner, docs)
    fname = f"{(owner.name or owner.email).split('@')[0]}-credentials.zip"
    return Response(
        content=blob,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@app.get("/s/{token}/packet/pdf")
def share_packet_pdf(token: str, db: Session = Depends(get_session)):
    link, owner = _resolve_share(token, db)
    docs = db.query(Document).filter_by(user_id=owner.id).order_by(Document.category.asc(), Document.title.asc()).all()
    if not docs:
        raise HTTPException(404, "No documents to package.")
    blob = build_manifest_pdf(owner, docs)
    fname = f"{(owner.name or owner.email).split('@')[0]}-manifest.pdf"
    return Response(
        content=blob,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


# ---------------------------------------------------------------------------
# Premium page
# ---------------------------------------------------------------------------

@app.get("/premium", response_class=HTMLResponse)
def premium_page(request: Request):
    user = require_user(request)
    log_event("premium_clicked", user_id=user.id, meta={"source": "premium_page"})
    ids = price_ids()
    return render(
        request,
        "premium.html",
        stripe_configured=stripe_configured(),
        price_premium_monthly=ids["premium_monthly"],
        price_premium_yearly=ids["premium_yearly"],
        price_premium_plus_monthly=ids["premium_plus_monthly"],
        price_premium_plus_yearly=ids["premium_plus_yearly"],
    )


# ---------------------------------------------------------------------------
# Premium routes
# ---------------------------------------------------------------------------

@app.get("/premium/reminders/settings", response_class=HTMLResponse)
def reminders_settings_get(request: Request, db: Session = Depends(get_session)):
    user = require_user(request)
    require_premium(user)
    settings = db.query(ReminderSettings).filter_by(user_id=user.id).first()
    return render(
        request,
        "premium_reminders.html",
        settings=settings,
        email_status=get_email_status(),
        sms_status=get_sms_status(),
    )


@app.post("/premium/reminders/settings")
def reminders_settings_post(
    request: Request,
    email_enabled: str = Form("0"),
    sms_enabled: str = Form("0"),
    reminder_email: str = Form(""),
    phone_number: str = Form(""),
    reminder_days: str = Form("30,14,7,0"),
    db: Session = Depends(get_session),
):
    user = require_user(request)
    require_premium(user)
    settings = db.query(ReminderSettings).filter_by(user_id=user.id).first()
    if not settings:
        settings = ReminderSettings(user_id=user.id)
        db.add(settings)
    settings.email_enabled = 1 if email_enabled in ("1", "on", "true") else 0
    # SMS only for premium_plus
    want_sms = sms_enabled in ("1", "on", "true")
    settings.sms_enabled = 1 if (want_sms and has_premium_plus(user)) else 0
    settings.reminder_email = reminder_email.strip() or user.email
    settings.phone_number = phone_number.strip() or None
    settings.reminder_days = reminder_days.strip() or "30,14,7,0"
    settings.updated_at = datetime.utcnow()
    db.commit()
    if settings.email_enabled or settings.sms_enabled:
        log_event("reminders_enabled", user_id=user.id, meta={"email": bool(settings.email_enabled), "sms": bool(settings.sms_enabled)}, db=db)
    request.session["flash"] = "Reminder settings saved."
    return RedirectResponse("/premium/reminders/settings", status_code=302)


@app.post("/api/reminders/test-email")
def reminders_test_email(request: Request, db: Session = Depends(get_session)):
    user = require_user(request)
    require_premium(user)
    result = send_test_email(user)
    return JSONResponse(result)


@app.post("/api/reminders/test-sms")
def reminders_test_sms(request: Request, db: Session = Depends(get_session)):
    user = require_user(request)
    require_premium_plus(user)
    result = send_test_sms(user)
    return JSONResponse(result)


@app.get("/api/reminders/logs")
def reminders_logs(request: Request, db: Session = Depends(get_session)):
    user = require_user(request)
    require_premium(user)
    logs = (
        db.query(ReminderLog)
        .filter_by(user_id=user.id)
        .order_by(ReminderLog.sent_at.desc())
        .limit(20)
        .all()
    )
    return JSONResponse([{
        "id": lg.id,
        "document_id": lg.document_id,
        "reminder_type": lg.reminder_type,
        "days_before": lg.days_before,
        "sent_at": lg.sent_at.isoformat() if lg.sent_at else None,
        "status": lg.status,
        "error_message": lg.error_message,
    } for lg in logs])


def _get_or_create_calendar_token(user, db: Session) -> str:
    """Return the user's calendar token, creating one if absent."""
    import secrets
    db_user = db.get(User, user.id)
    if not db_user.calendar_token:
        db_user.calendar_token = secrets.token_urlsafe(32)
        db.commit()
    return db_user.calendar_token


@app.get("/calendar/feed/{token}.ics")
def public_calendar_feed(token: str, db: Session = Depends(get_session)):
    """Public, unauthenticated live .ics feed — subscribed to by calendar apps."""
    db_user = db.query(User).filter_by(calendar_token=token).first()
    if not db_user:
        raise HTTPException(404)
    from .premium import has_premium_plus
    if not has_premium_plus(db_user):
        raise HTTPException(403)
    docs = db.query(Document).filter_by(user_id=db_user.id).all()
    body = build_expiring_ics(docs, calendar_name="Credanta — Expiring Credentials")
    return Response(
        content=body,
        media_type="text/calendar; charset=utf-8",
        headers={"Cache-Control": "no-cache, no-store"},
    )


@app.get("/premium/calendar", response_class=HTMLResponse)
def premium_calendar_get(request: Request, db: Session = Depends(get_session)):
    user = require_user(request)
    require_premium_plus(user)
    token = _get_or_create_calendar_token(user, db)
    base = os.environ.get("APP_BASE_URL") or (
        f"https://{os.environ['REPLIT_DEV_DOMAIN']}"
        if os.environ.get("REPLIT_DEV_DOMAIN")
        else "https://credanta.com"
    )
    feed_url = f"{base}/calendar/feed/{token}.ics"
    return render(request, "premium_calendar.html", feed_url=feed_url)


@app.post("/premium/calendar/regenerate")
def premium_calendar_regenerate(request: Request, db: Session = Depends(get_session)):
    import secrets
    user = require_user(request)
    require_premium_plus(user)
    db_user = db.get(User, user.id)
    db_user.calendar_token = secrets.token_urlsafe(32)
    db.commit()
    log_event("calendar_token_regenerated", user_id=user.id, meta={}, db=db)
    request.session["flash"] = "Calendar feed URL regenerated. Update your calendar subscription."
    return RedirectResponse("/premium/calendar", status_code=302)


@app.get("/premium/calendar/export")
def premium_calendar_export(request: Request, db: Session = Depends(get_session)):
    """Legacy manual download — kept for backwards compat, now redirects to the feed page."""
    user = require_user(request)
    require_premium_plus(user)
    return RedirectResponse("/premium/calendar", status_code=302)


@app.get("/premium/packet/generate")
def premium_packet_generate(request: Request, db: Session = Depends(get_session)):
    user = require_user(request)
    require_premium(user)
    docs = db.query(Document).filter_by(user_id=user.id).all()
    if not docs:
        request.session["flash"] = "Upload at least one document before building a packet."
        return RedirectResponse("/premium", status_code=302)
    blob = build_zip(user, docs)
    fname = f"credentials-packet-{datetime.utcnow().strftime('%Y%m%d')}.zip"
    return Response(
        content=blob,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@app.get("/resume", response_class=HTMLResponse)
def resume_redirect(request: Request):
    return RedirectResponse("/premium/resume/enhance", status_code=301)


@app.get("/resume-enhancer", response_class=HTMLResponse)
def resume_enhancer_alias(request: Request):
    return RedirectResponse("/premium/resume/enhance", status_code=301)


@app.get("/premium/resume/enhance", response_class=HTMLResponse)
def resume_enhance_get(request: Request):
    from .resume_enhancer import TARGET_ROLES, TONES
    user = require_user(request)
    require_premium(user)
    return render(request, "premium_resume.html",
                  analysis=None, filename=None, versions={},
                  target_roles=TARGET_ROLES, tones=TONES,
                  sel_role="Travel Nurse", sel_tone="Professional")


@app.post("/premium/resume/enhance", response_class=HTMLResponse)
async def resume_enhance_post(
    request: Request,
    resume_text: str = Form(""),
    target_role: str = Form("Travel Nurse"),
    tone: str = Form("Professional"),
    file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_session),
):
    from .resume_enhancer import enhance_resume, TARGET_ROLES, TONES
    user = require_user(request)

    raw, mime, fname = b"", "", ""
    if file and file.filename:
        raw = await file.read()
        if len(raw) > 10 * 1024 * 1024:
            request.session["flash"] = "Resume file must be 10 MB or smaller."
            return RedirectResponse("/premium/resume/enhance", status_code=302)
        mime  = file.content_type or ""
        fname = file.filename or "resume"

    if not raw and not resume_text.strip():
        request.session["flash"] = "Please upload a file or paste your resume text."
        return RedirectResponse("/premium/resume/enhance", status_code=302)

    # Extract text once so both the analyser and rewriter can use it
    if resume_text.strip():
        extracted_text = resume_text.strip()
    elif raw:
        try:
            from .smart_categorize import _extract_text as _smart_extract
            extracted_text = _smart_extract(raw, mime, fname)
        except Exception:
            extracted_text = ""
    else:
        extracted_text = ""

    analysis = enhance_resume(
        raw=raw, mime_type=mime, filename=fname,
        text_input=extracted_text,
        target_role=target_role, tone=tone,
    )

    versions: dict = {}
    if extracted_text and len(extracted_text.strip()) > 50:
        try:
            from .resume_rewriter import rewrite_resume
            versions = rewrite_resume(extracted_text, target_role)
        except Exception as _exc:
            import logging
            logging.getLogger(__name__).warning(f"[ResumeRewriter] failed: {_exc}")

    log_event("resume_analyzed", user_id=user.id,
              meta={"target_role": target_role, "tone": tone,
                    "score": analysis.get("overall_score"),
                    "versions_generated": len(versions),
                    "tier": getattr(user, "subscription_tier", "free")}, db=db)
    return render(
        request,
        "premium_resume.html",
        analysis=analysis,
        versions=versions,
        filename=fname or "(pasted text)",
        target_roles=TARGET_ROLES, tones=TONES,
        sel_role=target_role, sel_tone=tone,
    )


@app.post("/resume/save-analysis")
async def resume_save_analysis(
    request: Request,
    target_role: str = Form(""),
    tone: str = Form(""),
    overall_score: int = Form(0),
    category_scores_json: str = Form("{}"),
    suggestions_json: str = Form("[]"),
    db: Session = Depends(get_session),
):
    from .db import ResumeAnalysis
    user = require_user(request)
    ra = ResumeAnalysis(
        user_id=user.id,
        target_role=target_role or None,
        tone=tone or None,
        overall_score=overall_score,
        category_scores=category_scores_json,
        suggestions=suggestions_json,
    )
    db.add(ra)
    db.commit()
    request.session["flash"] = "Analysis saved."
    return RedirectResponse("/premium/resume/enhance", status_code=302)


# ---------------------------------------------------------------------------
# Premium+ routes
# ---------------------------------------------------------------------------

@app.get("/checklist", response_class=HTMLResponse)
def checklist_redirect(request: Request):
    return RedirectResponse("/premium-plus/checklist", status_code=301)


@app.get("/premium-plus/checklist", response_class=HTMLResponse)
def checklist_get(request: Request, db: Session = Depends(get_session)):
    user = require_user(request)
    require_premium_plus(user)
    from .checklist import PROFILE_NAMES
    last = db.query(ChecklistResult).filter_by(user_id=user.id).order_by(ChecklistResult.created_at.desc()).first()
    return render(request, "premium_checklist.html", profile_names=PROFILE_NAMES, result=last)


@app.post("/premium-plus/checklist/generate", response_class=HTMLResponse)
def checklist_generate(
    request: Request,
    profile_type: str = Form(...),
    db: Session = Depends(get_session),
):
    user = require_user(request)
    from .checklist import PROFILE_NAMES, generate_checklist
    docs = db.query(Document).filter_by(user_id=user.id).all()
    result_data = generate_checklist(profile_type, docs)

    result = ChecklistResult(
        user_id=user.id,
        profile_type=profile_type,
        missing_items=json.dumps(result_data["missing"]),
        completed_items=json.dumps(result_data["completed"]),
        expiring_items=json.dumps(result_data["expiring"]),
        expired_items=json.dumps(result_data["expired"]),
        readiness_score=result_data["readiness_score"],
    )
    db.add(result)
    db.commit()
    log_event("checklist_generate", user_id=user.id, meta={"profile": profile_type, "score": result_data["readiness_score"]}, db=db)

    return render(
        request,
        "premium_checklist.html",
        profile_names=PROFILE_NAMES,
        result=result,
        result_data=result_data,
    )


@app.get("/premium-plus/agency-packet/autofill", response_class=HTMLResponse)
def agency_packet_get(request: Request):
    user = require_user(request)
    require_premium_plus(user)
    from .agency_packet import TEMPLATE_NAMES
    return render(request, "premium_agency.html", template_names=TEMPLATE_NAMES, result=None)


@app.post("/premium-plus/agency-packet/autofill", response_class=HTMLResponse)
def agency_packet_post(
    request: Request,
    template_name: str = Form(...),
    db: Session = Depends(get_session),
):
    user = require_user(request)
    require_premium_plus(user)
    from .agency_packet import TEMPLATE_NAMES, autofill_agency_packet
    docs = db.query(Document).filter_by(user_id=user.id).all()
    result = autofill_agency_packet(template_name, docs)
    return render(
        request,
        "premium_agency.html",
        template_names=TEMPLATE_NAMES,
        result=result,
        selected_template=template_name,
    )


# ---------------------------------------------------------------------------
# Security / MFA
# ---------------------------------------------------------------------------

MFA_SESSION_WINDOW = 1800  # 30 minutes


def _is_mfa_verified(request: Request) -> bool:
    """True if the session has a recent MFA verification timestamp."""
    ts = request.session.get("mfa_verified_at", 0)
    return (time.time() - ts) < MFA_SESSION_WINDOW


def _mfa_gate(request: Request, user: User) -> Optional[RedirectResponse]:
    """Return a redirect to the MFA challenge page if needed, else None."""
    if not _is_production:
        return None
    if getattr(user, "mfa_enabled", False) and not _is_mfa_verified(request):
        request.session["mfa_next"] = str(request.url)
        return RedirectResponse("/security/mfa/challenge", status_code=302)
    return None


def _mfa_signer() -> "_itsd.URLSafeSerializer":
    return _itsd.URLSafeSerializer(
        os.environ.get("SESSION_SECRET", "dev"), salt="mfa-setup"
    )


@app.get("/security", response_class=HTMLResponse)
def security_settings(request: Request, db: Session = Depends(get_session)):
    user = require_user(request)
    db_user = db.get(User, user.id)
    recovery_codes = request.session.pop("mfa_recovery_codes_display", None)
    return render(request, "security.html", user=db_user, recovery_codes=recovery_codes)


@app.get("/security/mfa/setup", response_class=HTMLResponse)
def mfa_setup_page(request: Request):
    user = require_user(request)
    secret = generate_totp_secret()
    uri = get_totp_uri(secret, user.email)
    token = _mfa_signer().dumps(secret)
    return render(
        request,
        "mfa_setup.html",
        user=user,
        totp_uri=uri,
        totp_secret_token=token,
        totp_secret_display=secret,
    )


@app.post("/security/mfa/confirm")
async def mfa_confirm(
    request: Request,
    totp_secret: str = Form(...),
    code: str = Form(...),
    db: Session = Depends(get_session),
):
    user = require_user(request)
    try:
        raw_secret = _mfa_signer().loads(totp_secret)
    except Exception:
        request.session["flash"] = "Setup session expired. Please start again."
        return RedirectResponse("/security/mfa/setup", status_code=302)

    if not verify_totp(raw_secret, code):
        request.session["flash"] = "Incorrect code — please check your authenticator and try again."
        return RedirectResponse("/security/mfa/setup", status_code=302)

    db_user = db.get(User, user.id)
    db_user.mfa_enabled = True
    db_user.mfa_method = "totp"
    db_user.mfa_totp_secret = encrypt_totp_secret(raw_secret)
    plain_codes = generate_recovery_codes()
    db_user.mfa_recovery_codes = encode_recovery_hashes([hash_recovery_code(c) for c in plain_codes])
    db.commit()
    request.session["mfa_verified_at"] = time.time()
    request.session["mfa_recovery_codes_display"] = plain_codes
    log_event("mfa_enabled", user_id=user.id, db=db)
    request.session["flash"] = "Two-step verification enabled."
    return RedirectResponse("/dashboard", status_code=302)


@app.post("/security/mfa/disable")
async def mfa_disable(request: Request, db: Session = Depends(get_session)):
    require_user(request)
    request.session["flash"] = "Two-step verification is required and cannot be disabled."
    return RedirectResponse("/dashboard", status_code=302)


@app.get("/security/mfa/challenge", response_class=HTMLResponse)
def mfa_challenge_page(request: Request):
    user = require_user(request)
    if not getattr(user, "mfa_enabled", False):
        return RedirectResponse("/security", status_code=302)
    next_url = request.session.get("mfa_next", "/dashboard")
    return render(request, "mfa_challenge.html", user=user, next_url=next_url)


@app.post("/security/mfa/challenge")
async def mfa_challenge_submit(
    request: Request,
    code: str = Form(...),
    next: str = Form("/dashboard"),
    is_recovery: str = Form(""),
    db: Session = Depends(get_session),
):
    user = require_user(request)
    db_user = db.get(User, user.id)
    if not db_user.mfa_enabled:
        safe_next = next if next.startswith("/") else "/dashboard"
        return RedirectResponse(safe_next, status_code=302)

    verified = False
    if is_recovery:
        matched, new_stored = consume_recovery_code(code, db_user.mfa_recovery_codes)
        if matched:
            db_user.mfa_recovery_codes = new_stored
            db.commit()
            verified = True
    else:
        raw_secret = decrypt_totp_secret(db_user.mfa_totp_secret or "")
        if raw_secret and verify_totp(raw_secret, code):
            verified = True

    if not verified:
        request.session["flash"] = "Incorrect code — please try again."
        return RedirectResponse("/security/mfa/challenge", status_code=302)

    request.session["mfa_verified_at"] = time.time()
    request.session.pop("mfa_next", None)
    safe_next = next if next.startswith("/") else "/dashboard"
    return RedirectResponse(safe_next, status_code=302)


@app.post("/security/recovery-codes/regenerate")
async def regenerate_recovery_codes(request: Request, db: Session = Depends(get_session)):
    user = require_user(request)
    db_user = db.get(User, user.id)
    if not db_user.mfa_enabled:
        return RedirectResponse("/security", status_code=302)
    mfa_check = _mfa_gate(request, db_user)
    if mfa_check:
        return mfa_check
    plain_codes = generate_recovery_codes()
    db_user.mfa_recovery_codes = encode_recovery_hashes([hash_recovery_code(c) for c in plain_codes])
    db.commit()
    request.session["mfa_recovery_codes_display"] = plain_codes
    request.session["flash"] = "Recovery codes regenerated."
    return RedirectResponse("/security", status_code=302)


# ---------------------------------------------------------------------------
# Account
# ---------------------------------------------------------------------------

def _fmt_bytes(n: int) -> str:
    if n < 1_024:
        return f"{n} B"
    if n < 1_048_576:
        return f"{n / 1_024:.1f} KB"
    if n < 1_073_741_824:
        return f"{n / 1_048_576:.1f} MB"
    return f"{n / 1_073_741_824:.2f} GB"


_STORAGE_LIMIT_BYTES = {"free": 500 * 1_048_576, "premium": 2 * 1_073_741_824, "premium_plus": 10 * 1_073_741_824}
_STORAGE_LIMIT_LABEL = {"free": "500 MB", "premium": "2 GB", "premium_plus": "10 GB"}


@app.get("/account", response_class=HTMLResponse)
def account_page(request: Request, db: Session = Depends(get_session)):
    user = require_user(request)
    db_user = db.get(User, user.id)
    mfa_check = _mfa_gate(request, db_user)
    if mfa_check:
        return mfa_check

    docs = db.query(Document).filter_by(user_id=user.id).all()
    summary = summarize(docs)
    valid_count = len(summary["current"]) + len(summary["no_expiry"])

    total_bytes = sum(d.size_bytes or 0 for d in docs)
    tier = getattr(db_user, "subscription_tier", "free")
    lim = _STORAGE_LIMIT_BYTES.get(tier, _STORAGE_LIMIT_BYTES["free"])
    storage_pct = min(100, int(total_bytes / lim * 100)) if lim else 0

    last_login = (
        db.query(Event)
        .filter(Event.user_id == user.id, Event.event_type == "user_login")
        .order_by(Event.created_at.desc())
        .first()
    )
    reminder_settings = db.query(ReminderSettings).filter_by(user_id=user.id).first()

    from datetime import datetime as _dt
    _now = _dt.utcnow()
    active_share_links = (
        db.query(ShareLink)
        .filter(
            ShareLink.user_id == user.id,
            ShareLink.revoked_at.is_(None),
        )
        .all()
    )
    active_share_links_count = sum(
        1 for sl in active_share_links
        if sl.expires_at is None or sl.expires_at > _now
    )

    return render(
        request,
        "account.html",
        user=db_user,
        summary=summary,
        valid_count=valid_count,
        total_bytes_fmt=_fmt_bytes(total_bytes),
        storage_pct=storage_pct,
        storage_limit_label=_STORAGE_LIMIT_LABEL.get(tier, "500 MB"),
        last_login=last_login,
        reminder_settings=reminder_settings,
        active_share_links_count=active_share_links_count,
    )


@app.post("/account/preferences")
async def account_preferences(
    request: Request,
    email_enabled: int = Form(0),
    db: Session = Depends(get_session),
):
    user = require_user(request)
    s = db.query(ReminderSettings).filter_by(user_id=user.id).first()
    if not s:
        s = ReminderSettings(user_id=user.id)
        db.add(s)
    s.email_enabled = email_enabled
    db.commit()
    request.session["flash"] = "Preferences saved."
    return RedirectResponse("/account", status_code=302)


@app.post("/account/delete")
async def account_delete_request(request: Request):
    require_user(request)
    request.session["flash"] = "Account deletion request submitted. Our team will be in touch within 30 days."
    return RedirectResponse("/account", status_code=302)


# ---------------------------------------------------------------------------
# Billing (Stripe)
# ---------------------------------------------------------------------------

@app.post("/billing/checkout")
async def billing_checkout(
    request: Request,
    price_id: str = Form(...),
    db: Session = Depends(get_session),
):
    user = require_user(request)
    mfa_check = _mfa_gate(request, user)
    if mfa_check:
        return mfa_check
    if not stripe_configured():
        request.session["flash"] = "Payments are not configured yet. Please contact support."
        return RedirectResponse("/premium", status_code=302)
    ids = price_ids()
    valid = set(ids.values()) - {""}
    if price_id not in valid:
        request.session["flash"] = "Invalid plan selected."
        return RedirectResponse("/premium", status_code=302)
    db_user = db.get(User, user.id)
    base = str(request.base_url).rstrip("/")
    try:
        session = create_checkout_session(
            db_user,
            price_id,
            success_url=f"{base}/billing/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{base}/premium",
        )
        if db_user.stripe_customer_id != session.customer:
            db_user.stripe_customer_id = session.customer
            db.commit()
        log_event("billing_checkout_started", user_id=user.id, meta={"price_id": price_id}, db=db)
    except Exception as exc:
        import logging
        logging.error(f"[Stripe] checkout error: {exc}")
        log_event("billing_checkout_started", user_id=user.id, meta={"price_id": price_id, "error": str(exc)}, ok=False)
        request.session["flash"] = "Could not start checkout — please try again."
        return RedirectResponse("/premium", status_code=302)
    return RedirectResponse(session.url, status_code=303)


@app.get("/billing/success", response_class=HTMLResponse)
def billing_success(request: Request, session_id: str = ""):
    require_user(request)
    request.session["flash"] = "Payment successful — your subscription is now active!"
    return RedirectResponse("/premium", status_code=302)


@app.get("/billing/cancel", response_class=HTMLResponse)
def billing_cancel(request: Request):
    require_user(request)
    request.session["flash"] = "Checkout cancelled — no charge was made."
    return RedirectResponse("/premium", status_code=302)


@app.get("/billing/portal")
def billing_portal(request: Request, db: Session = Depends(get_session)):
    user = require_user(request)
    mfa_check = _mfa_gate(request, user)
    if mfa_check:
        return mfa_check
    if not stripe_configured():
        request.session["flash"] = "Billing portal is not configured yet."
        return RedirectResponse("/premium", status_code=302)
    db_user = db.get(User, user.id)
    base = str(request.base_url).rstrip("/")
    try:
        portal = create_portal_session(db_user, return_url=f"{base}/premium")
    except Exception as exc:
        import logging
        logging.error(f"[Stripe] portal error: {exc}")
        request.session["flash"] = "Could not open billing portal — please try again."
        return RedirectResponse("/premium", status_code=302)
    if not portal:
        request.session["flash"] = "No active subscription found."
        return RedirectResponse("/premium", status_code=302)
    log_event("billing_portal_opened", user_id=user.id, db=db)
    return RedirectResponse(portal.url, status_code=303)


@app.post("/billing/webhook")
async def billing_webhook(request: Request, db: Session = Depends(get_session)):
    import logging
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    try:
        event = construct_webhook_event(payload, sig)
    except Exception as exc:
        logging.warning(f"[Stripe] webhook signature error: {exc}")
        raise HTTPException(400, "Invalid webhook signature")

    etype = event["type"]
    logging.info(f"[Stripe] webhook event: {etype}")

    if etype == "checkout.session.completed":
        obj = event["data"]["object"]
        customer_id = obj.get("customer")
        subscription_id = obj.get("subscription")
        user_id = int((obj.get("metadata") or {}).get("user_id", 0) or 0)
        db_user = db.get(User, user_id) if user_id else None
        if not db_user and customer_id:
            db_user = db.query(User).filter_by(stripe_customer_id=customer_id).first()
        if db_user and subscription_id:
            import stripe as _stripe
            _stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
            sub = _stripe.Subscription.retrieve(subscription_id)
            price_id = sub["items"]["data"][0]["price"]["id"]
            db_user.stripe_customer_id = customer_id
            db_user.stripe_subscription_id = subscription_id
            db_user.subscription_tier = tier_for_price_id(price_id)
            db.commit()
            logging.info(f"[Stripe] user {db_user.id} upgraded to {db_user.subscription_tier}")

    elif etype == "customer.subscription.updated":
        sub = event["data"]["object"]
        customer_id = sub["customer"]
        status = sub["status"]
        price_id = sub["items"]["data"][0]["price"]["id"]
        db_user = db.query(User).filter_by(stripe_customer_id=customer_id).first()
        if db_user:
            if status in ("active", "trialing"):
                db_user.subscription_tier = tier_for_price_id(price_id)
            else:
                db_user.subscription_tier = "free"
            db_user.stripe_subscription_id = sub["id"]
            db.commit()
            log_event("stripe_subscription_changed", user_id=db_user.id, meta={"tier": db_user.subscription_tier, "status": status}, db=db)
            logging.info(f"[Stripe] subscription updated → user {db_user.id}: {db_user.subscription_tier}")

    elif etype == "customer.subscription.deleted":
        sub = event["data"]["object"]
        customer_id = sub["customer"]
        db_user = db.query(User).filter_by(stripe_customer_id=customer_id).first()
        if db_user:
            db_user.subscription_tier = "free"
            db_user.stripe_subscription_id = None
            db.commit()
            log_event("stripe_subscription_changed", user_id=db_user.id, meta={"tier": "free", "status": "cancelled"}, db=db)
            logging.info(f"[Stripe] subscription cancelled → user {db_user.id} downgraded to free")

    return JSONResponse({"received": True})


# ---------------------------------------------------------------------------
# Admin dashboard
# ---------------------------------------------------------------------------

@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request, db: Session = Depends(get_session)):
    from .admin import (
        document_metrics,
        failed_events,
        feature_metrics,
        misc_metrics,
        recent_events,
        user_metrics,
    )
    user = require_user(request)
    require_admin(user)
    return render(
        request,
        "admin.html",
        now=datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        user_stats=user_metrics(db),
        doc_stats=document_metrics(db),
        feature_stats=feature_metrics(db),
        recent=recent_events(db),
        failed=failed_events(db),
        misc=misc_metrics(db),
    )


@app.get("/admin/analytics", response_class=HTMLResponse)
def admin_analytics(
    request: Request,
    range: str = "all",
    event: str = "all",
    db: Session = Depends(get_session),
):
    user = require_user(request)
    require_admin(user)
    from .admin import analytics_metrics, analytics_recent, analytics_by_date_user, ANALYTICS_EVENTS
    days = {"7": 7, "30": 30}.get(range)
    return render(
        request,
        "admin_analytics.html",
        now=datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        metrics=analytics_metrics(db),
        recent=analytics_recent(db, limit=50, days=days, event_filter=event),
        by_date_user=analytics_by_date_user(db, days=days, event_filter=event),
        analytics_events=ANALYTICS_EVENTS,
        selected_range=range,
        selected_event=event,
    )


# ---------------------------------------------------------------------------
# Beta Feedback
# ---------------------------------------------------------------------------

_FEEDBACK_TYPES  = ("Bug", "Confusing", "Missing Feature", "Improvement", "Praise")
_FEATURE_AREAS   = ("Uploads", "Previews", "Expiration Tracking", "Packet Generation",
                    "Premium", "Reminders", "Account", "Other")
_SEVERITIES      = ("Low", "Medium", "High")
_FEEDBACK_STATUS = ("new", "reviewing", "fixed", "closed")

_FEEDBACK_DIR = BASE_DIR / "uploads" / "feedback"
_FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)


@app.post("/feedback")
async def submit_feedback(
    request: Request,
    feedback_type: str = Form(...),
    feature_area: str = Form(...),
    severity: str = Form("Medium"),
    message: str = Form(...),
    page_url: str = Form(""),
    user_agent_field: str = Form(""),
    screen_size: str = Form(""),
    screenshot: Optional[UploadFile] = File(None),
    db: Session = Depends(get_session),
):
    from .db import BetaFeedback
    user = require_user(request)

    if feedback_type not in _FEEDBACK_TYPES:
        feedback_type = "Other"
    if feature_area not in _FEATURE_AREAS:
        feature_area = "Other"
    if severity not in _SEVERITIES:
        severity = "Medium"
    message = (message or "").strip()
    if not message:
        return JSONResponse({"ok": False, "error": "Message is required."}, status_code=400)

    screenshot_filename = None
    if screenshot and screenshot.filename:
        raw = await screenshot.read(5 * 1024 * 1024)
        if raw:
            import secrets as _sec
            ext = Path(screenshot.filename).suffix.lower()
            if ext not in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
                ext = ".png"
            fname = _sec.token_urlsafe(12) + ext
            (_FEEDBACK_DIR / fname).write_bytes(raw)
            screenshot_filename = fname

    fb = BetaFeedback(
        user_id=user.id,
        user_email=user.email,
        feedback_type=feedback_type,
        feature_area=feature_area,
        severity=severity,
        message=message,
        screenshot_filename=screenshot_filename,
        page_url=page_url[:500] if page_url else None,
        user_agent=user_agent_field[:300] if user_agent_field else None,
        screen_size=screen_size[:30] if screen_size else None,
        status="new",
    )
    db.add(fb)
    db.commit()
    log_event("feedback_submitted", user_id=user.id,
              meta={"type": feedback_type, "area": feature_area, "severity": severity}, db=db)
    return JSONResponse({"ok": True})


@app.get("/admin/feedback", response_class=HTMLResponse)
def admin_feedback(
    request: Request,
    ftype: str = "",
    area: str = "",
    severity: str = "",
    status: str = "",
    db: Session = Depends(get_session),
):
    from .db import BetaFeedback
    user = require_user(request)
    require_admin(user)

    q = db.query(BetaFeedback)
    if ftype:
        q = q.filter(BetaFeedback.feedback_type == ftype)
    if area:
        q = q.filter(BetaFeedback.feature_area == area)
    if severity:
        q = q.filter(BetaFeedback.severity == severity)
    if status:
        q = q.filter(BetaFeedback.status == status)
    items = q.order_by(BetaFeedback.created_at.desc()).limit(200).all()

    total  = db.query(BetaFeedback).count()
    new_ct = db.query(BetaFeedback).filter(BetaFeedback.status == "new").count()
    high_ct = db.query(BetaFeedback).filter(BetaFeedback.severity == "High").count()

    return render(
        request,
        "admin_feedback.html",
        now=datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        items=items,
        total=total,
        new_count=new_ct,
        high_count=high_ct,
        feedback_types=_FEEDBACK_TYPES,
        feature_areas=_FEATURE_AREAS,
        severities=_SEVERITIES,
        feedback_statuses=_FEEDBACK_STATUS,
        sel_type=ftype,
        sel_area=area,
        sel_severity=severity,
        sel_status=status,
    )


@app.post("/admin/feedback/{fb_id}/status")
def admin_feedback_status(
    fb_id: int,
    request: Request,
    status: str = Form(...),
    db: Session = Depends(get_session),
):
    from .db import BetaFeedback
    user = require_user(request)
    require_admin(user)
    fb = db.get(BetaFeedback, fb_id)
    if not fb:
        raise HTTPException(404)
    if status in _FEEDBACK_STATUS:
        fb.status = status
        db.commit()
    return RedirectResponse(request.headers.get("referer", "/admin/feedback"), status_code=302)


@app.get("/admin/feedback/{fb_id}/screenshot")
def admin_feedback_screenshot(fb_id: int, request: Request, db: Session = Depends(get_session)):
    from .db import BetaFeedback
    user = require_user(request)
    require_admin(user)
    fb = db.get(BetaFeedback, fb_id)
    if not fb or not fb.screenshot_filename:
        raise HTTPException(404)
    p = _FEEDBACK_DIR / Path(fb.screenshot_filename).name
    if not p.exists():
        raise HTTPException(404)
    mime = "image/png"
    ext = Path(fb.screenshot_filename).suffix.lower()
    if ext in {".jpg", ".jpeg"}:
        mime = "image/jpeg"
    elif ext == ".gif":
        mime = "image/gif"
    elif ext == ".webp":
        mime = "image/webp"
    return Response(content=p.read_bytes(), media_type=mime,
                    headers={"Cache-Control": "private, max-age=3600"})


# ---------------------------------------------------------------------------
# Public informational / trust pages
# ---------------------------------------------------------------------------

@app.get("/privacy", response_class=HTMLResponse)
def page_privacy(request: Request):
    return render(request, "privacy.html")


@app.get("/security-overview", response_class=HTMLResponse)
def page_security_overview(request: Request):
    return render(request, "security_overview.html")


@app.get("/about", response_class=HTMLResponse)
def page_about(request: Request):
    return render(request, "about.html")


@app.get("/document-security", response_class=HTMLResponse)
def page_document_security(request: Request):
    return render(request, "document_security.html")


@app.get("/contact", response_class=HTMLResponse)
def page_contact(request: Request):
    return render(request, "contact.html")


# ---------------------------------------------------------------------------
# Dev-only tier toggle (disabled in ENV=production)
# ---------------------------------------------------------------------------

@app.post("/dev/reminders/test-doc")
def dev_reminders_test_doc(request: Request, db: Session = Depends(get_session)):
    if _is_production:
        raise HTTPException(404)
    user = require_user(request)
    from datetime import date, timedelta
    import uuid
    exp = datetime.utcnow() + timedelta(days=7)
    fake_filename = f"test_reminder_doc_{uuid.uuid4().hex[:8]}.txt"
    doc = Document(
        user_id=user.id,
        category="Licenses & Certifications",
        title="[Test] RN License — Expiry Reminder",
        notes="Auto-created test document for reminder testing. Safe to delete.",
        expires_at=exp,
        stored_filename=fake_filename,
        original_filename="test_rn_license.txt",
        mime_type="text/plain",
        size_bytes=0,
    )
    db.add(doc)
    db.commit()
    return JSONResponse({"ok": True, "doc_id": doc.id, "expires_at": exp.isoformat(), "message": "Test document created — expires in 7 days."})


@app.post("/dev/reminders/trigger")
def dev_reminders_trigger(request: Request, db: Session = Depends(get_session)):
    if _is_production:
        raise HTTPException(404)
    user = require_user(request)
    from datetime import date as _date
    from .services.email_service import send_expiration_email, get_email_status
    from .services.sms_service import get_sms_status
    from .premium import has_premium, has_premium_plus

    lines: list[str] = []

    # -- provider status
    lines.append(f"Email provider: {get_email_status()}")
    lines.append(f"SMS provider:   {get_sms_status()}")

    # -- load settings for this user only
    settings = db.query(ReminderSettings).filter_by(user_id=user.id).first()
    if not settings:
        lines.append("No reminder settings found for your account.")
        return JSONResponse({"ok": False, "log": lines})

    to_email = (settings.reminder_email or "") or user.email
    reminder_days = settings.get_days_list()
    lines.append(f"Email enabled:  {bool(settings.email_enabled)}")
    lines.append(f"Reminder days:  {reminder_days}")
    lines.append(f"Sending to:     {to_email}")
    lines.append(f"Premium:        {has_premium(user)}  Premium+: {has_premium_plus(user)}")

    if not settings.email_enabled:
        lines.append("⚠ Email reminders are disabled — toggle them on and save first.")
        return JSONResponse({"ok": False, "log": lines})

    # -- find matching documents
    today = _date.today()
    docs = db.query(Document).filter_by(user_id=user.id).all()
    lines.append(f"\nChecking {len(docs)} document(s) for your account:")

    matched = 0
    for doc in docs:
        if not doc.expires_at:
            lines.append(f"  • {doc.title} — no expiry date, skipped")
            continue
        days_left = (doc.expires_at.date() - today).days
        lines.append(f"  • {doc.title} — {days_left}d left (threshold match: {days_left in reminder_days})")
        if days_left not in reminder_days:
            continue
        matched += 1
        lines.append(f"    → Sending email to {to_email} ...")
        result = send_expiration_email(user, doc, days_left)
        if result.get("ok"):
            lines.append(f"    ✓ Sent!  Resend message_id={result.get('message_id')}")
        else:
            lines.append(f"    ✗ Failed: {result.get('error')}")

    if matched == 0:
        lines.append(f"\nNo documents are due for a reminder today (need days_left in {reminder_days}).")

    return JSONResponse({"ok": True, "log": lines})


@app.get("/dev/set-tier", response_class=HTMLResponse)
def dev_tier_get(request: Request):
    if os.environ.get("ENV", "").lower() == "production":
        raise HTTPException(404)
    require_user(request)
    return render(request, "dev_tier.html")


@app.post("/dev/set-tier")
def dev_tier_post(
    request: Request,
    tier: str = Form(...),
    db: Session = Depends(get_session),
):
    if os.environ.get("ENV", "").lower() == "production":
        raise HTTPException(404)
    user = require_user(request)
    allowed = ("free", "premium", "premium_plus")
    if tier not in allowed:
        raise HTTPException(400, "Invalid tier.")
    db_user = db.get(User, user.id)
    db_user.subscription_tier = tier
    db.commit()
    request.session["flash"] = f"[Dev] Tier set to '{tier}'."
    return RedirectResponse("/premium", status_code=302)


# ---------------------------------------------------------------------------
# Admin — Testing Dashboard
# ---------------------------------------------------------------------------

@app.get("/admin/testing", response_class=HTMLResponse)
def admin_testing(request: Request, db: Session = Depends(get_session)):
    user = require_user(request)
    require_admin(user)
    from .admin_testing import (
        build_cards,
        get_all_runs,
        get_latest_run,
        get_run_failures,
    )
    run = get_latest_run(db)
    failures = get_run_failures(db, run["id"]) if run else []
    cards = build_cards(run, failures)
    all_runs = get_all_runs(db, limit=10)
    return render(
        request,
        "admin_testing.html",
        now=datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        run=run,
        failures=failures,
        cards=cards,
        all_runs=all_runs,
    )


@app.post("/admin/testing/run")
def admin_testing_run(request: Request, db: Session = Depends(get_session)):
    user = require_user(request)
    require_admin(user)
    from .admin_testing import run_test_suite
    try:
        result = run_test_suite(db)
        return JSONResponse({"ok": True, **result})
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)


@app.get("/admin/testing/export")
def admin_testing_export(request: Request, db: Session = Depends(get_session)):
    user = require_user(request)
    require_admin(user)
    from .admin_testing import (
        generate_report_md,
        get_all_runs,
        get_latest_run,
        get_run_failures,
    )
    run = get_latest_run(db)
    if not run:
        return Response(
            content="# No test runs found\n\nRun the test suite first.",
            media_type="text/markdown",
            headers={"Content-Disposition": 'attachment; filename="TEST_REPORT.md"'},
        )
    failures = get_run_failures(db, run["id"])
    all_runs = get_all_runs(db, limit=10)
    md = generate_report_md(run, failures, all_runs)
    return Response(
        content=md,
        media_type="text/markdown",
        headers={"Content-Disposition": 'attachment; filename="TEST_REPORT.md"'},
    )


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/healthz")
def healthz():
    return {"status": "ok"}
