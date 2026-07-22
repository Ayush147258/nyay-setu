"""Case-isolated lexical retrieval with citation-ready source spans.

The production schema supports PostgreSQL full-text plus pgvector. This local
implementation is the deterministic keyword side and remains useful as the
fallback when an embedding provider or vector index is unavailable.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict

from app.document_intelligence.models import (
    Citation,
    DocumentBlock,
    DocumentIR,
    ParseStatus,
    SearchHit,
    SourceSpan,
)


_TOKEN = re.compile(r"\w{2,}", re.UNICODE)


def _tokens(text: str) -> list[str]:
    return [token.casefold() for token in _TOKEN.findall(text)]


class CaseRetriever:
    """Small-corpus BM25 retriever that never crosses a case boundary."""

    def search(self, documents: list[DocumentIR], query: str, limit: int = 8) -> list[SearchHit]:
        case_ids = {document.case_id for document in documents}
        if len(case_ids) > 1:
            raise ValueError("Retriever input must be isolated to one case")
        blocks: list[tuple[DocumentIR, DocumentBlock]] = [
            (document, block)
            for document in documents
            if document.status in {ParseStatus.READY, ParseStatus.PARTIAL}
            for page in document.pages
            for block in page.blocks
            if block.text.strip()
        ]
        query_terms = _tokens(query)
        if not blocks or not query_terms:
            return []

        tokenized = [_tokens(block.text) for _, block in blocks]
        document_frequency: Counter[str] = Counter()
        for terms in tokenized:
            document_frequency.update(set(terms))
        average_length = sum(len(terms) for terms in tokenized) / len(tokenized)
        scores: list[tuple[float, int]] = []
        query_counts = Counter(query_terms)
        for index, terms in enumerate(tokenized):
            frequencies = Counter(terms)
            score = 0.0
            for term, query_frequency in query_counts.items():
                frequency = frequencies[term]
                if not frequency:
                    continue
                inverse_frequency = math.log(
                    1 + (len(blocks) - document_frequency[term] + 0.5) / (document_frequency[term] + 0.5)
                )
                denominator = frequency + 1.2 * (1 - 0.75 + 0.75 * len(terms) / max(average_length, 1))
                score += inverse_frequency * ((frequency * 2.2) / denominator) * query_frequency
            if query.casefold() in blocks[index][1].text.casefold():
                score += 2.0
            if score > 0:
                scores.append((score, index))
        scores.sort(reverse=True)

        hits: list[SearchHit] = []
        for score, index in scores[:limit]:
            document, block = blocks[index]
            source_span = SourceSpan(
                document_id=document.document_id,
                version_id=document.version_id,
                page_number=block.page_number,
                block_id=block.block_id,
                start_char=0,
                end_char=min(len(block.text), 4000),
                exact_quote=block.text[:4000],
                bbox=block.bbox,
            )
            citation = Citation(
                citation_id=f"cite_{block.block_id}",
                evidence_id=f"source_{block.block_id}",
                source_span=source_span,
                display_label=f"{document.original_name}, page {block.page_number}",
            )
            hits.append(SearchHit(score=round(score, 6), text=block.text, citation=citation))
        return hits

