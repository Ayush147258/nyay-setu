"""
app/core/document_builder.py

Fills legal document templates with extracted entities — deterministically.
Zero LLM. Pure string substitution + smart defaults + gap detection.
"""

from __future__ import annotations

import re
from datetime import date
from functools import lru_cache
from pathlib import Path

from app.models.case import CaseType, LegalContext
from app.models.document import UnresolvedGap


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_TEMPLATES_DIR = Path(__file__).parent.parent.parent / "data" / "legal_templates"

# Fallback template when no specific template exists for a case type
_FALLBACK_TEMPLATE = "rti_request.txt"

# Map CaseType → template file name
_CASE_TEMPLATE_MAP: dict[CaseType, str] = {
    CaseType.FIR_REFUSAL: "fir_refusal.txt",
    CaseType.CROP_INSURANCE: "pmfby_grievance.txt",
    CaseType.FLOOD_RELIEF: "sdrf_application.txt",
    CaseType.WAGE_THEFT: "labour_complaint.txt",
    CaseType.RTI_REQUEST: "rti_request.txt",
    CaseType.CONSUMER_COMPLAINT: "consumer_complaint.txt",
    CaseType.LAND_DISPUTE: "land_dispute.txt",
    CaseType.DOMESTIC_VIOLENCE: "domestic_violence.txt",
    CaseType.LABOUR_COMPLAINT: "labour_complaint.txt",
    CaseType.UNKNOWN: _FALLBACK_TEMPLATE,
}

# ---------------------------------------------------------------------------
# Human-readable gap descriptions for common placeholder names
# ---------------------------------------------------------------------------

_GAP_DESCRIPTIONS: dict[str, tuple[str, str]] = {
    # field_name: (description, how_to_fix)
    "complainant_name": (
        "Your full legal name is required for the application",
        "Provide your complete name as it appears on your Aadhaar card",
    ),
    "complainant_address": (
        "Your residential address is needed to establish jurisdiction",
        "Provide your complete address: house number, street, village/town, district, state, PIN",
    ),
    "complainant_contact": (
        "A contact number lets the court / authority reach you",
        "Provide your active mobile number",
    ),
    "district": (
        "The district is needed to route the application to the correct authority",
        "Mention the district where the incident occurred or where you reside",
    ),
    "state": (
        "The state is required for correct authority identification",
        "Provide the name of your state",
    ),
    "incident_date": (
        "The date of the incident is a mandatory fact for the application",
        "Provide the exact date (DD/MM/YYYY) when the incident occurred",
    ),
    "incident_description": (
        "A description of what happened is the core of your complaint",
        "Describe in 2–3 sentences exactly what happened, who was involved, and what was the harm",
    ),
    "police_station": (
        "The police station name is required to direct the court order",
        "Provide the full name of the police station where you tried to file the FIR",
    ),
    "complaint_date": (
        "The date you visited the police station is required",
        "Provide the date (DD/MM/YYYY) when you went to file the FIR",
    ),
    "employer_name": (
        "Your employer's name or company name is required",
        "Provide the full name of the person or company that owes you wages",
    ),
    "amount_owed": (
        "The exact amount of unpaid wages must be specified",
        "Provide the total amount (in rupees) that your employer owes you",
    ),
    "crop_name": (
        "The crop name is required to process the PMFBY insurance claim",
        "Specify the name of the crop that was damaged (e.g., Wheat, Paddy, Cotton)",
    ),
    "insurance_company": (
        "The insurance company name is required to direct the grievance",
        "Provide the name of the insurance company that rejected your claim",
    ),
    "village": (
        "Your village name is required for relief / farming applications",
        "Provide your village name",
    ),
    "damage_type": (
        "The type of damage must be specified for SDRF compensation",
        "Specify what was damaged: house / crop / livestock / road",
    ),
    "department_name": (
        "The government department you are filing the RTI against must be named",
        "Name the specific government department or ministry (e.g., 'District Supply Office, Patna')",
    ),
    "information_requested": (
        "You must specify exactly what information you are requesting",
        "Describe in 1–3 sentences the specific documents, records, or information you need",
    ),
    "seller_name": (
        "The seller or company name is required for the consumer complaint",
        "Provide the full name of the shop, company, or platform you purchased from",
    ),
    "product_description": (
        "A description of the defective product is required",
        "Describe the product: name, model, brand, and what defect it has",
    ),
    "khasra_number": (
        "The Khasra/Survey number uniquely identifies your land parcel",
        "Find your Khasra number on your land record document (Khatauni)",
    ),
    "accused_name": (
        "The name of the person encroaching or causing the dispute is required",
        "Provide the full name of the person who has encroached on or disputed your land",
    ),
    "respondent_name": (
        "The name of the person committing domestic violence is required",
        "Provide the full name of the respondent (abuser)",
    ),
}


