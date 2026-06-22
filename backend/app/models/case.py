from pydantic import BaseModel, Field
from enum import Enum


class CaseType(str, Enum):
    FIR_REFUSAL = "fir_refusal"
    CROP_INSURANCE = "crop_insurance"
    FLOOD_RELIEF = "flood_relief"
    WAGE_THEFT = "wage_theft"
    RTI_REQUEST = "rti_request"
    CONSUMER_COMPLAINT = "consumer_complaint"
    LAND_DISPUTE = "land_dispute"
    DOMESTIC_VIOLENCE = "domestic_violence"
    LABOUR_COMPLAINT = "labour_complaint"
    UNKNOWN = "unknown"


class Language(str, Enum):
    EN = "en"
    HI = "hi"
    HINGLISH = "hinglish"
    BHOJPURI = "bhojpuri"
    MAITHILI = "maithili"
    OTHER = "other"


class UserTier(str, Enum):
    FREE = "free"
    PREMIUM = "premium"


class CaseInput(BaseModel):
    text: str = Field(..., min_length=10, max_length=5000)
    detected_language: Language = Language.EN
    tier: UserTier = UserTier.FREE
    user_name: str = ""
    user_location: str = ""  # district/state for routing
    user_id: str | None = None


class ClassifiedCase(BaseModel):
    """Output of IntakeAgent"""

    original_text: str
    normalized_text: str  # English-normalized version
    case_type: CaseType
    confidence: float = Field(ge=0.0, le=1.0)
    detected_language: Language
    extracted_entities: dict[str, str] = {}  # {"accused_name": "...", "date": "..."}
    user_name: str = ""
    user_location: str = ""
    tier: UserTier = UserTier.FREE


class LegalContext(BaseModel):
    """Output of ResearchAgent"""

    case_type: CaseType
    applicable_sections: list[str]  # ["IPC 166A", "CrPC 156(3)"]
    relevant_precedents: list[str]  # brief SC/HC ruling summaries
    authority_to_file: str  # "Judicial Magistrate First Class"
    filing_url: str = ""  # government portal URL if available
    scheme_name: str = ""  # "PMFBY", "SDRF", etc.
    required_documents: list[str]  # ["FIR copy", "Land record", ...]
