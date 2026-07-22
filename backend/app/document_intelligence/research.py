"""Allow-listed legal research agent for document analysis."""

from __future__ import annotations

import hashlib
import re
from urllib.parse import urlparse

from app.config import settings
from app.document_intelligence.models import (
    EvidenceAtom,
    EvidenceKind,
    ResearchFinding,
    ResearchPacket,
)
from app.integrations.indiankanoon import search_indiankanoon
from app.integrations.utils import IntegrationError


_ALLOWED_HOSTS = {"indiankanoon.org", "www.indiankanoon.org"}
_DOCUMENT_PATH = re.compile(r"^/doc/[0-9]+/?$")


def is_allowed_legal_source_url(value: str) -> bool:
    """Return True only for canonical IndianKanoon judgment URLs."""
    parsed = urlparse(value.strip())
    return (
        parsed.scheme == "https"
        and parsed.hostname in _ALLOWED_HOSTS
        and parsed.username is None
        and parsed.password is None
        and bool(_DOCUMENT_PATH.fullmatch(parsed.path))
    )

class ControlledLegalResearchAgent:
    """Uses only the IndianKanoon connector and preserves source URLs."""

    name = "controlled_legal_research"
    version = "1.0.0"

    async def research(self, evidence: list[EvidenceAtom]) -> ResearchPacket:
        query = self._query(evidence)
        if not settings.indiankanoon_api_key:
            return ResearchPacket(
                query=query,
                status="disabled",
                warnings=[
                    "External legal research was requested but INDIANKANOON_API_KEY is not configured."
                ],
            )
        try:
            raw_results = await search_indiankanoon(
                "document_analysis",
                query,
            )
        except IntegrationError as exc:
            return ResearchPacket(
                query=query,
                status="failed",
                warnings=[f"IndianKanoon research failed safely: {exc}"],
            )

        findings: list[ResearchFinding] = []
        skipped = 0
        for result in raw_results:
            source_url = str(result.get("source_url", "")).strip()
            if not is_allowed_legal_source_url(source_url):
                skipped += 1
                continue
            title = re.sub(r"\s+", " ", str(result.get("title", ""))).strip()
            excerpt = re.sub(r"\s+", " ", str(result.get("excerpt", ""))).strip()
            research_id = "research_" + hashlib.sha256(
                f"{source_url}:{title}:{excerpt}".encode("utf-8")
            ).hexdigest()[:24]
            findings.append(
                ResearchFinding(
                    research_id=research_id,
                    title=title or "IndianKanoon result",
                    excerpt=excerpt or "Open the cited judgment to review the relevant passage.",
                    source_url=source_url,
                    citation=str(result.get("citation", "")),
                    court=str(result.get("court", "")),
                    year=str(result.get("year", "")),
                    provider="IndianKanoon",
                )
            )
        warnings = []
        if skipped:
            warnings.append(
                f"{skipped} research result(s) were excluded because no verifiable source URL was returned."
            )
        if not findings:
            warnings.append("No citable IndianKanoon result was returned for the extracted record.")
        return ResearchPacket(
            query=query,
            status="completed",
            findings=findings,
            warnings=warnings,
        )

    @staticmethod
    def _query(evidence: list[EvidenceAtom]) -> str:
        priority = {
            EvidenceKind.LEGAL_PROVISION,
            EvidenceKind.CASE_NUMBER,
            EvidenceKind.COURT,
            EvidenceKind.AUTHORITY,
            EvidenceKind.DOCUMENT_REFERENCE,
        }
        values = [
            item.value
            for item in evidence
            if item.kind in priority
        ][:12]
        if not values:
            values = [item.value for item in evidence[:8]]
        query = " ".join(dict.fromkeys(values))
        return query[:500] or "Indian legal document rights and procedure"

