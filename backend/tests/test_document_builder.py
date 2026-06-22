"""
tests/test_document_builder.py

Tests for template loading, filling, gap detection, and build_initial_document.
Run with: pytest tests/test_document_builder.py -v
"""

import pytest
from datetime import date

from app.models.case import CaseType, LegalContext
from app.core.document_builder import (
    load_template,
    fill_template,
    build_initial_document,
    identify_gaps,
    _build_defaults,
)


# ---------------------------------------------------------------------------
# load_template
# ---------------------------------------------------------------------------


class TestLoadTemplate:
    def test_loads_fir_template(self):
        text = load_template("fir_refusal.txt")
        assert "156(3)" in text
        assert "{complainant_name}" in text

    def test_loads_pmfby_template(self):
        text = load_template("pmfby_grievance.txt")
        assert "PMFBY" in text
        assert "{crop_name}" in text

    def test_loads_sdrf_template(self):
        text = load_template("sdrf_application.txt")
        assert "SDRF" in text

    def test_loads_rti_template(self):
        text = load_template("rti_request.txt")
        assert "Right to Information" in text

    def test_loads_labour_template(self):
        text = load_template("labour_complaint.txt")
        assert "Payment of Wages" in text

    def test_fallback_on_nonexistent_file(self):
        # Should not raise — falls back to rti_request.txt
        text = load_template("nonexistent_template.txt")
        assert len(text) > 50


# ---------------------------------------------------------------------------
# fill_template
# ---------------------------------------------------------------------------


class TestFillTemplate:
    def test_fills_provided_entities(self):
        template = "Hello {complainant_name}, district: {district}."
        result = fill_template(template, {"complainant_name": "Ramesh Kumar", "district": "Patna"})
        assert "Ramesh Kumar" in result
        assert "Patna" in result
        assert "{" not in result  # no unfilled tokens

    def test_uses_defaults_for_missing_fields(self):
        template = "Date: {filing_date}. Name: {complainant_name}."
        result = fill_template(template, {})
        today = date.today()
        assert str(today.year) in result
        assert "[Your Full Name]" in result

    def test_entities_override_defaults(self):
        template = "Name: {complainant_name}."
        result = fill_template(
            template,
            {"complainant_name": "Seema Devi"},
            defaults=_build_defaults(),
        )
        assert "Seema Devi" in result
        assert "[Your Full Name]" not in result

    def test_unfilled_placeholders_marked(self):
        template = "Station: {police_station}. Officer: {officer_name}."
        result = fill_template(template, {})
        # officer_name has no default → marked
        assert "Please Fill" in result

    def test_no_raw_braces_remain(self):
        tpl = load_template("fir_refusal.txt")
        result = fill_template(tpl, {})
        # All {placeholder} tokens must be replaced
        import re
        raw_tokens = re.findall(r"\{[^}]+\}", result)
        assert raw_tokens == [], f"Unfilled raw tokens remain: {raw_tokens}"

    def test_user_name_and_location_in_defaults(self):
        template = "{complainant_name} from {complainant_address}."
        result = fill_template(
            template,
            {},
            defaults=_build_defaults(user_name="Arjun Singh", user_location="Varanasi UP"),
        )
        assert "Arjun Singh" in result
        assert "Varanasi" in result


# ---------------------------------------------------------------------------
# identify_gaps
# ---------------------------------------------------------------------------


