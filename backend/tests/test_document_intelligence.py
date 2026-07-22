from __future__ import annotations

import io

import pytest

from app.config import settings
from app.document_intelligence.chat import CaseChatService
from app.document_intelligence.extraction import LegalExtractorAgent
from app.document_intelligence.ingestion import DocumentIngestionService
from app.document_intelligence.integrity import IntegrityVerifier
from app.document_intelligence.models import (
    AnalyzeCaseRequest,
    CaseChatMessage,
    CaseChatRequest,
    CaseRole,
    DocumentBlock,
    DocumentFormat,
    DocumentIR,
    DocumentPage,
    EvidenceAtom,
    EvidenceKind,
    ParseStatus,
    ResearchFinding,
    ResearchPacket,
    ReviewState,
    SourceSpan,
)
from app.document_intelligence.research import ControlledLegalResearchAgent
from app.document_intelligence.retrieval import CaseRetriever
from app.document_intelligence.storage import LocalDocumentStore, StorageError
from app.integrations.utils import IntegrationError
from app.document_intelligence.workflow import DocumentAnalysisWorkflow


LEGAL_TEXT = """Petitioner: Ramesh Kumar
Respondent: State of Bihar

FIR No. 123 of 2024 was presented on 12/03/2024.
The complaint refers to Section 154 of the Code.
The disputed amount is Rs. 10,000.
The matter was mentioned before the Supreme Court of India.
"""


def ingest_text(
    store: LocalDocumentStore,
    *,
    case_id: str = "case-123",
    filename: str = "petition.txt",
    text: str = LEGAL_TEXT,
):
    service = DocumentIngestionService(store)
    return service.ingest(
        case_id=case_id,
        filename=filename,
        media_type="text/plain",
        stream=io.BytesIO(text.encode("utf-8")),
        language_hint="en",
    )


def test_text_ingestion_hashes_and_preserves_source(tmp_path):
    store = LocalDocumentStore(tmp_path)
    result = ingest_text(store)

    assert result.duplicate is False
    assert result.document.document_format == DocumentFormat.TEXT
    assert result.document.status == ParseStatus.READY
    assert len(result.document.sha256) == 64
    assert result.document.pages[0].blocks
    persisted = store.get_ir(
        "case-123",
        result.document.document_id,
        result.document.version_id,
    )
    assert persisted.sha256 == result.document.sha256


def test_identical_upload_is_idempotent(tmp_path):
    store = LocalDocumentStore(tmp_path)
    first = ingest_text(store)
    second = ingest_text(store)

    assert second.duplicate is True
    assert second.document.document_id == first.document.document_id
    assert second.document.version_id == first.document.version_id
    assert len(store.list_case_documents("case-123")) == 1


def test_changed_file_creates_immutable_version(tmp_path):
    store = LocalDocumentStore(tmp_path)
    first = ingest_text(store)
    second = ingest_text(store, text=LEGAL_TEXT + "\nAnnexure A was filed.")

    assert second.duplicate is False
    assert second.document.document_id == first.document.document_id
    assert second.document.version_id != first.document.version_id
    assert second.document.sha256 != first.document.sha256
    assert len(store.list_case_documents("case-123")) == 2


def test_unknown_format_is_preserved_with_explicit_status(tmp_path):
    store = LocalDocumentStore(tmp_path)
    service = DocumentIngestionService(store)
    result = service.ingest(
        case_id="case-unknown",
        filename="legacy.bin",
        media_type="application/octet-stream",
        stream=io.BytesIO(b"\x00\x01\x02 proprietary"),
    )

    assert result.document.status == ParseStatus.UNSUPPORTED
    assert result.document.warnings
    assert store.list_case_documents("case-unknown")


def test_extractor_produces_exact_verifiable_spans(tmp_path):
    store = LocalDocumentStore(tmp_path)
    document = ingest_text(store).document
    evidence = LegalExtractorAgent().extract([document])
    result = IntegrityVerifier().verify(
        documents=[document],
        evidence=evidence,
    )

    assert result.valid is True
    assert result.checked_spans >= 5
    assert {item.kind for item in evidence} >= {
        EvidenceKind.PERSON,
        EvidenceKind.DATE,
        EvidenceKind.MONEY,
        EvidenceKind.CASE_NUMBER,
        EvidenceKind.LEGAL_PROVISION,
    }
    block_map = document.block_map()
    for item in evidence:
        for span in item.source_spans:
            block = block_map[span.block_id]
            assert block.text[span.start_char : span.end_char] == span.exact_quote


