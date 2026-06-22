"""
tests/test_classifier.py

Deterministic tests for the case classifier.
Run with: pytest tests/test_classifier.py -v
"""

import pytest
from app.models.case import CaseType
from app.core.case_classifier import (
    classify_case,
    extract_entities,
    get_legal_context,
    normalize_hinglish,
    load_case_db,
)


# ---------------------------------------------------------------------------
# classify_case — language coverage
# ---------------------------------------------------------------------------


class TestClassifyCase:
    def test_hindi_fir_refusal(self):
        text = "पुलिस ने मेरी FIR दर्ज नहीं की। थाने में शिकायत दी थी।"
        case_type, confidence = classify_case(text)
        assert case_type == CaseType.FIR_REFUSAL
        assert confidence > 0.4

    def test_english_fir_refusal(self):
        text = "The police officer at the station refused to register my FIR complaint."
        case_type, confidence = classify_case(text)
        assert case_type == CaseType.FIR_REFUSAL
        assert confidence > 0.4

    def test_hinglish_fir_refusal(self):
        text = "police ne meri FIR nahi ki. Station pe gaya tha complaint karne."
        case_type, confidence = classify_case(text)
        assert case_type == CaseType.FIR_REFUSAL
        assert confidence > 0.3

    def test_hinglish_crop_insurance(self):
        text = "mera pmfby fasal bima claim reject ho gaya bina kisi reason ke"
        case_type, confidence = classify_case(text)
        assert case_type == CaseType.CROP_INSURANCE
        assert confidence > 0.4

    def test_hindi_crop_insurance(self):
        text = "फसल बीमा का दावा अस्वीकार हो गया है। पीएमएफबीवाई के तहत मुआवजा नहीं मिला।"
        case_type, confidence = classify_case(text)
        assert case_type == CaseType.CROP_INSURANCE
        assert confidence > 0.4

    def test_flood_relief_english(self):
        text = "My house was damaged in the flood. I need SDRF disaster relief compensation."
        case_type, confidence = classify_case(text)
        assert case_type == CaseType.FLOOD_RELIEF
        assert confidence > 0.4

    def test_flood_relief_hindi(self):
        text = "बाढ़ में मेरा घर तबाह हो गया। एसडीआरएफ से मुआवजा नहीं मिला।"
        case_type, confidence = classify_case(text)
        assert case_type == CaseType.FLOOD_RELIEF
        assert confidence > 0.4

    def test_wage_theft_hinglish(self):
        text = "malik ne 3 mahine ki tankhwah nahi di. Rs 45000 ka paisa nahi mila."
        case_type, confidence = classify_case(text)
        assert case_type == CaseType.WAGE_THEFT
        assert confidence > 0.3

    def test_rti_request(self):
        text = "I want to apply for RTI to get information about the government scheme."
        case_type, confidence = classify_case(text)
        assert case_type == CaseType.RTI_REQUEST
        assert confidence > 0.3

    def test_consumer_complaint(self):
        text = "The product I purchased is defective. The company is refusing refund."
        case_type, confidence = classify_case(text)
        assert case_type == CaseType.CONSUMER_COMPLAINT
        assert confidence > 0.3

    def test_unknown_text_low_confidence(self):
        text = "The weather is nice today and I had a good breakfast."
        case_type, confidence = classify_case(text)
        assert case_type == CaseType.UNKNOWN
        assert confidence == 0.0

    def test_unknown_random_short(self):
        case_type, confidence = classify_case("hello world this is a test")
        assert case_type == CaseType.UNKNOWN
        assert confidence < 0.3

    def test_confidence_capped_at_one(self):
        # Very keyword-rich text should not exceed 1.0
        text = (
            "police station fir refused officer complaint register "
            "एफआईआर पुलिस दर्ज थाना शिकायत"
        )
        _, confidence = classify_case(text)
        assert confidence <= 1.0


# ---------------------------------------------------------------------------
# normalize_hinglish
# ---------------------------------------------------------------------------


class TestNormalizeHinglish:
    def test_hinglish_phrase_substitution(self):
        result = normalize_hinglish("police ne nahi ki FIR")
        assert "police refused" in result or "fir" in result

    def test_lowercase(self):
        result = normalize_hinglish("POLICE NE FIR")
        assert result == result.lower()

    def test_whitespace_collapse(self):
        result = normalize_hinglish("   too   many   spaces   ")
        assert "  " not in result

    def test_devanagari_preserved(self):
        text = "पुलिस ने FIR नहीं की"
        result = normalize_hinglish(text)
        assert "पुलिस" in result or "police" in result


# ---------------------------------------------------------------------------
# extract_entities
# ---------------------------------------------------------------------------


class TestExtractEntities:
    def test_fir_station_name(self):
        text = "I went to Kotwali Police Station to file an FIR."
        entities = extract_entities(text, CaseType.FIR_REFUSAL)
        assert "station_name" in entities
        assert "kotwali" in entities["station_name"].lower()

    def test_fir_date_extraction(self):
        text = "The incident happened on 12/03/2024 and police refused."
        entities = extract_entities(text, CaseType.FIR_REFUSAL)
        assert entities.get("incident_date") != ""
        assert "12" in entities["incident_date"] or "03" in entities["incident_date"]

    def test_crop_insurance_crop_name(self):
        text = "My wheat crop was destroyed by floods. PMFBY claim rejected."
        entities = extract_entities(text, CaseType.CROP_INSURANCE)
        assert "wheat" in entities.get("crop_name", "").lower()

    def test_flood_village_name(self):
        text = "I am from village Rampur in the district. My house was damaged."
        entities = extract_entities(text, CaseType.FLOOD_RELIEF)
        assert "rampur" in entities.get("village_name", "").lower()

    def test_wage_amount_extraction(self):
        text = "My employer owes me Rs. 25,000 for three months of work."
        entities = extract_entities(text, CaseType.WAGE_THEFT)
        assert entities.get("amount_owed") != ""
        assert "25" in entities["amount_owed"]

    def test_unknown_returns_date_only(self):
        text = "Something happened on 01/01/2024."
        entities = extract_entities(text, CaseType.UNKNOWN)
        assert "date" in entities


# ---------------------------------------------------------------------------
# get_legal_context
# ---------------------------------------------------------------------------


class TestGetLegalContext:
    def test_fir_context_has_sections(self):
        ctx = get_legal_context(CaseType.FIR_REFUSAL, {})
        assert "CrPC 154" in ctx.applicable_sections
        assert "CrPC 156(3)" in ctx.applicable_sections
        assert ctx.authority_to_file != ""
        assert ctx.filing_url != ""

    def test_crop_insurance_has_pmfby(self):
        ctx = get_legal_context(CaseType.CROP_INSURANCE, {})
        assert ctx.scheme_name == "PMFBY"
        assert len(ctx.required_documents) > 0

    def test_unknown_returns_fallback(self):
        ctx = get_legal_context(CaseType.UNKNOWN, {})
        assert ctx.authority_to_file != ""
        assert len(ctx.applicable_sections) > 0

    def test_all_case_types_have_authority(self):
        """Every defined case type must resolve to a non-empty authority."""
        db = load_case_db()
        for key in db:
            ctx = get_legal_context(CaseType(key), {})
            assert ctx.authority_to_file, f"No authority for {key}"

    def test_all_case_types_have_sections(self):
        db = load_case_db()
        for key in db:
            ctx = get_legal_context(CaseType(key), {})
            assert len(ctx.applicable_sections) > 0, f"No sections for {key}"