# ---------------------------------------------------------------------------
# Template loader — cached
# ---------------------------------------------------------------------------


@lru_cache(maxsize=20)
def load_template(template_file: str) -> str:
    """
    Load and cache a legal template from data/legal_templates/.
    Falls back to rti_request.txt if the file does not exist.
    """
    path = _TEMPLATES_DIR / template_file
    if not path.exists():
        path = _TEMPLATES_DIR / _FALLBACK_TEMPLATE
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Default values for common placeholders
# ---------------------------------------------------------------------------


def _build_defaults(user_name: str = "", user_location: str = "") -> dict[str, str]:
    today = date.today()
    month_names = [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    ]
    filing_date = f"{today.day:02d} {month_names[today.month - 1]} {today.year}"

    defaults: dict[str, str] = {
        "filing_date": filing_date,
        "complainant_name": user_name if user_name else "[Your Full Name]",
        "complainant_address": user_location if user_location else "[Your Complete Address]",
        "complainant_contact": "[Your Phone Number]",
        "district": "[Your District]",
        "state": "[Your State]",
        "village": "[Your Village]",
        "tehsil": "[Your Tehsil]",
        "complaint_date": filing_date,
        # PMFBY-specific
        "scheme_year": str(today.year),
        "policy_number": "[Policy Number]",
        "land_record_number": "[Khasra/Survey No.]",
        "land_area": "[Area in Hectares]",
        "premium_amount": "[Premium Amount]",
        "rejection_date": "[Rejection Date]",
        "rejection_reason": "[Reason stated by insurance company]",
        "grounds_for_appeal": "the damage was caused by a notified peril covered under the policy",
        "enclosed_documents": "copies of relevant documents",
        "aadhaar_last4": "XXXX",
        # SDRF-specific
        "disaster_type": "flood",
        "time_elapsed": "30 days",
        "estimated_loss": "[Estimated Loss Amount]",
        "disaster_date": "[Date of Disaster]",
        "damage_type": "[house / crop / livestock]",
        # RTI-specific
        "department_name": "[Government Department Name]",
        "department_address": "[Department Address]",
        "subject_matter": "[Subject of Information Request]",
        "information_requested": "[Describe the specific information you need]",
        "time_period": "[Relevant time period, e.g., April 2023 to March 2024]",
        "reference_number": "Not known",
        "payment_mode": "Indian Postal Order / court fee stamp",
        # Labour-specific
        "designation": "[Your Job Title]",
        "employer_address": "[Employer's Address]",
        "employment_start": "[Start Date]",
        "employment_end": "[End Date / Present]",
        "unpaid_period": "[Months/Period of Non-payment]",
        "last_payment_date": "[Last Date Salary Was Paid]",
        "employer_reason": "[Reason given by employer, if any]",
        # Consumer-specific
        "seller_address": "[Seller's Address]",
        "purchase_date": "[Date of Purchase]",
        "purchase_amount": "[Purchase Amount in Rs.]",
        "defect_description": "[Description of defect or deficiency]",
        "compensation_claimed": "5000",
        "litigation_cost": "2000",
        # Land dispute
        "khasra_number": "[Khasra/Survey No.]",
        "khatauni_number": "[Khatauni No.]",
        "title_basis": "[Sale deed / inheritance / govt allotment]",
        "dispute_description": "[Describe the nature of the dispute]",
        "accused_address": "[Accused Person's Address]",
        # Domestic violence
        "respondent_address": "[Respondent's Address]",
        "relationship": "[Husband / Father-in-law / Other]",
        "physical_abuse_details": "[Details if applicable, else write 'Not applicable']",
        "emotional_abuse_details": "[Details if applicable]",
        "economic_abuse_details": "[Details if applicable]",
        "start_date": "[Date abuse began]",
        "monetary_relief": "[Amount claimed in Rs.]",
        "custody_details": "Not applicable",
        "product_description": "[Product name and description]",
        "seller_name": "[Seller / Company Name]",
        "accused_name": "[Name of accused person]",
    }
    return defaults