class TestIdentifyGaps:
    def test_detects_please_fill_markers(self):
        doc = "Name: [YOUR FULL NAME — Please Fill]. Station: [POLICE STATION — Please Fill]."
        gaps = identify_gaps(doc)
        fields = [g.field for g in gaps]
        assert "your_full_name" in fields or "complainant_name" in fields or len(gaps) >= 2

    def test_no_gaps_when_fully_filled(self):
        doc = "Name: Ramesh Kumar. Date: 01 June 2026. Station: Kotwali."
        gaps = identify_gaps(doc)
        assert gaps == []

    def test_gap_has_description_and_fix(self):
        doc = "Incident: [INCIDENT DATE — Please Fill]."
        gaps = identify_gaps(doc)
        assert len(gaps) == 1
        assert gaps[0].description != ""
        assert gaps[0].how_to_fix != ""

    def test_duplicate_gaps_deduplicated(self):
        doc = "[DISTRICT — Please Fill] and again [DISTRICT — Please Fill]."
        gaps = identify_gaps(doc)
        fields = [g.field for g in gaps]
        assert fields.count("district") == 1

    def test_known_gap_has_specific_description(self):
        doc = "Crop: [CROP NAME — Please Fill]."
        gaps = identify_gaps(doc)
        assert len(gaps) >= 1
        # Should have a meaningful description, not the generic fallback
        assert any("crop" in g.description.lower() for g in gaps)


# ---------------------------------------------------------------------------
# build_initial_document
# ---------------------------------------------------------------------------


class TestBuildInitialDocument:
    def _make_context(self, case_type: CaseType) -> LegalContext:
        from app.core.case_classifier import get_legal_context
        return get_legal_context(case_type, {})

    def test_fir_document_contains_crpc(self):
        ctx = self._make_context(CaseType.FIR_REFUSAL)
        doc = build_initial_document(CaseType.FIR_REFUSAL, {}, ctx)
        assert "156(3)" in doc
        assert "CrPC" in doc

    def test_fir_user_name_injected(self):
        ctx = self._make_context(CaseType.FIR_REFUSAL)
        doc = build_initial_document(
            CaseType.FIR_REFUSAL, {}, ctx, user_name="Priya Sharma"
        )
        assert "Priya Sharma" in doc

    def test_crop_document_contains_pmfby(self):
        ctx = self._make_context(CaseType.CROP_INSURANCE)
        doc = build_initial_document(
            CaseType.CROP_INSURANCE,
            {"crop_name": "Wheat", "district": "Lucknow"},
            ctx,
        )
        assert "PMFBY" in doc
        assert "Wheat" in doc

    def test_sections_appended_to_document(self):
        ctx = self._make_context(CaseType.FIR_REFUSAL)
        doc = build_initial_document(CaseType.FIR_REFUSAL, {}, ctx)
        assert "APPLICABLE LEGAL PROVISIONS" in doc
        assert "CrPC 154" in doc

    def test_labour_document_contains_wages_act(self):
        ctx = self._make_context(CaseType.WAGE_THEFT)
        doc = build_initial_document(CaseType.WAGE_THEFT, {}, ctx)
        assert "Payment of Wages" in doc

    def test_unknown_type_returns_fallback(self):
        ctx = self._make_context(CaseType.UNKNOWN)
        doc = build_initial_document(CaseType.UNKNOWN, {}, ctx)
        assert len(doc) > 50  # something is returned

    def test_gaps_present_when_entities_empty(self):
        ctx = self._make_context(CaseType.FIR_REFUSAL)
        doc = build_initial_document(CaseType.FIR_REFUSAL, {}, ctx)
        gaps = identify_gaps(doc)
        # Must have at least some gaps (police_station, incident details, etc.)
        assert len(gaps) >= 1

    def test_complete_entities_minimize_gaps(self):
        ctx = self._make_context(CaseType.FIR_REFUSAL)
        full_entities = {
            "complainant_name": "Ramesh Kumar",
            "complainant_address": "12 MG Road, Patna, Bihar",
            "complainant_contact": "9876543210",
            "district": "Patna",
            "police_station": "Kotwali",
            "officer_name": "Inspector Sharma",
            "incident_date": "01/06/2026",
            "incident_description": "My neighbour forcibly entered my house and stole property.",
            "complaint_date": "02/06/2026",
        }
        doc = build_initial_document(CaseType.FIR_REFUSAL, full_entities, ctx)
        gaps = identify_gaps(doc)
        # With complete entities, gaps should be zero or minimal
        assert len(gaps) <= 1
