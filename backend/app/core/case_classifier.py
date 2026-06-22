"""
app/core/case_classifier.py

100% deterministic case classification — zero LLM cost.
Handles English, Hindi (Devanagari), and Hinglish input.
"""

from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from app.models.case import CaseType, LegalContext


# ---------------------------------------------------------------------------
# DB loader — cached on first call
# ---------------------------------------------------------------------------

_DB_PATH = Path(__file__).parent.parent.parent / "data" / "case_types.json"


@lru_cache(maxsize=1)
def load_case_db() -> dict:
    """Load and cache data/case_types.json. Called once per process lifetime."""
    with _DB_PATH.open(encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Hinglish normalisation map
# Extends known romanised Hindi words → English equivalents so the English
# keyword list can match them.
# ---------------------------------------------------------------------------

_HINGLISH_MAP: dict[str, str] = {
    # Common romanised Hindi words
    "kiraya": "rent",
    "makaan": "house",
    "ghar": "house",
    "paisa": "money",
    "paise": "money",
    "khet": "crop",
    "kisan": "farmer",
    "baadh": "flood",
    "baarish": "rain",
    "naukri": "job",
    "kaam": "work",
    "malik": "employer",
    "dukaan": "shop",
    "zameen": "land",
    "jameen": "land",
    # Hinglish phrases (longer first so they match before substrings)
    "police ne nahi ki": "police refused",
    "police ne nahi": "police refused",
    "fir nahi ki": "fir not filed",
    "fir nahi": "fir not filed",
    "nahi diya": "not paid",
    "nahi mila": "not received",
    "nahi hua": "not done",
    "reject ho gaya": "rejected",
    "reject kar diya": "rejected",
    "tankhwah nahi": "salary unpaid",
    "tankhwah nahi mili": "salary unpaid",
    "police ne": "police",
    "fasal bima": "crop insurance",
    "bima claim": "insurance claim",
}


def normalize_hinglish(text: str) -> str:
    """
    Normalise text for keyword matching:
    1. Lowercase
    2. Replace Hinglish phrases/words with English equivalents
       (Devanagari characters are kept intact for Hindi keyword matching)
    3. Collapse extra whitespace
    """
    lowered = text.lower().strip()

    # Apply longest-match Hinglish substitutions first
    sorted_keys = sorted(_HINGLISH_MAP.keys(), key=len, reverse=True)
    for phrase in sorted_keys:
        lowered = lowered.replace(phrase, _HINGLISH_MAP[phrase])

    # Collapse multiple spaces / newlines
    lowered = re.sub(r"\s+", " ", lowered).strip()
    return lowered


# ---------------------------------------------------------------------------
# Core classifier
# ---------------------------------------------------------------------------

_PHRASE_SCORE = 3  # exact multi-word phrase match
_KEYWORD_SCORE = 1  # single keyword match


def classify_case(text: str) -> tuple[CaseType, float]:
    """
    Classify text into a CaseType using keyword scoring.

    Returns (CaseType, confidence 0.0–1.0).
    confidence = min(1.0, best_score / 5.0)
    """
    db = load_case_db()
    normalised = normalize_hinglish(text)

    best_type = CaseType.UNKNOWN
    best_score = 0

    for case_key, meta in db.items():
        score = 0
        keywords_en: list[str] = meta.get("keywords_en", [])
        keywords_hi: list[str] = meta.get("keywords_hi", [])

        # Score English keywords (on normalised text)
        for kw in keywords_en:
            if " " in kw:
                # Multi-word phrase
                if kw in normalised:
                    score += _PHRASE_SCORE
            else:
                if re.search(r"\b" + re.escape(kw) + r"\b", normalised):
                    score += _KEYWORD_SCORE

        # Score Hindi keywords (on original lowercased text — keep Devanagari)
        original_lower = text.lower()
        for kw in keywords_hi:
            if kw in original_lower:
                # Devanagari phrases don't have word-boundary anchors in regex
                score += _PHRASE_SCORE if " " in kw else _KEYWORD_SCORE

        if score > best_score:
            best_score = score
            best_type = CaseType(case_key)

    if best_score == 0:
        return CaseType.UNKNOWN, 0.0

    confidence = min(1.0, best_score / 5.0)
    return best_type, confidence


# ---------------------------------------------------------------------------
# Entity extractor — regex, per case type
# ---------------------------------------------------------------------------

# Date patterns common to all case types
_DATE_PATTERNS = [
    r"\b(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{2,4})\b",  # DD/MM/YYYY or DD-MM-YYYY
    r"\b(\d{1,2})\s+(january|february|march|april|may|june|july|august|"
    r"september|october|november|december)\s+(\d{4})\b",
    r"\b(aaj|kal|parso)\b",  # Hindi relative dates
]

_MONTHS_HI = {
    "जनवरी": "January", "फरवरी": "February", "मार्च": "March",
    "अप्रैल": "April", "मई": "May", "जून": "June",
    "जुलाई": "July", "अगस्त": "August", "सितंबर": "September",
    "अक्टूबर": "October", "नवंबर": "November", "दिसंबर": "December",
}

# Amount pattern (₹ or Rs)
_AMOUNT_PATTERN = r"(?:rs\.?\s*|₹\s*)(\d[\d,]*)"


def _extract_date(text: str) -> str:
    """Try all date patterns and return the first match, or ''."""
    lower = text.lower()
    for pattern in _DATE_PATTERNS:
        m = re.search(pattern, lower)
        if m:
            return m.group(0)
    # Hindi month names
    for hi_month, en_month in _MONTHS_HI.items():
        if hi_month in text:
            m = re.search(r"(\d{1,2})\s*" + hi_month + r"\s*(\d{4})", text)
            if m:
                return m.group(0)
    return ""


def extract_entities(text: str, case_type: CaseType) -> dict[str, str]:
    """
    Regex-based entity extraction per case type.
    Returns a dict of found entities; empty string for not-found fields.
    All patterns are best-effort — never raises.
    """
    lower = text.lower()
    entities: dict[str, str] = {}

    # Universal — date
    entities["date"] = _extract_date(text)

    if case_type == CaseType.FIR_REFUSAL:
        # Station name: "X police station" or "thana X"
        m = re.search(r"(\w[\w\s]{1,30})\s+(?:police\s+)?(?:station|thana)", lower)
        entities["station_name"] = m.group(1).strip().title() if m else ""

        # Officer: "officer X" / "SHO X" / "inspector X"
        m = re.search(r"(?:officer|sho|inspector|constable)\s+([a-z][a-z\s]{1,25})", lower)
        entities["officer_name"] = m.group(1).strip().title() if m else ""

        entities["incident_date"] = entities.pop("date", "")

    elif case_type == CaseType.CROP_INSURANCE:
        # Crop name
        crops = ["wheat", "rice", "paddy", "cotton", "soybean", "maize",
                 "gehu", "dhan", "kapas", "गेहूं", "धान", "कपास", "मक्का"]
        found_crop = next((c for c in crops if c in lower or c in text), "")
        entities["crop_name"] = found_crop.title() if found_crop else ""

        # Insurance company
        companies = ["lIC", "reliance", "bajaj", "hdfc", "new india", "oriental",
                     "united india", "agriculture insurance"]
        found_co = next((c for c in companies if c in lower), "")
        entities["insurance_company"] = found_co.title() if found_co else ""

        # District — word before "district" or "jila"
        m = re.search(r"(\w[\w\s]{1,20})\s+(?:district|jila|जिला)", lower)
        entities["district"] = m.group(1).strip().title() if m else ""

    elif case_type == CaseType.FLOOD_RELIEF:
        # Village name: "village X" / "gaon X" / "gram X"
        m = re.search(r"(?:village|gaon|gram|गांव|गाँव)\s+([a-zA-Z\u0900-\u097F][\w\s]{1,25})", text, re.IGNORECASE)
        entities["village_name"] = m.group(1).strip() if m else ""

        # Damage type
        damage_types = ["house", "ghar", "crop", "fasal", "livestock", "pashu", "road"]
        found_damage = next((d for d in damage_types if d in lower or d in text), "")
        entities["damage_type"] = found_damage if found_damage else ""

        # District
        m = re.search(r"(\w[\w\s]{1,20})\s+(?:district|jila|जिला)", lower)
        entities["district"] = m.group(1).strip().title() if m else ""

    elif case_type == CaseType.WAGE_THEFT:
        # Employer name: "X company" / "X pvt" / "malik X"
        m = re.search(r"([a-zA-Z][\w\s]{1,30})\s+(?:company|pvt|ltd|enterprises|malik)", lower)
        entities["employer_name"] = m.group(1).strip().title() if m else ""

        # Amount owed
        m = re.search(_AMOUNT_PATTERN, lower)
        entities["amount_owed"] = m.group(0).strip() if m else ""

        entities["last_payment_date"] = entities.pop("date", "")

    elif case_type in (CaseType.LABOUR_COMPLAINT,):
        m = re.search(_AMOUNT_PATTERN, lower)
        entities["amount_claimed"] = m.group(0).strip() if m else ""

    # Keep generic date for remaining types
    if "date" in entities and case_type not in (
        CaseType.FIR_REFUSAL, CaseType.WAGE_THEFT
    ):
        pass  # keep as-is

    return entities


# ---------------------------------------------------------------------------
# LegalContext builder — zero LLM
# ---------------------------------------------------------------------------


def get_legal_context(case_type: CaseType, entities: dict[str, str]) -> LegalContext:
    """
    Build LegalContext purely from case_types.json + extracted entities.
    Zero LLM. Falls back gracefully if case_type is UNKNOWN.
    """
    db = load_case_db()

    if case_type == CaseType.UNKNOWN or case_type.value not in db:
        return LegalContext(
            case_type=case_type,
            applicable_sections=["Seek general legal advice"],
            relevant_precedents=[],
            authority_to_file="District Legal Services Authority (DLSA)",
            filing_url="https://nalsa.gov.in",
            scheme_name="",
            required_documents=["Aadhaar / identity proof", "Written description of grievance"],
        )

    meta = db[case_type.value]
    return LegalContext(
        case_type=case_type,
        applicable_sections=meta["applicable_sections"],
        relevant_precedents=[],  # filled later by ResearchAgent (IndianKanoon)
        authority_to_file=meta["authority"],
        filing_url=meta.get("filing_portal", ""),
        scheme_name=meta.get("scheme_name", ""),
        required_documents=meta["required_documents"],
    )



# ---------------------------------------------------------------------------
# LLM-based Classifier (Prompt 3 Implementation)
# ---------------------------------------------------------------------------

import json
from app.core.ai_router import call_with_fallback

_CLASSIFY_SYSTEM = """
You are an expert legal triage classifier for the Indian justice system.
Analyze the user's complaint and map it to EXACTLY ONE of the following categories:
- fir_not_registered
- domestic_violence
- land_dispute
- consumer_complaint
- cyber_fraud
- crop_insurance_rejected
- disaster_relief_denied
- other

Provide your output ONLY as a valid JSON object with the following fields:
1. case_type: One of the exact categories listed above.
2. confidence_score: A float between 0.0 and 1.0 indicating your confidence.
3. legal_provision: The specific Indian legal provision or law likely to apply (e.g., "Section 156(3) CrPC", "Consumer Protection Act, 2019", "Section 12 PWDVA"). Use "Unknown" if not applicable.

Return NO MARKDOWN FENCES, NO PREAMBLE. Only raw JSON.
"""

async def classify_case_llm(text: str) -> tuple[str, float, str]:
    """
    Uses the AI Router to classify the free-text complaint into standard categories,
    yielding (case_type, confidence_score, legal_provision).
    """
    try:
        response_text, _ = await call_with_fallback(
            prompt=text[:1500],
            preferred="gemini",
            system=_CLASSIFY_SYSTEM,
            max_tokens=300
        )
        
        # Clean markdown fences if the LLM hallucinated them
        clean = response_text.replace("`json", "").replace("`", "").strip()
        data = json.loads(clean)
        
        c_type = str(data.get("case_type", "other"))
        conf = float(data.get("confidence_score", 0.5))
        prov = str(data.get("legal_provision", "Unknown"))
        return c_type, conf, prov
        
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"[classify_case_llm] Failed to classify using LLM: {e}")
        return "other", 0.0, "Unknown"
