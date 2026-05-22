"""Tests for category inference and metadata extraction."""
import pytest

from app.smart_categorize import (
    _clean_filename_as_title,
    _extract_dates_from_text,
    extract_document_metadata,
    infer_category,
    infer_expiry_from_text,
)


class TestInferCategory:
    # --- Identity ---
    def test_passport(self):
        assert infer_category("passport.pdf", "") == "Identity"

    def test_drivers_license(self):
        assert infer_category("drivers_license.jpg", "") == "Identity"

    def test_state_id(self):
        assert infer_category("state id card.pdf", "") == "Identity"

    def test_birth_certificate(self):
        assert infer_category("birth certificate.pdf", "") == "Identity"

    # --- Licenses & Certifications ---
    def test_rn_license(self):
        assert infer_category("rn_license.pdf", "Registered Nurse License") == "Licenses & Certifications"

    def test_bls_certification(self):
        assert infer_category("bls_card.pdf", "BLS Certification") == "Licenses & Certifications"

    def test_cpr_card(self):
        assert infer_category("cpr_card.pdf", "") == "Licenses & Certifications"

    def test_acls_cert(self):
        assert infer_category("acls.pdf", "") == "Licenses & Certifications"

    def test_aws_cert(self):
        assert infer_category("aws_cert.pdf", "AWS Certification") == "Licenses & Certifications"

    # --- Health & Compliance ---
    def test_vaccine_record(self):
        assert infer_category("vaccination_record.pdf", "") == "Health & Compliance"

    def test_tb_test(self):
        assert infer_category("tb test result.pdf", "") == "Health & Compliance"

    def test_drug_screen(self):
        assert infer_category("drug screen result.pdf", "") == "Health & Compliance"

    def test_hipaa_training(self):
        assert infer_category("hipaa_training.pdf", "") == "Health & Compliance"

    def test_background_check(self):
        assert infer_category("background check.pdf", "") == "Health & Compliance"

    # --- Education ---
    def test_diploma(self):
        assert infer_category("diploma.pdf", "") == "Education"

    def test_transcript(self):
        assert infer_category("university_transcript.pdf", "") == "Education"

    def test_degree_certificate(self):
        # Title must not contain "certificate" to avoid matching Licenses & Certifications first
        assert infer_category("bsn_degree.pdf", "BSN Degree Program Completion") == "Education"

    # --- Other ---
    def test_unknown_falls_to_other(self):
        assert infer_category("random_document.pdf", "Random stuff") == "Other"

    def test_empty_strings(self):
        assert infer_category("", "") == "Other"

    # --- Case insensitivity ---
    def test_case_insensitive(self):
        assert infer_category("PASSPORT.PDF", "") == "Identity"
        assert infer_category("BLS_CARD.PDF", "") == "Licenses & Certifications"

    # --- Title takes precedence when filename is generic ---
    def test_title_match(self):
        assert infer_category("document.pdf", "Nursing License Renewal") == "Licenses & Certifications"


class TestInferExpiryFromText:
    def test_iso_date_in_filename(self):
        result = infer_expiry_from_text("license_2026-03-15.pdf", "")
        assert result is not None
        assert result.year == 2026
        assert result.month == 3
        assert result.day == 15

    def test_iso_date_in_title(self):
        result = infer_expiry_from_text("", "RN License exp 2027-12-01")
        assert result is not None
        assert result.year == 2027

    def test_no_date_returns_none(self):
        result = infer_expiry_from_text("rn_license.pdf", "RN License")
        assert result is None

    def test_slash_separator(self):
        result = infer_expiry_from_text("license_2025/06/30.pdf", "")
        assert result is not None
        assert result.year == 2025


class TestExtractDatesFromText:
    def test_iso_format_date(self):
        issued, expires = _extract_dates_from_text(
            "Issued: 2023-01-15\nExpires: 2025-01-15"
        )
        assert issued is not None
        assert expires is not None

    def test_expiry_context_detected(self):
        text = "This license is valid until 2026-06-30."
        _, expires = _extract_dates_from_text(text)
        assert expires is not None
        assert expires.year == 2026

    def test_issue_context_detected(self):
        text = "Date Issued: 2023-03-01. Expiration: 2026-03-01."
        issued, expires = _extract_dates_from_text(text)
        assert issued is not None
        assert expires is not None

    def test_no_dates_returns_none_none(self):
        issued, expires = _extract_dates_from_text("No dates here at all.")
        assert issued is None
        assert expires is None

    def test_month_name_format(self):
        _, expires = _extract_dates_from_text("Expires January 15, 2027")
        assert expires is not None
        assert expires.year == 2027
        assert expires.month == 1


class TestCleanFilenameAsTitle:
    def test_underscores_replaced_with_spaces(self):
        assert "rn license" in _clean_filename_as_title("rn_license.pdf").lower()

    def test_dashes_replaced(self):
        assert "rn license" in _clean_filename_as_title("rn-license.pdf").lower()

    def test_leading_digits_stripped(self):
        result = _clean_filename_as_title("001_rn_license.pdf")
        assert not result[0].isdigit()

    def test_title_case_applied(self):
        result = _clean_filename_as_title("rn_license.pdf")
        assert result[0].isupper()

    def test_empty_string(self):
        result = _clean_filename_as_title("")
        assert result == ""


class TestExtractDocumentMetadata:
    def test_plain_text_with_expiry(self):
        content = b"Nurse License\nExpires: 2027-06-30\nIssued: 2022-06-30"
        result = extract_document_metadata(content, "text/plain", "license.txt")
        assert result["expires_at"] is not None
        assert "2027" in result["expires_at"]

    def test_filename_used_for_category(self):
        result = extract_document_metadata(b"", "application/octet-stream", "passport_scan.jpg")
        assert result["category"] == "Identity"

    def test_returns_dict_with_expected_keys(self):
        result = extract_document_metadata(b"hello", "text/plain", "doc.txt")
        assert set(result.keys()) == {"title", "category", "issued_at", "expires_at"}

    def test_title_derived_from_filename(self):
        result = extract_document_metadata(b"", "application/octet-stream", "rn_license_2025.pdf")
        assert result["title"] is not None
        assert len(result["title"]) > 0

    def test_category_none_for_unknown(self):
        result = extract_document_metadata(b"gibberish content", "text/plain", "xyzxyz.txt")
        assert result["category"] is None

    def test_date_format_is_iso(self):
        content = b"Expires: 2028-12-31"
        result = extract_document_metadata(content, "text/plain", "doc.txt")
        if result["expires_at"]:
            parts = result["expires_at"].split("-")
            assert len(parts) == 3
            assert len(parts[0]) == 4
