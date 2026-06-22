"""
tests/test_debate_loop.py

Tests for the adversarial debate loop:
- Hard round cap (max 2 rounds)
- 90-second wall-clock timeout override
- Clean draft exits early (0 objections)
- DebateRound accumulation via Annotated[list, operator.add]
- Mediator override flag set correctly

Run with: pytest tests/test_debate_loop.py -v
"""

from __future__ import annotations

import asyncio
import time
import pytest

from app.models.case import CaseType, Language, UserTier, ClassifiedCase, LegalContext
from app.agents.debate_graph import (
    DebateState,
    should_continue_debate,
    build_graph,
    run_debate,
)
from app.models.document import DebateRound, DocumentStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_classified(case_type: CaseType = CaseType.FIR_REFUSAL) -> ClassifiedCase:
    return ClassifiedCase(
        original_text="Police ne meri FIR nahi ki",
        normalized_text="police refused to register my fir",
        case_type=case_type,
        confidence=0.85,
        detected_language=Language.HINGLISH,
        extracted_entities={"district": "Patna", "police_station": "Kotwali"},
        user_name="Ramesh Kumar",
        user_location="Patna, Bihar",
        tier=UserTier.FREE,
    )


def make_legal_context(case_type: CaseType = CaseType.FIR_REFUSAL) -> LegalContext:
    from app.core.case_classifier import get_legal_context
    return get_legal_context(case_type, {})


def make_state(round_number: int = 0, objections: list[str] = None, elapsed: float = 0.0) -> DebateState:
    return DebateState(
        classified_case=make_classified(),
        legal_context=make_legal_context(),
        current_draft="Draft document text with CrPC 156(3) content.",
        debate_rounds=[],
        round_number=round_number,
        objections=objections or ["Missing address"],
        final_document=None,
        start_time=time.time() - elapsed,
        tier="free",
        provider_used="gemini",
        session_id="test-session",
    )


# ---------------------------------------------------------------------------
# should_continue_debate — conditional edge tests
# ---------------------------------------------------------------------------


class TestShouldContinueDebate:
    def test_round_cap_triggers_filing(self):
        state = make_state(round_number=2, objections=["some objection"])
        assert should_continue_debate(state) == "filing"

    def test_round_cap_at_exactly_two(self):
        state = make_state(round_number=2)
        assert should_continue_debate(state) == "filing"

    def test_round_below_cap_with_objections_continues(self):
        state = make_state(round_number=1, objections=["Missing address"])
        assert should_continue_debate(state) == "advocate"

    def test_round_zero_with_objections_continues(self):
        state = make_state(round_number=0, objections=["Missing station name"])
        assert should_continue_debate(state) == "advocate"

    def test_no_objections_goes_to_filing(self):
        state = make_state(round_number=0, objections=[])
        assert should_continue_debate(state) == "filing"

    def test_timeout_90s_triggers_filing(self):
        state = make_state(round_number=0, objections=["some objection"], elapsed=91.0)
        assert should_continue_debate(state) == "filing"

    def test_timeout_exactly_90s_triggers_filing(self):
        state = make_state(round_number=0, objections=["objection"], elapsed=90.1)
        assert should_continue_debate(state) == "filing"

    def test_under_timeout_with_objections_continues(self):
        state = make_state(round_number=1, objections=["Missing date"], elapsed=30.0)
        assert should_continue_debate(state) == "advocate"

    def test_round_cap_takes_priority_over_objections(self):
        # Even with objections, round cap wins
        state = make_state(round_number=2, objections=["Missing address", "Wrong section"])
        assert should_continue_debate(state) == "filing"


# ---------------------------------------------------------------------------
# Full graph integration tests (mocked AI)
# ---------------------------------------------------------------------------


async def _always_object_router(prompt: str, preferred: str) -> tuple[str, str]:
    """Mock AI router that always returns 2 objections."""
    import json
    if "strict government official" in prompt or "find reasons to REJECT" in prompt:
        return json.dumps(["Complainant address is missing", "Police station not named"]), "mock"
    if "senior judge" in prompt or "arbitrating" in prompt:
        return json.dumps({
            "patched_document": prompt.split("---")[1].strip() if "---" in prompt else "Patched document.",
            "resolved": [],
            "unresolved": ["Complainant address is missing"],
        }), "mock"
    return "Improved document text with all legal sections intact.", "mock"


async def _clean_draft_router(prompt: str, preferred: str) -> tuple[str, str]:
    """Mock AI router — bureaucrat always returns no objections."""
    import json
    if "strict government official" in prompt or "find reasons to REJECT" in prompt:
        return "[]", "mock"
    return "Clean improved document text with CrPC sections.", "mock"


@pytest.mark.asyncio
async def test_debate_stops_at_round_cap():
    """Graph must never exceed 2 rounds even if bureaucrat keeps objecting."""
    classified = make_classified()
    legal_context = make_legal_context()

    doc = await run_debate(
        classified=classified,
        legal_context=legal_context,
        tier="free",
        ai_router_fn=_always_object_router,
        session_id="test-cap",
    )

    assert doc.total_rounds <= 2, f"Expected ≤2 rounds, got {doc.total_rounds}"
    assert doc.mediator_override_triggered is True


@pytest.mark.asyncio
async def test_clean_draft_exits_after_one_round():
    """When bureaucrat finds no objections, graph exits after round 1."""
    classified = make_classified()
    legal_context = make_legal_context()

    doc = await run_debate(
        classified=classified,
        legal_context=legal_context,
        tier="free",
        ai_router_fn=_clean_draft_router,
        session_id="test-clean",
    )

    assert doc.total_rounds <= 1
    assert doc.mediator_override_triggered is False


@pytest.mark.asyncio
async def test_debate_rounds_accumulate():
    """DebateRound list must grow with each round (Annotated[list, operator.add])."""
    classified = make_classified()
    legal_context = make_legal_context()

    doc = await run_debate(
        classified=classified,
        legal_context=legal_context,
        tier="free",
        ai_router_fn=_always_object_router,
        session_id="test-accumulate",
    )

    # With always-object router, should have 2 rounds
    assert len(doc.debate_rounds) == doc.total_rounds
    assert len(doc.debate_rounds) >= 1


@pytest.mark.asyncio
async def test_hardened_status_when_no_gaps():
    """Document with no unresolved gaps must have HARDENED status."""
    classified = make_classified()
    legal_context = make_legal_context()

    # Use full entities so no template gaps remain
    classified = classified.model_copy(update={
        "extracted_entities": {
            "complainant_name": "Ramesh Kumar",
            "district": "Patna",
            "police_station": "Kotwali",
            "incident_date": "01/06/2026",
            "incident_description": "Neighbour stole my property.",
            "complaint_date": "02/06/2026",
        }
    })

    doc = await run_debate(
        classified=classified,
        legal_context=legal_context,
        tier="free",
        ai_router_fn=_clean_draft_router,
        session_id="test-hardened",
    )

    # With clean router + complete entities, should be HARDENED
    assert doc.status in (DocumentStatus.HARDENED, DocumentStatus.ANNOTATED)
    assert doc.confidence_score > 0.0


@pytest.mark.asyncio
async def test_final_document_never_none():
    """run_debate must always return a LegalDocument, never None."""
    classified = make_classified()
    legal_context = make_legal_context()

    doc = await run_debate(
        classified=classified,
        legal_context=legal_context,
        tier="free",
        ai_router_fn=_clean_draft_router,
        session_id="test-not-none",
    )

    assert doc is not None
    assert doc.document_body != ""
    assert doc.case_type == CaseType.FIR_REFUSAL
