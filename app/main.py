import hashlib
import json
import os
import secrets
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
from sqlalchemy.orm import Session
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
from .categories import CATEGORY_ORDER, CREDENTIAL_CATEGORIES, normalized_effective_category
from .dashboard import days_until, status_for, summarize, ui_status_label
from .db import (
    ChecklistResult,
    Document,
    Event,
    ReminderSettings,
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

AUTO_CATEGORY = "__auto__"

BASE_DIR = Path(__file__).parent

app = FastAPI(title="Credanta")

app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("SESSION_SECRET", secrets.token_urlsafe(32)),
    same_site="lax",
    https_only=False,
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
    init_db()


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


templates.env.filters["dt"] = _format_dt
templates.env.filters["filesize"] = _format_size
templates.env.filters["days_from_now"] = _days_from_now


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
        preset_category=category or "",
        advanced_ai_available=user_has_premium(user) and ai_enabled(),
    )


def _parse_date(value: str) -> Optional[datetime]:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return None


@app.post("/documents/upload")
async def upload_submit(
    request: Request,
    title: str = Form(...),
    category: str = Form(...),
    issued_at: str = Form(""),
    expires_at: str = Form(""),
    notes: str = Form(""),
    file: UploadFile = File(...),
    db: Session = Depends(get_session),
):
    user = require_user(request)
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
        sample = extract_text_sample(raw, file.content_type, fname)
        ai_cat, ai_exp = ai_refine_category_expiry(fname, title_clean, sample, cat or "Other", exp)
        if ai_cat:
            cat = ai_cat
        if ai_exp:
            exp = ai_exp

    # Apply custom expiration rules (e.g. NIHSS → 1 year) when no expiry is set yet.
    doc_text = extract_document_text(raw, file.content_type, fname)
    exp, rule_applied, rule_source = apply_custom_expiration_rules(
        filename=fname,
        title=title_clean,
        text=doc_text,
        issue_date=_parse_date(issued_at),
        upload_date=datetime.utcnow(),
        existing_expires=exp,
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
        mime_type=file.content_type or "application/octet-stream",
        size_bytes=size,
        content_hash=content_hash,
        expiration_rule_applied=rule_applied,
        expiration_source=rule_source,
    )
    db.add(doc)
    db.commit()
    log_event("document_upload", user_id=user.id, meta={"category": doc.category, "mime": doc.mime_type}, db=db)
    request.session["flash"] = f"Saved \"{doc.title}\"."
    return RedirectResponse("/documents", status_code=302)


@app.get("/documents/{doc_id}/thumb")
def document_thumb(doc_id: int, request: Request, db: Session = Depends(get_session)):
    user = require_user(request)
    doc = db.get(Document, doc_id)
    if not doc or doc.user_id != user.id:
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
        raise HTTPException(404)
    return render(request, "edit_document.html", doc=doc, categories=CREDENTIAL_CATEGORIES)


@app.post("/documents/{doc_id}/edit")
def edit_document_submit(
    doc_id: int,
    request: Request,
    title: str = Form(...),
    category: str = Form(...),
    issued_at: str = Form(""),
    expires_at: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_session),
):
    user = require_user(request)
    doc = db.get(Document, doc_id)
    if not doc or doc.user_id != user.id:
        raise HTTPException(404)
    doc.title = title.strip() or doc.title
    doc.category = category if category in CREDENTIAL_CATEGORIES else doc.category
    doc.notes = notes.strip() or None
    doc.issued_at = _parse_date(issued_at)
    doc.expires_at = _parse_date(expires_at)
    db.commit()
    request.session["flash"] = "Document updated."
    return RedirectResponse("/documents", status_code=302)


@app.post("/documents/{doc_id}/delete")
def delete_document(doc_id: int, request: Request, db: Session = Depends(get_session)):
    user = require_user(request)
    doc = db.get(Document, doc_id)
    if not doc or doc.user_id != user.id:
        raise HTTPException(404)
    delete_file(user.id, doc.stored_filename)
    db.delete(doc)
    db.commit()
    request.session["flash"] = f"Deleted {doc.title}."
    return RedirectResponse("/documents", status_code=302)


@app.get("/documents/{doc_id}/view")
def view_document(doc_id: int, request: Request, db: Session = Depends(get_session)):
    user = require_user(request)
    doc = db.get(Document, doc_id)
    if not doc or doc.user_id != user.id:
        raise HTTPException(404)
    p = file_path(user.id, doc.stored_filename)
    if not p.exists():
        raise HTTPException(404, "File missing.")
    return Response(
        content=p.read_bytes(),
        media_type=doc.mime_type or "application/octet-stream",
        headers={"Content-Disposition": f'inline; filename="{doc.original_filename}"'},
    )


