from pydantic import BaseModel, Field
from enum import Enum

from app.models.case import CaseType, UserTier


# ---------------------------------------------------------------------------
# Evidentiary mapping — every legal point must cite a verifiable source
# (upgrade from README: agents exchange LegalPoint objects, not plain text)
# ---------------------------------------------------------------------------


class LegalPoint(BaseModel):
    argument: str
    statute_cited: str  # "Section 154 CrPC" — must match IndianKanoon lookup
    source_verification_url: str  # "https://api.indiankanoon.org/doc/1233994/"
    confidence: float = Field(ge=0.0, le=1.0, default=0.8)


# ---------------------------------------------------------------------------
# Debate models
# ---------------------------------------------------------------------------


class DebateRound(BaseModel):
    round_number: int
    advocate_draft: str
    advocate_points: list[LegalPoint] = []  # evidentiary map for this round
    bureaucrat_objections: list[str]
    objection_severity: list[str]  # "critical" | "moderate" | "minor"
    mediator_verdict: str
    patch_applied: bool
    patched_draft: str = ""


# ---------------------------------------------------------------------------
# Document status & gap tracking
# ---------------------------------------------------------------------------


class DocumentStatus(str, Enum):
    DRAFT = "draft"
    HARDENED = "hardened"  # survived adversarial loop with no unresolved gaps
    ANNOTATED = "annotated"  # has unresolved gaps noted — honest AI
    FILED = "filed"


class UnresolvedGap(BaseModel):
    field: str  # e.g. "witness_name"
    description: str  # what is missing and why it matters
    how_to_fix: str  # actionable instruction for the user


# ---------------------------------------------------------------------------
# Core legal document — the main output of the entire pipeline
# ---------------------------------------------------------------------------


class LegalDocument(BaseModel):
    # Identity
    case_type: CaseType
    document_title: str
    document_body: str  # final hardened document text (English)
    document_body_hindi: str = ""  # Hindi version (Tier 3 AI fills this)

    # Adversarial trace (shown in AgentTraceLog on frontend)
    debate_rounds: list[DebateRound] = []
    total_rounds: int = 0
    mediator_override_triggered: bool = False  # True when round cap hit
    unresolved_gaps: list[UnresolvedGap] = []

    # Legal context
    applicable_sections: list[str] = []
    authority_to_file: str = ""
    filing_instructions: str = ""
    filing_instructions_hindi: str = ""
    required_documents: list[str] = []

    # Status
    status: DocumentStatus = DocumentStatus.DRAFT
    confidence_score: float = Field(ge=0.0, le=1.0, default=0.0)

    # AI-generated fields (Tier 3 / Tier 4)
    summary: str = ""
    summary_hindi: str = ""
    next_steps: list[str] = []
    lawyer_note: str = ""  # Tier 4 (Claude) only

    # Metadata
    tier_used: UserTier = UserTier.FREE
    processing_time_ms: int | None = None
    provider_used: str = ""  # "gemini" | "groq" | "claude"
    session_id: str = ""  # LangGraph thread_id for checkpoint resumption


# ---------------------------------------------------------------------------
# API request / response contracts
# ---------------------------------------------------------------------------


class AnalyzeRequest(BaseModel):
    text: str = Field(..., min_length=10, max_length=5000)
    lang: str = "en"
    tier: str = "free"
    user_name: str = ""
    user_location: str = ""
    user_id: str | None = None


class AnalyzeResponse(LegalDocument):
    pass  # LegalDocument is the full response — no additional fields needed


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    document_data: str  # JSON-stringified LegalDocument
    lang: str = "en"
    tier: str = "free"


class ChatResponse(BaseModel):
    reply: str
    lang: str


class VoiceRequest(BaseModel):
    audio_base64: str  # base64-encoded audio bytes
    lang_hint: str = "hi"  # hint for Sarvam AI STT


class VoiceResponse(BaseModel):
    transcript: str
    detected_language: str
