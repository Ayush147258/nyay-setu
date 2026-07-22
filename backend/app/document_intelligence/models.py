"""Canonical contracts for versioned legal-document analysis.

The models in this module form the boundary between parsers, agents, storage,
and the frontend. They intentionally carry provenance instead of passing
unstructured strings between stages.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, Field, field_validator, model_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DocumentFormat(str, Enum):
    PDF = "pdf"
    DOCX = "docx"
    TEXT = "text"
    CSV = "csv"
    SPREADSHEET = "spreadsheet"
    IMAGE = "image"
    EMAIL = "email"
    UNKNOWN = "unknown"


class ParseStatus(str, Enum):
    READY = "ready"
    PARTIAL = "partial"
    OCR_REQUIRED = "ocr_required"
    PASSWORD_PROTECTED = "password_protected"
    CORRUPTED = "corrupted"
    LIMIT_EXCEEDED = "limit_exceeded"
    UNSUPPORTED = "unsupported"
    FAILED = "failed"


class BlockKind(str, Enum):
    TITLE = "title"
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    TABLE = "table"
    LIST_ITEM = "list_item"
    HEADER = "header"
    FOOTER = "footer"
    IMAGE_TEXT = "image_text"
    METADATA = "metadata"


class ReviewState(str, Enum):
    VERIFIED = "verified"
    NEEDS_REVIEW = "needs_review"
    REJECTED = "rejected"


class EvidenceKind(str, Enum):
    PERSON = "person"
    ORGANIZATION = "organization"
    COURT = "court"
    AUTHORITY = "authority"
    DATE = "date"
    MONEY = "money"
    CASE_NUMBER = "case_number"
    LEGAL_PROVISION = "legal_provision"
    DOCUMENT_REFERENCE = "document_reference"
    CONTACT = "contact"
    LOCATION = "location"
    STATEMENT = "statement"


class ClaimKind(str, Enum):
    FACT = "fact"
    LAW = "law"
    INFERENCE = "inference"
    RECOMMENDATION = "recommendation"


class CaseRole(str, Enum):
    JUDGE = "judge"
    AUTHORITY = "authority"
    LAWYER = "lawyer"
    ANALYST = "analyst"


class AnalysisStatus(str, Enum):
    QUEUED = "queued"
    EXTRACTING = "extracting"
    RELATING = "relating"
    RETRIEVING = "retrieving"
    SYNTHESIZING = "synthesizing"
    CRITIQUING = "critiquing"
    VERIFYING = "verifying"
    NEEDS_REVIEW = "needs_review"
    COMPLETED = "completed"
    FAILED = "failed"


class BoundingBox(BaseModel):
    x0: float
    y0: float
    x1: float
    y1: float


class SourceSpan(BaseModel):
    document_id: str
    version_id: str
    page_number: int = Field(ge=1)
    block_id: str
    start_char: int = Field(ge=0)
    end_char: int = Field(gt=0)
    exact_quote: str = Field(min_length=1, max_length=4000)
    bbox: BoundingBox | None = None

    @field_validator("end_char")
    @classmethod
    def end_after_start(cls, value: int, info: Any) -> int:
        start = info.data.get("start_char", 0)
        if value <= start:
            raise ValueError("end_char must be greater than start_char")
        return value


class TableCell(BaseModel):
    row_index: int = Field(ge=0)
    column_index: int = Field(ge=0)
    text: str = ""
    row_span: int = Field(default=1, ge=1)
    column_span: int = Field(default=1, ge=1)
    bbox: BoundingBox | None = None


class TableRow(BaseModel):
    row_index: int = Field(ge=0)
    cells: list[TableCell] = Field(default_factory=list)


class StructuredTable(BaseModel):
    table_id: str
    page_number: int = Field(ge=1)
    rows: list[TableRow] = Field(default_factory=list)
    bbox: BoundingBox | None = None


class DocumentBlock(BaseModel):
    block_id: str
    page_number: int = Field(ge=1)
    sequence: int = Field(ge=0)
    kind: BlockKind = BlockKind.PARAGRAPH
    text: str
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    bbox: BoundingBox | None = None
    table: StructuredTable | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentPage(BaseModel):
    page_number: int = Field(ge=1)
    width: float | None = Field(default=None, gt=0)
    height: float | None = Field(default=None, gt=0)
    rotation: int = Field(default=0)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    extraction_method: Literal["digital", "ocr", "mixed", "none"] = "none"
    warnings: list[str] = Field(default_factory=list)
    blocks: list[DocumentBlock] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentIR(BaseModel):
    tenant_id: str = "default"
    document_id: str
    version_id: str
    case_id: str
    original_name: str
    media_type: str
    document_format: DocumentFormat
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    size_bytes: int = Field(ge=0)
    status: ParseStatus
    parser_name: str
    parser_version: str
    language_hint: str | None = None
    pages: list[DocumentPage] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)

    def block_map(self) -> dict[str, DocumentBlock]:
        return {block.block_id: block for page in self.pages for block in page.blocks}


class EvidenceAtom(BaseModel):
    evidence_id: str
    case_id: str
    kind: EvidenceKind
    label: str
    value: str
    normalized_value: str = ""
    confidence: float = Field(ge=0.0, le=1.0)
    review_state: ReviewState = ReviewState.VERIFIED
    source_spans: list[SourceSpan] = Field(min_length=1)
    extractor_name: str
    extractor_version: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class RelationshipEdge(BaseModel):
    relationship_id: str
    case_id: str
    source_evidence_id: str
    target_evidence_id: str
    relationship_type: str
    description: str
    confidence: float = Field(ge=0.0, le=1.0)
    supporting_evidence_ids: list[str] = Field(min_length=1)
    review_state: ReviewState = ReviewState.VERIFIED


class TimelineEvent(BaseModel):
    event_id: str
    case_id: str
    date_text: str
    normalized_date: str | None = None
    description: str
    evidence_ids: list[str] = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)


class ResearchFinding(BaseModel):
    research_id: str
    title: str
    excerpt: str
    source_url: str
    citation: str = ""
    court: str = ""
    year: str = ""
    provider: Literal["IndianKanoon"] = "IndianKanoon"
    retrieved_at: datetime = Field(default_factory=utc_now)


class ResearchPacket(BaseModel):
    query: str
    status: Literal["disabled", "completed", "failed"]
    findings: list[ResearchFinding] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    provider: Literal["IndianKanoon"] = "IndianKanoon"


class Citation(BaseModel):
    citation_id: str
    evidence_id: str | None = None
    research_id: str | None = None
    source_span: SourceSpan | None = None
    source_url: str | None = None
    display_label: str
    source_type: Literal["uploaded_evidence", "external_authority"] | None = None

    @model_validator(mode="after")
    def exactly_one_source(self) -> "Citation":
        local = bool(self.evidence_id and self.source_span)
        external = bool(self.research_id and self.source_url)
        if local == external:
            raise ValueError("Citation must have exactly one local or external source")
        expected = "uploaded_evidence" if local else "external_authority"
        if self.source_type is not None and self.source_type != expected:
            raise ValueError("Citation source_type does not match its source")
        self.source_type = expected
        return self


class ReportClaim(BaseModel):
    claim_id: str
    statement: str = Field(min_length=1)
    kind: ClaimKind
    evidence_ids: list[str] = Field(default_factory=list)
    research_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    caveat: str | None = None


class ReportSection(BaseModel):
    section_id: str
    title: str
    claims: list[ReportClaim] = Field(default_factory=list)


class ReportCaveat(BaseModel):
    caveat_id: str
    severity: Literal["info", "warning", "blocking"]
    title: str
    detail: str
    evidence_ids: list[str] = Field(default_factory=list)


class LegalAnalysisReport(BaseModel):
    report_id: str
    case_id: str
    version: int = Field(ge=1)
    title: str
    status: AnalysisStatus
    sections: list[ReportSection] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    relationships: list[RelationshipEdge] = Field(default_factory=list)
    timeline: list[TimelineEvent] = Field(default_factory=list)
    research_findings: list[ResearchFinding] = Field(default_factory=list)
    caveats: list[ReportCaveat] = Field(default_factory=list)
    source_document_versions: list[str] = Field(default_factory=list)
    workflow_version: str
    created_at: datetime = Field(default_factory=utc_now)


class IntegrityIssue(BaseModel):
    code: str
    severity: Literal["warning", "blocking"]
    message: str
    entity_type: str
    entity_id: str


class IntegrityResult(BaseModel):
    valid: bool
    issues: list[IntegrityIssue] = Field(default_factory=list)
    checked_claims: int = 0
    checked_evidence: int = 0
    checked_spans: int = 0


class AgentTraceEvent(BaseModel):
    sequence: int = Field(ge=0)
    agent: str
    status: AnalysisStatus
    summary: str
    round_number: int = Field(default=1, ge=1, le=2)
    started_at: datetime
    completed_at: datetime | None = None
    input_ids: list[str] = Field(default_factory=list)
    output_ids: list[str] = Field(default_factory=list)


class AnalysisRun(BaseModel):
    run_id: str
    case_id: str
    status: AnalysisStatus
    workflow_version: str
    document_version_ids: list[str] = Field(min_length=1)
    events: list[AgentTraceEvent] = Field(default_factory=list)
    report_id: str | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class UploadDocumentResponse(BaseModel):
    document: DocumentIR
    duplicate: bool = False


class AnalyzeCaseRequest(BaseModel):
    document_version_ids: list[str] | None = None
    role: CaseRole = CaseRole.ANALYST
    enable_external_research: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "enable_external_research",
            "include_external_research",
        ),
    )


class SearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=1000)
    limit: int = Field(default=8, ge=1, le=25)


class SearchHit(BaseModel):
    score: float = Field(ge=0.0)
    text: str
    citation: Citation


class SearchResponse(BaseModel):
    hits: list[SearchHit]


class CaseChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=10000)


class CaseChatRequest(BaseModel):
    role: CaseRole
    messages: list[CaseChatMessage] = Field(min_length=1, max_length=30)
    language: str = "en"
    document_version_ids: list[str] = Field(default_factory=list, max_length=25)


class CaseChatTraceStep(BaseModel):
    agent: str
    status: Literal["complete", "needs_review"]
    summary: str


class CaseChatResponse(BaseModel):
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    agent_trace: list[CaseChatTraceStep] = Field(default_factory=list)
    role: CaseRole


class ReviewItem(BaseModel):
    review_id: str
    case_id: str
    source_type: str
    source_id: str
    severity: Literal["warning", "blocking"]
    reason: str
    status: Literal["open", "resolved", "dismissed"] = "open"
    created_at: datetime = Field(default_factory=utc_now)


class AnalysisBundle(BaseModel):
    run: AnalysisRun
    report: LegalAnalysisReport
    evidence: list[EvidenceAtom]
    research: ResearchPacket | None = None
    integrity: IntegrityResult
    review_items: list[ReviewItem] = Field(default_factory=list)

