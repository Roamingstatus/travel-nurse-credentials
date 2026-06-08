"""Tests for the custom expiration rules engine (app/expiration_rules.py)."""
from datetime import datetime

import pytest

from app.expiration_rules import apply_custom_expiration_rules


def dt(s: str) -> datetime:
    """Parse 'YYYY-MM-DD' → datetime for convenience."""
    return datetime.strptime(s, "%Y-%m-%d")


UPLOAD = dt("2025-01-15")


# ---------------------------------------------------------------------------
# NIH Stroke Scale — positive cases
# ---------------------------------------------------------------------------

class TestNIHRule:
    def test_filename_nihss_with_issue_date(self):
        """NIHSS in filename + issue_date present → expires issue_date + 2yr (default non-CA rule)."""
        expires, label, source = apply_custom_expiration_rules(
            filename="NIHSS_completion_cert.pdf",
            title="NIH Stroke Scale Certificate",
            text=None,
            issue_date=dt("2024-06-10"),
            upload_date=UPLOAD,
            existing_expires=None,
        )
        assert expires == dt("2026-06-10"), f"Expected 2026-06-10, got {expires}"
        assert source == "custom_rule"
        assert label is not None and "NIH" in label

    def test_text_contains_nih_stroke_scale_completion_date(self):
        """Extracted text contains 'NIH Stroke Scale' + completion date → expires + 2yr (non-CA)."""
        text = "Thank you for completing the NIH Stroke Scale training. Completion date: 2024-03-01."
        expires, label, source = apply_custom_expiration_rules(
            filename="certificate.pdf",
            title="Training Certificate",
            text=text,
            issue_date=dt("2024-03-01"),
            upload_date=UPLOAD,
            existing_expires=None,
        )
        assert expires == dt("2026-03-01"), f"Expected 2026-03-01, got {expires}"
        assert source == "custom_rule"
        assert label is not None and "NIH" in label

    def test_no_detected_date_falls_back_to_upload_date(self):
        """No issue_date at all → upload_date used as base date (+ 2yr default)."""
        expires, label, source = apply_custom_expiration_rules(
            filename="nihss_cert.pdf",
            title="NIHSS",
            text=None,
            issue_date=None,
            upload_date=UPLOAD,
            existing_expires=None,
        )
        assert expires == dt("2027-01-15"), f"Expected 2027-01-15, got {expires}"
        assert source == "custom_rule"
        assert label is not None and "NIH" in label

    def test_existing_expiry_not_overridden(self):
        """If an expiry date is already set, the rule must not touch it."""
        already = dt("2027-12-31")
        expires, label, source = apply_custom_expiration_rules(
            filename="NIHSS_cert.pdf",
            title="NIH Stroke Scale",
            text=None,
            issue_date=dt("2024-06-10"),
            upload_date=UPLOAD,
            existing_expires=already,
        )
        assert expires == already
        assert label is None
        assert source is None


# ---------------------------------------------------------------------------
# Unrelated documents — rule must NOT fire
# ---------------------------------------------------------------------------

class TestNoRuleMatch:
    def test_unrelated_document_no_rule_applied(self):
        """A generic document not matching any keyword returns (None, None, None)."""
        expires, label, source = apply_custom_expiration_rules(
            filename="w2_form_2024.pdf",
            title="W-2 Tax Form",
            text="Employee wages and tax withholding statement for 2024.",
            issue_date=None,
            upload_date=UPLOAD,
            existing_expires=None,
        )
        assert expires is None
        assert label is None
        assert source is None

    def test_nih_keyword_not_in_blob_no_match(self):
        """'national' alone in text should not trigger the NIH rule."""
        expires, label, source = apply_custom_expiration_rules(
            filename="national_license.pdf",
            title="National License",
            text="Issued by the national licensing board.",
            issue_date=None,
            upload_date=UPLOAD,
            existing_expires=None,
        )
        assert expires is None
        assert label is None
        assert source is None


# ---------------------------------------------------------------------------
# Keyword variants
# ---------------------------------------------------------------------------

class TestKeywordVariants:
    @pytest.mark.parametrize("kw", [
        "nihss",
        "nih stroke scale",
        "national institutes of health stroke scale",
        "NIH Stroke",
    ])
    def test_keyword_variants_all_match(self, kw):
        """Every keyword variant in the rule should trigger a match."""
        _, _, source = apply_custom_expiration_rules(
            filename=f"{kw}.pdf",
            title=kw,
            text=None,
            issue_date=None,
            upload_date=UPLOAD,
            existing_expires=None,
        )
        assert source == "custom_rule", f"Keyword '{kw}' did not match"
