"""Tests for upload file validation (magic-byte detection, extension blocking, MIME allow-list)."""
import pytest
from fastapi import HTTPException

from app.security import validate_upload, ALLOWED_MIME_TYPES, _BLOCKED_EXTENSIONS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PDF_MAGIC   = b"%PDF-1.4 fake pdf content"
JPEG_MAGIC  = b"\xff\xd8\xff" + b"\x00" * 20
PNG_MAGIC   = b"\x89PNG\r\n" + b"\x00" * 20
GIF87_MAGIC = b"GIF87a" + b"\x00" * 20
GIF89_MAGIC = b"GIF89a" + b"\x00" * 20
TIFF_LE     = b"II*\x00" + b"\x00" * 20
TIFF_BE     = b"MM\x00*" + b"\x00" * 20
WEBP_MAGIC  = b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 10
ZIP_MAGIC   = b"PK\x03\x04" + b"\x00" * 30
OLE_MAGIC   = b"\xd0\xcf\x11\xe0" + b"\x00" * 30
TXT_CONTENT = b"This is a plain text document."


# ---------------------------------------------------------------------------
# Accepted file types
# ---------------------------------------------------------------------------

class TestAcceptedTypes:
    def test_pdf_accepted(self):
        mime = validate_upload(PDF_MAGIC, "license.pdf", "application/pdf")
        assert mime == "application/pdf"

    def test_jpeg_accepted(self):
        mime = validate_upload(JPEG_MAGIC, "photo.jpg", "image/jpeg")
        assert mime == "image/jpeg"

    def test_png_accepted(self):
        mime = validate_upload(PNG_MAGIC, "scan.png", "image/png")
        assert mime == "image/png"

    def test_gif87_accepted(self):
        mime = validate_upload(GIF87_MAGIC, "anim.gif", "image/gif")
        assert mime == "image/gif"

    def test_gif89_accepted(self):
        mime = validate_upload(GIF89_MAGIC, "anim.gif", "image/gif")
        assert mime == "image/gif"

    def test_tiff_little_endian_accepted(self):
        mime = validate_upload(TIFF_LE, "scan.tiff", "image/tiff")
        assert mime == "image/tiff"

    def test_tiff_big_endian_accepted(self):
        mime = validate_upload(TIFF_BE, "scan.tif", "image/tiff")
        assert mime == "image/tiff"

    def test_webp_accepted(self):
        mime = validate_upload(WEBP_MAGIC, "photo.webp", "image/webp")
        assert mime == "image/webp"

    def test_docx_accepted(self):
        docx_mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        mime = validate_upload(ZIP_MAGIC, "resume.docx", docx_mime)
        assert mime == docx_mime

    def test_xlsx_accepted(self):
        xlsx_mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        mime = validate_upload(ZIP_MAGIC, "data.xlsx", xlsx_mime)
        assert mime == xlsx_mime

    def test_doc_ole_accepted(self):
        mime = validate_upload(OLE_MAGIC, "resume.doc", "application/msword")
        assert mime == "application/msword"

    def test_plain_text_accepted(self):
        mime = validate_upload(TXT_CONTENT, "resume.txt", "text/plain")
        assert mime == "text/plain"


# ---------------------------------------------------------------------------
# Blocked extensions
# ---------------------------------------------------------------------------

class TestBlockedExtensions:
    @pytest.mark.parametrize("filename", [
        "evil.exe",
        "malware.dll",
        "script.sh",
        "script.bat",
        "code.js",
        "page.html",
        "page.htm",
        "code.py",
        "hack.php",
    ])
    def test_blocked_extension_raises_400(self, filename):
        with pytest.raises(HTTPException) as exc:
            validate_upload(b"some data", filename, "application/octet-stream")
        assert exc.value.status_code == 400
        assert "not allowed" in exc.value.detail.lower() or "not permitted" in exc.value.detail.lower()

    def test_ts_extension_blocked(self):
        with pytest.raises(HTTPException) as exc:
            validate_upload(b"code", "component.ts", "text/plain")
        assert exc.value.status_code == 400

    def test_svg_extension_blocked(self):
        with pytest.raises(HTTPException) as exc:
            validate_upload(b"<svg/>", "icon.svg", "image/svg+xml")
        assert exc.value.status_code == 400


# ---------------------------------------------------------------------------
# Rejected by MIME (unknown magic, bad content-type)
# ---------------------------------------------------------------------------

class TestRejectedContent:
    def test_empty_file_raises_400(self):
        with pytest.raises(HTTPException) as exc:
            validate_upload(b"", "file.pdf", "application/pdf")
        assert exc.value.status_code == 400
        assert "empty" in exc.value.detail.lower()

    def test_exe_magic_bytes_rejected(self):
        """MZ header (Windows PE executable) should not be in ALLOWED_MIME_TYPES."""
        exe_magic = b"MZ" + b"\x00" * 100
        with pytest.raises(HTTPException) as exc:
            validate_upload(exe_magic, "notapdf.pdf", "application/pdf")
        assert exc.value.status_code == 400

    def test_unknown_binary_with_bad_mime_rejected(self):
        with pytest.raises(HTTPException) as exc:
            validate_upload(b"\x00\x01\x02\x03" * 20, "file.bin", "application/octet-stream")
        assert exc.value.status_code == 400

    def test_text_with_html_extension_blocked(self):
        with pytest.raises(HTTPException) as exc:
            validate_upload(b"<html>hello</html>", "page.html", "text/html")
        assert exc.value.status_code == 400


# ---------------------------------------------------------------------------
# Magic-byte detection overrides claimed MIME
# ---------------------------------------------------------------------------

class TestMagicOverridesClaimed:
    def test_pdf_magic_overrides_wrong_claimed_mime(self):
        """Server should detect PDF by magic bytes even if claimed MIME is wrong."""
        mime = validate_upload(PDF_MAGIC, "license.pdf", "image/jpeg")
        assert mime == "application/pdf"

    def test_jpeg_magic_overrides_wrong_claimed_mime(self):
        mime = validate_upload(JPEG_MAGIC, "photo.jpg", "application/pdf")
        assert mime == "image/jpeg"


# ---------------------------------------------------------------------------
# Allow-list coverage check
# ---------------------------------------------------------------------------

class TestAllowList:
    def test_allowed_mime_set_is_not_empty(self):
        assert len(ALLOWED_MIME_TYPES) > 0

    def test_pdf_in_allowed_set(self):
        assert "application/pdf" in ALLOWED_MIME_TYPES

    def test_html_not_in_allowed_set(self):
        assert "text/html" not in ALLOWED_MIME_TYPES

    def test_javascript_not_in_allowed_set(self):
        assert "application/javascript" not in ALLOWED_MIME_TYPES

    def test_blocked_extensions_set_is_not_empty(self):
        assert len(_BLOCKED_EXTENSIONS) > 0

    def test_exe_in_blocked(self):
        assert ".exe" in _BLOCKED_EXTENSIONS

    def test_js_in_blocked(self):
        assert ".js" in _BLOCKED_EXTENSIONS

    def test_html_in_blocked(self):
        assert ".html" in _BLOCKED_EXTENSIONS