def test_integrity_verifier_rejects_tampered_span():
    document = DocumentIR(
        document_id="doc-1",
        version_id="ver-1",
        case_id="case-1",
        original_name="source.txt",
        media_type="text/plain",
        document_format=DocumentFormat.TEXT,
        sha256="a" * 64,
        size_bytes=5,
        status=ParseStatus.READY,
        parser_name="test",
        parser_version="1",
        pages=[
            DocumentPage(
                page_number=1,
                blocks=[
                    DocumentBlock(
                        block_id="block-1",
                        page_number=1,
                        sequence=0,
                        text="hello",
                    )
                ],
            )
        ],
    )
    evidence = EvidenceAtom(
        evidence_id="ev-1",
        case_id="case-1",
        kind=EvidenceKind.STATEMENT,
        label="Statement",
        value="world",
        confidence=0.9,
        review_state=ReviewState.VERIFIED,
        source_spans=[
            SourceSpan(
                document_id="doc-1",
                version_id="ver-1",
                page_number=1,
                block_id="block-1",
                start_char=0,
                end_char=5,
                exact_quote="world",
            )
        ],
        extractor_name="test",
        extractor_version="1",
    )

    result = IntegrityVerifier().verify(
        documents=[document],
        evidence=[evidence],
    )

    assert result.valid is False
    assert any(issue.code == "source_quote" for issue in result.issues)


def test_full_workflow_builds_cited_report_and_trace(tmp_path):
    store = LocalDocumentStore(tmp_path)
    document = ingest_text(store).document
    workflow = DocumentAnalysisWorkflow(store)

    bundle = workflow.run("case-123", [document.version_id])

    assert bundle.integrity.valid is True
    assert bundle.report.status.value in {"completed", "needs_review"}
    assert bundle.report.citations
    assert all(claim.evidence_ids for section in bundle.report.sections for claim in section.claims)
    assert [event.agent for event in bundle.run.events] == [
        "Extractor",
        "Relationship",
        "Synthesis",
        "Adversarial",
        "Verifier / Mediator",
    ]
    persisted = store.latest_case_artifact("case-123", "reports")
    assert persisted["report_id"] == bundle.report.report_id


def test_retrieval_rejects_cross_case_documents(tmp_path):
    store = LocalDocumentStore(tmp_path)
    first = ingest_text(store, case_id="case-a").document
    second = ingest_text(store, case_id="case-b").document

    with pytest.raises(ValueError, match="isolated"):
        CaseRetriever().search([first, second], "FIR")


@pytest.mark.asyncio
async def test_role_chat_returns_source_citations(tmp_path):
    store = LocalDocumentStore(tmp_path)
    document = ingest_text(store).document
    request = CaseChatRequest(
        role=CaseRole.JUDGE,
        messages=[
            CaseChatMessage(
                role="user",
                content="When was the FIR presented?",
            )
        ],
    )

    response = await CaseChatService().answer(
        documents=[document],
        request=request,
    )

    assert response.role == CaseRole.JUDGE
    assert response.citations
    assert "[1]" in response.answer
    assert response.citations[0].source_span.version_id == document.version_id
@pytest.mark.asyncio
async def test_controlled_research_disabled_without_api_key(monkeypatch):
    monkeypatch.setattr(settings, "indiankanoon_api_key", "")

    packet = await ControlledLegalResearchAgent().research([])

    assert packet.status == "disabled"
    assert packet.findings == []
    assert packet.warnings


@pytest.mark.asyncio
async def test_controlled_research_failure_is_non_fatal(monkeypatch):
    monkeypatch.setattr(settings, "indiankanoon_api_key", "test-key")

    async def fail_search(*_args, **_kwargs):
        raise IntegrationError("provider unavailable")

    monkeypatch.setattr(
        "app.document_intelligence.research.search_indiankanoon",
        fail_search,
    )

    packet = await ControlledLegalResearchAgent().research([])

    assert packet.status == "failed"
    assert packet.findings == []
    assert "failed safely" in packet.warnings[0]


@pytest.mark.asyncio
async def test_controlled_research_empty_result_has_warning(monkeypatch):
    monkeypatch.setattr(settings, "indiankanoon_api_key", "test-key")

    async def empty_search(*_args, **_kwargs):
        return []

    monkeypatch.setattr(
        "app.document_intelligence.research.search_indiankanoon",
        empty_search,
    )

    packet = await ControlledLegalResearchAgent().research([])

    assert packet.status == "completed"
    assert packet.findings == []
    assert packet.warnings == [
        "No citable IndianKanoon result was returned for the extracted record."
    ]


