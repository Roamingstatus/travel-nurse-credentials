import hashlib
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
from .categories import CATEGORY_ORDER, CREDENTIAL_CATEGORIES, normalized_effective_category
from .dashboard import days_until, status_for, summarize, ui_status_label
from .db import (
    Document,
    ShareLink,
    User,
    get_session,
    init_db,
)
from .packet import build_zip
from .packet_pdf import build_manifest_pdf
from .premium import PREMIUM_FEATURES, user_has_premium
from .reminders import build_expiring_ics
from .smart_categorize import extract_document_metadata, infer_category, infer_expiry_from_text
from .storage import delete_file, file_path, save_upload

AUTO_CATEGORY = "__auto__"

BASE_DIR = Path(__file__).parent

app = FastAPI(title="skillDock")

app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("SESSION_SECRET", secrets.token_urlsafe(32)),
    same_site="lax",
    https_only=False,
)

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


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


templates.env.filters["dt"] = _format_dt
templates.env.filters["filesize"] = _format_size


def render(request: Request, template: str, **ctx) -> HTMLResponse:
    ctx.setdefault("user", current_user(request))
    ctx.setdefault("flash", request.session.pop("flash", None))
    u = ctx.get("user")
    is_premium = user_has_premium(u)
    ctx.setdefault("is_premium", is_premium)
    ctx.setdefault("premium_features", PREMIUM_FEATURES)
    if u is not None:
        ctx.setdefault("ai_features_enabled", is_premium and ai_enabled())
    else:
        ctx.setdefault("ai_features_enabled", False)
    return templates.TemplateResponse(request, template, ctx)


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
        redirect_uri = "https://" + redirect_uri[len("http://") :]
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
        )
        db.add(user)
    else:
        user.email = email
        user.name = info.get("name") or user.name
        user.picture = info.get("picture") or user.picture
    db.commit()
    request.session["user_id"] = user.id
    request.session["flash"] = f"Signed in as {user.email}"
    return RedirectResponse("/dashboard", status_code=302)


@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)


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
    )
    db.add(doc)
    db.commit()
    request.session["flash"] = f"Saved “{doc.title}”."
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


@app.get("/packet")
def packet(request: Request, db: Session = Depends(get_session)):
    user = require_user(request)
    docs = db.query(Document).filter_by(user_id=user.id).all()
    if not docs:
        request.session["flash"] = "Upload at least one document before building a packet."
        return RedirectResponse("/dashboard", status_code=302)
    blob = build_zip(user, docs)
    fname = f"credentials-packet-{datetime.utcnow().strftime('%Y%m%d')}.zip"
    return Response(
        content=blob,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@app.get("/packet/pdf")
def packet_pdf(request: Request, db: Session = Depends(get_session)):
    user = require_user(request)
    docs = db.query(Document).filter_by(user_id=user.id).order_by(Document.category.asc(), Document.title.asc()).all()
    if not docs:
        request.session["flash"] = "Upload at least one document before building a packet."
        return RedirectResponse("/dashboard", status_code=302)
    blob = build_manifest_pdf(user, docs)
    fname = f"credentials-manifest-{datetime.utcnow().strftime('%Y%m%d')}.pdf"
    return Response(
        content=blob,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@app.get("/calendar/expiring.ics")
def calendar_expiring_ics(request: Request, db: Session = Depends(get_session)):
    user = require_user(request)
    docs = db.query(Document).filter_by(user_id=user.id).all()
    body = build_expiring_ics(docs, calendar_name="Expiring credentials")
    return Response(
        content=body,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="credential-expirations.ics"'},
    )


@app.get("/share", response_class=HTMLResponse)
def share_index(request: Request, db: Session = Depends(get_session)):
    user = require_user(request)
    links = (
        db.query(ShareLink)
        .filter_by(user_id=user.id)
        .order_by(ShareLink.created_at.desc())
        .all()
    )
    base = str(request.base_url).rstrip("/")
    return render(request, "share.html", links=links, base_url=base)


@app.get("/premium", response_class=HTMLResponse)
def premium_page(request: Request):
    require_user(request)
    return render(request, "premium.html")


@app.post("/share/create")
def share_create(
    request: Request,
    label: str = Form(""),
    expires_days: str = Form(""),
    db: Session = Depends(get_session),
):
    user = require_user(request)
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
    request.session["flash"] = "Share link created."
    return RedirectResponse("/share", status_code=302)


@app.post("/share/{link_id}/revoke")
def share_revoke(link_id: int, request: Request, db: Session = Depends(get_session)):
    user = require_user(request)
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


@app.get("/healthz")
def healthz():
    return {"ok": True}
