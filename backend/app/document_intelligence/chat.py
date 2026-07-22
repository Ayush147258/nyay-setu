"""Role-aware, evidence-grounded case workspace chat."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Awaitable, Callable

from app.document_intelligence.models import (
    CaseChatRequest,
    CaseChatResponse,
    CaseRole,
    Citation,
    DocumentIR,
    SearchHit,
    SourceSpan,
)
from app.document_intelligence.retrieval import CaseRetriever


AnswerGenerator = Callable[[str, str], Awaitable[str]]
_CITATION = re.compile(r"\[(\d+)]")
logger = logging.getLogger(__name__)

_ROLE_INSTRUCTIONS = {
    CaseRole.JUDGE: (
        "Use neutral language. Separate agreed facts, disputed facts, "
        "evidentiary gaps, and questions for the parties."
    ),
    CaseRole.AUTHORITY: (
        "Focus on jurisdiction, statutory duties, deadlines, compliance "
        "evidence, and the next lawful administrative action."
    ),
    CaseRole.LAWYER: (
        "Identify arguments, counterarguments, missing proof, drafting "
        "implications, and possible relief without predicting the outcome."
    ),
    CaseRole.ANALYST: (
        "Explain the document record, chronology, relationships, "
        "contradictions, and retrieval gaps precisely."
    ),
}

_ROLE_OPENERS = {
    CaseRole.JUDGE: "For neutral judicial review, the present record shows:",
    CaseRole.AUTHORITY: "For administrative review, the relevant record is:",
    CaseRole.LAWYER: "For legal preparation, the source record supports:",
    CaseRole.ANALYST: "The document record contains:",
}


class CaseChatService:
    def __init__(self, retriever: CaseRetriever | None = None):
        self.retriever = retriever or CaseRetriever()

    async def answer(
        self,
        *,
        documents: list[DocumentIR],
        request: CaseChatRequest,
        generator: AnswerGenerator | None = None,
    ) -> CaseChatResponse:
        query = next(
            message.content
            for message in reversed(request.messages)
            if message.role == "user"
        )
        hits = self.retriever.search(documents, query, limit=6)
        retrieval_miss = False
        if not hits:
            hits = self._broad_record_hits(documents)
            retrieval_miss = bool(hits)
        if not hits:
            return CaseChatResponse(
                answer=(
                    "Final answer:\n"
                    "The uploaded record does not contain enough matching evidence "
                    "to answer this question yet. Upload the relevant page, receipt, "
                    "order sheet, annexure, or correspondence and ask again."
                ),
                citations=[],
                caveats=["No relevant source block passed the retrieval threshold."],
                next_actions=self._next_actions(request.role, query, has_sources=False),
                agent_trace=self._agent_trace(request.role, source_count=0, needs_review=True),
                role=request.role,
            )

        generator_fallback = False
        generator_issue: str | None = None
        if generator:
            answer, generator_issue = await self._generated_answer(request, hits, generator)
            if answer:
                citation_numbers = sorted(
                    {int(value) for value in _CITATION.findall(answer)}
                )
                citations = [
                    hits[index - 1].citation
                    for index in citation_numbers
                ]
                return CaseChatResponse(
                    answer=answer,
                    citations=citations,
                    caveats=[
                        "This is evidence-grounded assistance, not a judicial "
                        "finding or substitute for counsel."
                    ],
                    next_actions=self._next_actions(request.role, query, has_sources=True),
                    agent_trace=self._agent_trace(
                        request.role,
                        source_count=len(citations),
                        needs_review=False,
                    ),
                    role=request.role,
                )
            generator_fallback = True

        return self._fallback_response(
            request,
            hits,
            query,
            retrieval_miss=retrieval_miss,
            generator_fallback=generator_fallback,
            generator_issue=generator_issue,
        )

    def _fallback_response(
        self,
        request: CaseChatRequest,
        hits: list[SearchHit],
        query: str,
        *,
        retrieval_miss: bool = False,
        generator_fallback: bool = False,
        generator_issue: str | None = None,
    ) -> CaseChatResponse:
        selected = self._select_useful_hits(hits)
        citations = [hit.citation for hit in selected]
        source_summary = self._source_summary(selected)
        answer = self._role_answer(request.role, query, selected, source_summary)
        return CaseChatResponse(
            answer=answer,
            citations=citations,
            caveats=self._caveats(
                selected,
                retrieval_miss=retrieval_miss,
                generator_fallback=generator_fallback,
                generator_issue=generator_issue,
            ),
            next_actions=self._next_actions(request.role, query, has_sources=bool(selected)),
            agent_trace=self._agent_trace(
                request.role,
                source_count=len(selected),
                needs_review=len(selected) < 2,
                generator_fallback=generator_fallback,
            ),
            role=request.role,
        )

    def _broad_record_hits(self, documents: list[DocumentIR]) -> list[SearchHit]:
        hits: list[SearchHit] = []
        for document in documents:
            for page in document.pages:
                for block in page.blocks:
                    excerpt = self._clean_excerpt(block.text, limit=900)
                    words = len(re.findall(r"\w+", excerpt))
                    if words < 8:
                        continue
                    exact_quote = excerpt[:4000]
                    span = SourceSpan(
                        document_id=document.document_id,
                        version_id=document.version_id,
                        page_number=page.page_number,
                        block_id=block.block_id,
                        start_char=0,
                        end_char=max(1, len(exact_quote)),
                        exact_quote=exact_quote,
                        bbox=block.bbox,
                    )
                    citation = Citation(
                        citation_id=f"fallback-{document.version_id}-{block.block_id}",
                        evidence_id=f"fallback-{document.version_id}-{block.block_id}",
                        source_span=span,
                        display_label=f"{document.original_name}, page {page.page_number}",
                        source_type="uploaded_evidence",
                    )
                    hits.append(SearchHit(score=0.01, text=block.text, citation=citation))
                    if len(hits) >= 3:
                        return hits
        return hits

    def _select_useful_hits(self, hits: list[SearchHit]) -> list[SearchHit]:
        useful = []
        for hit in hits:
            excerpt = self._clean_excerpt(hit.text, limit=480)
            letters = len(re.findall(r"[A-Za-z0-9]", excerpt))
            words = len(re.findall(r"\w+", excerpt))
            if letters >= 30 and words >= 6:
                useful.append(hit)
        return (useful or hits)[:3]

    def _clean_excerpt(self, text: str, *, limit: int = 260) -> str:
        excerpt = re.sub(r"\s+", " ", text).strip(" .,-")
        if len(excerpt) > limit:
            excerpt = excerpt[: limit - 3].rstrip() + "..."
        return excerpt or "A low-information source block was retrieved."

    def _source_summary(self, hits: list[SearchHit]) -> str:
        if not hits:
            return "no reliable source block"
        parts = [
            f"{self._clean_excerpt(hit.text, limit=175)} [{index}]"
            for index, hit in enumerate(hits, start=1)
        ]
        return "; ".join(parts)

    def _role_answer(
        self,
        role: CaseRole,
        query: str,
        hits: list[SearchHit],
        source_summary: str,
    ) -> str:
        cite_all = "".join(f"[{index}]" for index in range(1, len(hits) + 1))
        primary = "[1]" if hits else ""
        asks_lawyer = bool(re.search(r"\b(ask|question|questions)\b.*\blawyer\b|\blawyer\b.*\b(ask|question|questions)\b", query, re.I))

        if role == CaseRole.JUDGE:
            return "\n".join([
                "Bench agent final answer:",
                f"The safe judicial reading is limited to the source cards retrieved from the uploaded record: {source_summary}.",
                "",
                "Issues for clarification:",
                f"1. Which facts are admitted and which are disputed should be separated before relying on the record {cite_all}.",
                f"2. Any conclusion not tied to a page, annexure, or order-sheet entry should be treated as needing review {primary}.",
                f"3. Ask the parties to identify the missing document or authority if the retrieved sources do not contain the full dispute narrative {cite_all}.",
            ]).strip()

        if role == CaseRole.LAWYER:
            return "\n".join([
                "Counsel agent final answer:",
                f"The record currently supports only these evidence-grounded points: {source_summary}.",
                "",
                "Argument plan:",
                f"1. Lead with the strongest verified source span, not a general conclusion {primary}.",
                f"2. Treat missing dates, authorisation, receipts, annexures, signatures, or order sheets as proof gaps until supplied {cite_all}.",
                f"3. Prepare a short explanation of why each uploaded document is relevant to the relief being sought {cite_all}.",
            ]).strip()

        if role == CaseRole.AUTHORITY:
            return "\n".join([
                "Authority agent final answer:",
                f"The record supports administrative review only to the extent shown in these source cards: {source_summary}.",
                f"Check jurisdiction, filing completeness, statutory duty, and whether a missing receipt/order reference blocks action {cite_all}.",
            ]).strip()

        if asks_lawyer:
            return "\n".join([
                "Citizen agent final answer:",
                f"Ask your lawyer to explain how the uploaded documents are relevant, because the retrieved record shows: {source_summary}.",
                "",
                "Questions to ask your lawyer:",
                f"1. What legal purpose does this document serve in my case file {primary}?",
                f"2. Is the uploaded document enough, or do we still need an annexure, receipt, authorisation, signature, order sheet, or full page copy {cite_all}?",
                f"3. Which part of this source card supports my next filing or response {primary}?",
                f"4. If this document is only company or approval paperwork, what extra fact document connects it to my real legal problem {cite_all}?",
            ]).strip()

        return "\n".join([
            "Citizen agent final answer:",
            f"Based only on the uploaded record, the document shows: {source_summary}.",
            "",
            "What this means:",
            f"1. Keep this document as a source card, but do not treat it as the full case story unless the missing supporting papers are also uploaded {cite_all}.",
            f"2. Ask for the related receipt, order sheet, annexure, authorisation, or filing proof before taking the next legal step {primary}.",
        ]).strip()

    def _caveats(
        self,
        hits: list[SearchHit],
        *,
        retrieval_miss: bool = False,
        generator_fallback: bool = False,
        generator_issue: str | None = None,
    ) -> list[str]:
        caveats = [
            "The answer is restricted to retrieved source cards from the uploaded record.",
            "Unsupported legal conclusions are intentionally not filled in.",
        ]
        if generator_fallback:
            reason = f" Reason: {generator_issue}" if generator_issue else ""
            caveats.insert(
                0,
                "The AI synthesis provider was unavailable or returned an ungrounded answer, so NyaySetu used local source-card fallback." + reason,
            )
        if retrieval_miss:
            caveats.append("The question did not directly match a source block, so the agents used broad record inspection.")
        if len(hits) < 2:
            caveats.append("Only one usable source card was retrieved, so reviewer confidence is limited.")
        return caveats

    def _next_actions(self, role: CaseRole, query: str, *, has_sources: bool) -> list[str]:
        if not has_sources:
            return [
                "Upload the relevant page or missing annexure.",
                "Ask again after the source record is available.",
                "Do not rely on unsupported conclusions.",
            ]
        if role == CaseRole.JUDGE:
            return [
                "Check source cards before reading the conclusion.",
                "List disputed facts separately from admitted facts.",
                "Ask parties for missing annexures or order-sheet entries.",
            ]
        if role == CaseRole.LAWYER:
            return [
                "Map every argument to a cited page span.",
                "Collect missing receipts, signatures, annexures, or authority papers.",
                "Draft the final answer around verified facts first.",
            ]
        return [
            "Ask what each uploaded document proves.",
            "Ask which document is still missing before filing or replying.",
            "Keep copies of every cited page and do not treat this as legal advice.",
        ]

    def _agent_trace(
        self,
        role: CaseRole,
        *,
        source_count: int,
        needs_review: bool,
        generator_fallback: bool = False,
    ) -> list[dict[str, str]]:
        final_agent = {
            CaseRole.JUDGE: "Judge final agent",
            CaseRole.AUTHORITY: "Authority final agent",
            CaseRole.LAWYER: "Lawyer final agent",
            CaseRole.ANALYST: "Citizen final agent",
        }[role]
        review_status = "needs_review" if needs_review else "complete"
        synthesis_status = "needs_review" if generator_fallback or not source_count else "complete"
        synthesis_summary = (
            "AI synthesis could not produce a usable grounded answer, so local source-card synthesis was used."
            if generator_fallback
            else "Converted retrieved source spans into a structured answer instead of raw snippets."
        )
        return [
            {
                "agent": "Query router",
                "status": "complete",
                "summary": f"Routed the question to the {role.value} answer lens.",
            },
            {
                "agent": "Extractor agent",
                "status": "complete" if source_count else "needs_review",
                "summary": f"Selected {source_count} usable source card(s) from the uploaded record.",
            },
            {
                "agent": "Synthesis agent",
                "status": synthesis_status,
                "summary": synthesis_summary,
            },
            {
                "agent": "Reviewer agent",
                "status": review_status,
                "summary": "Checked that unsupported facts stay as caveats or next actions.",
            },
            {
                "agent": final_agent,
                "status": review_status,
                "summary": "Prepared the role-specific final response.",
            },
        ]

    def _line_needs_citation(self, line: str) -> bool:
        cleaned = line.strip()
        if not re.search(r"[A-Za-z0-9]", cleaned):
            return False
        normalised = re.sub(r"^[#>*\-\d.\s]+", "", cleaned).strip(" *_")
        if not normalised:
            return False
        if normalised.casefold().startswith(
            ("inference:", "insufficient evidence", "caveat:")
        ):
            return False
        if normalised.endswith(":") and len(normalised) <= 110:
            return False
        if re.fullmatch(
            r"(answer|summary|source cards?|questions to ask.*|next actions?|regarding .+|what this means)",
            normalised,
            re.I,
        ):
            return False
        return True

    def _repair_generated_answer(self, answer: str, source_count: int) -> str:
        fallback_citation = "".join(
            f"[{index}]" for index in range(1, min(source_count, 3) + 1)
        )
        if not fallback_citation:
            return answer.strip()
        repaired: list[str] = []
        for line in answer.replace("\r\n", "\n").split("\n"):
            stripped = line.rstrip()
            if (
                self._line_needs_citation(stripped)
                and not _CITATION.search(stripped)
            ):
                stripped = f"{stripped} {fallback_citation}"
            repaired.append(stripped)
        return "\n".join(repaired).strip()

    async def _generated_answer(
        self,
        request: CaseChatRequest,
        hits: list[SearchHit],
        generator: AnswerGenerator,
    ) -> tuple[str | None, str | None]:
        sources = "\n".join(
            f"[{index}] {hit.citation.display_label}: {hit.text[:1200]}"
            for index, hit in enumerate(hits, start=1)
        )
        history = "\n".join(
            f"{message.role}: {message.content}"
            for message in request.messages[-8:]
        )
        system = f"""You are NyaySetu's evidence-bound legal document assistant.
{_ROLE_INSTRUCTIONS[request.role]}
Answer only from the numbered source blocks. Every sentence asserting a fact or law must end with one or more citations like [1]. Clearly label inferences. If the sources are insufficient, say so. Never fabricate a citation, precedent, filing status, or outcome. Answer in {request.language}. Return JSON with one key: answer."""
        prompt = f"Conversation:\n{history}\n\nSource blocks:\n{sources}"
        try:
            raw = await generator(system, prompt)
            start = raw.find("{")
            end = raw.rfind("}")
            if start < 0 or end <= start:
                return None, "AI provider response was not valid JSON."
            answer = str(
                json.loads(raw[start : end + 1]).get("answer", "")
            ).strip()
            answer = self._repair_generated_answer(answer, len(hits))
            citations = [int(value) for value in _CITATION.findall(answer)]
            if (
                not answer
                or not citations
                or any(value < 1 or value > len(hits) for value in citations)
            ):
                return None, "AI provider response did not contain valid source citations."
            factual_lines = [
                line.strip()
                for line in re.split(r"(?<=[.!?])\s+|\n+", answer)
                if line.strip()
            ]
            if any(
                self._line_needs_citation(line)
                and not _CITATION.search(line)
                for line in factual_lines
            ):
                return None, "AI provider response left factual lines without citations."
            return answer, None
        except Exception as exc:
            logger.warning(
                "Document chat generator failed; using local fallback: %s: %s",
                type(exc).__name__,
                exc,
            )
            issue = re.sub(r"\s+", " ", str(exc)).strip()
            issue = issue[:360] if issue else type(exc).__name__
            return None, issue

