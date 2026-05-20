"""Simple PDF manifest for recruiter packets (no binary embeds)."""

from __future__ import annotations

from datetime import datetime

from fpdf import FPDF

from .db import Document, User


def _ascii(s: str) -> str:
    return "".join(c if ord(c) < 128 else "?" for c in (s or ""))


def build_manifest_pdf(user: User, documents: list[Document]) -> bytes:
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "Credential packet (manifest)", ln=True)
    pdf.set_font("Helvetica", size=11)
    pdf.ln(4)
    owner = _ascii(user.name or user.email)
    pdf.multi_cell(0, 6, f"Prepared for: {owner}\nEmail: {_ascii(user.email)}")
    pdf.ln(2)
    pdf.set_font("Helvetica", size=10)
    pdf.cell(0, 6, f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}", ln=True)
    pdf.ln(6)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, f"Documents ({len(documents)})", ln=True)
    pdf.set_font("Helvetica", size=10)
    for i, d in enumerate(documents, start=1):
        exp = d.expires_at.strftime("%Y-%m-%d") if d.expires_at else "\u2014"
        iss = d.issued_at.strftime("%Y-%m-%d") if d.issued_at else "\u2014"
        line = _ascii(f"{i}. [{d.category}] {d.title}")
        pdf.multi_cell(0, 5, line)
        pdf.cell(
            0,
            5,
            _ascii(f"    Issued: {iss}   Expires: {exp}   File: {d.original_filename}"),
            ln=True,
        )
        pdf.ln(1)
    pdf.ln(4)
    pdf.set_font("Helvetica", "I", 9)
    pdf.multi_cell(
        0,
        5,
        "This PDF lists filenames and dates only. Download the ZIP packet from Credanta for original files.",
    )
    out = pdf.output(dest="S")
    if isinstance(out, str):
        return out.encode("latin-1")
    return bytes(out)