@app.get("/documents/{doc_id}/download")
def download_document(doc_id: int, request: Request, db: Session = Depends(get_session)):
    user = require_user(request)
    doc = db.get(Document, doc_id)
    if not doc or doc.user_id != user.id:
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
    require_premium(user)
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
    require_premium_plus(user)
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


@app.get("/s/{token}", response_class=HTMLResponse)
def share_view(token: str, request: Request, db: Session = Depends(get_session)):
    link, owner = _resolve_share(token, db)
    docs = db.query(Document).filter_by(user_id=owner.id).order_by(Document.category.asc(), Document.title.asc()).all()
    summary = summarize(docs)
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
    )


@app.get("/s/{token}/download/{doc_id}")
def share_download(token: str, doc_id: int, db: Session = Depends(get_session)):
    link, owner = _resolve_share(token, db)
    doc = db.get(Document, doc_id)
    if not doc or doc.user_id != owner.id:
        raise HTTPException(404)
    p = file_path(owner.id, doc.stored_filename)
    if not p.exists():
        raise HTTPException(404)
    return Response(
        content=p.read_bytes(),
        media_type=doc.mime_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{doc.original_filename}"'},
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
    require_user(request)
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
    return render(request, "premium_reminders.html", settings=settings)


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
    settings.sms_enabled = 1 if sms_enabled in ("1", "on", "true") else 0
    settings.reminder_email = reminder_email.strip() or user.email
    settings.phone_number = phone_number.strip() or None
    settings.reminder_days = reminder_days.strip() or "30,14,7,0"
    db.commit()
    import logging
    if settings.sms_enabled and not os.environ.get("TWILIO_ACCOUNT_SID"):
        logging.info("[Reminders] SMS reminder provider not configured — skipping SMS setup.")
    request.session["flash"] = "Reminder settings saved."
    return RedirectResponse("/premium/reminders/settings", status_code=302)


@app.get("/premium/calendar/export")
def premium_calendar_export(request: Request, db: Session = Depends(get_session)):
    user = require_user(request)
    require_premium(user)
    docs = db.query(Document).filter_by(user_id=user.id).all()
    body = build_expiring_ics(docs, calendar_name="Credanta — Expiring Credentials")
    log_event("calendar_export", user_id=user.id, meta={"doc_count": len(docs)}, db=db)
    return Response(
        content=body,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="credential-expirations.ics"'},
    )


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


@app.get("/premium/resume/enhance", response_class=HTMLResponse)
def resume_enhance_get(request: Request):
    user = require_user(request)
    require_premium(user)
    return render(request, "premium_resume.html", suggestions=None, filename=None)


@app.post("/premium/resume/enhance", response_class=HTMLResponse)
async def resume_enhance_post(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_session),
):
    user = require_user(request)
    require_premium(user)
    raw = await file.read()
    if not raw:
        request.session["flash"] = "Please choose a resume file to upload."
        return RedirectResponse("/premium/resume/enhance", status_code=302)
    if len(raw) > 10 * 1024 * 1024:
        request.session["flash"] = "Resume file must be 10 MB or smaller."
        return RedirectResponse("/premium/resume/enhance", status_code=302)

    from .resume_enhancer import enhance_resume
    suggestions = enhance_resume(raw, file.content_type or "", file.filename or "resume")
    log_event("resume_enhance", user_id=user.id, meta={"filename": file.filename}, db=db)
    return render(
        request,
        "premium_resume.html",
        suggestions=suggestions,
        filename=file.filename,
    )


# ---------------------------------------------------------------------------
# Premium+ routes
# ---------------------------------------------------------------------------

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
    require_premium_plus(user)
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
# Billing (Stripe)
# ---------------------------------------------------------------------------

@app.post("/billing/checkout")
async def billing_checkout(
    request: Request,
    price_id: str = Form(...),
    db: Session = Depends(get_session),
):
    user = require_user(request)
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


# ---------------------------------------------------------------------------
# Dev-only tier toggle (disabled in ENV=production)
# ---------------------------------------------------------------------------

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
# Health check
# ---------------------------------------------------------------------------

@app.get("/healthz")
def healthz():
    return {"status": "ok"}