# ---------------------------------------------------------------------------
# Core fill function
# ---------------------------------------------------------------------------


def fill_template(
    template: str,
    entities: dict[str, str],
    defaults: dict[str, str] | None = None,
) -> str:
    """
    Replace all {placeholder} tokens in the template.

    Priority: entities → defaults → "[PLACEHOLDER_NAME — Please Fill]"
    """
    if defaults is None:
        defaults = _build_defaults()

    # Merge: entities override defaults
    merged: dict[str, str] = {**defaults, **{k: v for k, v in entities.items() if v}}

    # Find all placeholder tokens
    placeholders = re.findall(r"\{([^}]+)\}", template)

    result = template
    for ph in placeholders:
        if ph in merged and merged[ph]:
            result = result.replace(f"{{{ph}}}", merged[ph])
        else:
            # Mark as unfilled — Bureaucrat Agent can catch this
            result = result.replace(f"{{{ph}}}", f"[{ph.upper().replace('_', ' ')} — Please Fill]")

    return result


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def build_initial_document(
    case_type: CaseType,
    entities: dict[str, str],
    legal_context: LegalContext,
    user_name: str = "",
    user_location: str = "",
) -> str:
    """
    Load template → fill with entities + defaults → inject applicable_sections.
    Returns the fully-filled (or gap-marked) document string.
    """
    template_file = _CASE_TEMPLATE_MAP.get(case_type, _FALLBACK_TEMPLATE)
    template = load_template(template_file)

    defaults = _build_defaults(user_name=user_name, user_location=user_location)

    # Inject case-specific data from legal_context into entities
    extra: dict[str, str] = {}
    if legal_context.authority_to_file:
        extra["authority"] = legal_context.authority_to_file
    if legal_context.scheme_name:
        extra["scheme_name"] = legal_context.scheme_name

    merged_entities = {**extra, **entities}
    document = fill_template(template, merged_entities, defaults)

    # Append applicable sections footer (useful reference for the user)
    if legal_context.applicable_sections:
        sections_text = "\n".join(f"  • {s}" for s in legal_context.applicable_sections)
        document += (
            f"\n\n---\nAPPLICABLE LEGAL PROVISIONS (for reference):\n{sections_text}"
        )

    return document


# ---------------------------------------------------------------------------
# Gap detector
# ---------------------------------------------------------------------------

# Regex that matches our unfilled placeholder pattern
_GAP_PATTERN = re.compile(r"\[([A-Z][A-Z0-9 ]+) — Please Fill\]")


def identify_gaps(document: str) -> list[UnresolvedGap]:
    """
    Scan the filled document for remaining '[... — Please Fill]' markers.
    Returns a list of UnresolvedGap with actionable instructions.
    """
    gaps: list[UnresolvedGap] = []
    seen: set[str] = set()

    for match in _GAP_PATTERN.finditer(document):
        raw_field = match.group(1)  # e.g. "INCIDENT DATE"
        field_key = raw_field.lower().replace(" ", "_")  # → "incident_date"

        if field_key in seen:
            continue
        seen.add(field_key)

        description, how_to_fix = _GAP_DESCRIPTIONS.get(
            field_key,
            (
                f"The field '{raw_field.title()}' is required to complete this application",
                f"Please provide the value for: {raw_field.title()}",
            ),
        )

        gaps.append(
            UnresolvedGap(
                field=field_key,
                description=description,
                how_to_fix=how_to_fix,
            )
        )

    return gaps