@pytest.mark.asyncio
async def test_controlled_research_keeps_only_valid_indiankanoon_urls(monkeypatch):
    monkeypatch.setattr(settings, "indiankanoon_api_key", "test-key")

    async def successful_search(*_args, **_kwargs):
        return [
            {
                "title": "Lalita Kumari v. Government of Uttar Pradesh",
                "excerpt": "Registration of an FIR is mandatory in qualifying cases.",
                "source_url": "https://indiankanoon.org/doc/10239019/",
                "citation": "AIR 2014 SC 187",
                "court": "Supreme Court of India",
                "year": "2014",
            },
            {
                "title": "Untrusted result",
                "excerpt": "This result must not enter the report.",
                "source_url": "https://example.com/doc/123/",
            },
            {
                "title": "Malformed IndianKanoon result",
                "excerpt": "This path is not a judgment URL.",
                "source_url": "https://indiankanoon.org/search/?formInput=test",
            },
        ]

    monkeypatch.setattr(
        "app.document_intelligence.research.search_indiankanoon",
        successful_search,
    )

    packet = await ControlledLegalResearchAgent().research([])

    assert packet.status == "completed"
    assert len(packet.findings) == 1
    assert packet.findings[0].source_url == "https://indiankanoon.org/doc/10239019/"
    assert "2 research result(s) were excluded" in packet.warnings[0]


def test_research_request_accepts_current_and_legacy_flag_names():
    current = AnalyzeCaseRequest.model_validate({"enable_external_research": True})
    legacy = AnalyzeCaseRequest.model_validate({"include_external_research": True})

    assert current.enable_external_research is True
    assert legacy.enable_external_research is True


def test_workflow_persists_and_labels_external_research(tmp_path):
    store = LocalDocumentStore(tmp_path)
    document = ingest_text(store).document
    workflow = DocumentAnalysisWorkflow(store)

    class SuccessfulResearch:
        async def research(self, _evidence):
            return ResearchPacket(
                query="Section 154 Code",
                status="completed",
                findings=[
                    ResearchFinding(
                        research_id="research-test-1",
                        title="Lalita Kumari v. Government of Uttar Pradesh",
                        excerpt="Registration of an FIR is mandatory in qualifying cases.",
                        source_url="https://indiankanoon.org/doc/10239019/",
                        citation="AIR 2014 SC 187",
                        court="Supreme Court of India",
                        year="2014",
                    )
                ],
            )

    workflow.research_agent = SuccessfulResearch()
    bundle = workflow.run(
        "case-123",
        [document.version_id],
        enable_external_research=True,
    )

    assert bundle.integrity.valid is True
    assert len(bundle.report.research_findings) == 1
    assert bundle.research is not None
    assert bundle.research.status == "completed"
    assert [event.agent for event in bundle.run.events][:3] == [
        "Extractor",
        "Controlled Legal Research",
        "Relationship",
    ]
    assert {
        citation.source_type for citation in bundle.report.citations
    } == {"uploaded_evidence", "external_authority"}
    external_claims = [
        claim
        for section in bundle.report.sections
        for claim in section.claims
        if claim.research_ids
    ]
    assert external_claims
    assert external_claims[0].research_ids == ["research-test-1"]

    persisted = store.get_case_artifact(
        "case-123",
        "research",
        bundle.run.run_id,
    )
    assert persisted["status"] == "completed"
    assert persisted["findings"][0]["source_url"].startswith(
        "https://indiankanoon.org/doc/"
    )
    with pytest.raises(StorageError, match="Immutable"):
        store.save_case_artifact_immutable(
            "case-123",
            "research",
            bundle.run.run_id,
            persisted,
        )


def test_workflow_continues_when_research_raises(tmp_path):
    store = LocalDocumentStore(tmp_path)
    document = ingest_text(store).document
    workflow = DocumentAnalysisWorkflow(store)

    class FailingResearch:
        async def research(self, _evidence):
            raise RuntimeError("temporary provider failure")

    workflow.research_agent = FailingResearch()
    bundle = workflow.run(
        "case-123",
        [document.version_id],
        enable_external_research=True,
    )

    assert bundle.report.research_findings == []
    assert bundle.research is not None
    assert bundle.research.status == "failed"
    assert any(
        caveat.title == "External legal research incomplete"
        for caveat in bundle.report.caveats
    )
    persisted = store.get_case_artifact(
        "case-123",
        "research",
        bundle.run.run_id,
    )
    assert persisted["status"] == "failed"
    assert persisted["warnings"]
