"""
app/agents/debate_graph.py

LangGraph 1.2 adversarial debate orchestration — the technical core of NyaySetu.

Architecture:
  advocate → bureaucrat → mediator
       ↑_________________________|  (conditional: max 2 rounds)
                                  → filing → ai_enrich → END

Hard safety limits baked into graph state:
  - round_number >= 2  → mediator override (force filing)
  - wall-clock > 90s   → timeout override (force filing)
  - objections == []   → clean draft (proceed to filing)

Checkpoint: AsyncPostgresSaver (Neon DB) — crash-safe, resumable, time-travelable.
"""

from __future__ import annotations

import logging
import time
import operator
from typing import Annotated, Callable, Awaitable, TypedDict, Any

from langgraph.graph import StateGraph, START, END

from app.models.case import ClassifiedCase, LegalContext
from app.models.document import DebateRound, LegalDocument
from app.core.document_builder import build_initial_document
from app.agents.advocate_agent import run_advocate_agent
from app.agents.bureaucrat_agent import run_bureaucrat_agent
from app.agents.mediator_agent import run_mediator_agent
from app.agents.filing_agent import run_filing_agent

logger = logging.getLogger(__name__)

AiRouterFn = Callable[[str, str], Awaitable[tuple[str, str]]]


# ---------------------------------------------------------------------------
# LangGraph DebateState
# ---------------------------------------------------------------------------


class DebateState(TypedDict):
    classified_case: ClassifiedCase
    legal_context: LegalContext
    current_draft: str
    # Annotated[list, operator.add] — rounds ACCUMULATE across nodes (don't overwrite)
    debate_rounds: Annotated[list[DebateRound], operator.add]
    round_number: int          # HARD CAP: must not exceed 2
    objections: list[str]
    final_document: LegalDocument | None
    start_time: float          # wall-clock timeout reference
    tier: str
    provider_used: str         # tracks which AI provider was last used
    session_id: str


# ---------------------------------------------------------------------------
# Conditional edge — THE safety mechanism
# ---------------------------------------------------------------------------


def should_continue_debate(state: DebateState) -> str:
    """
    Called after every mediator node execution.
    Returns the name of the next node.

    Priority order (first match wins):
    1. round_number >= 2 → mediator override → filing
    2. elapsed > 90s     → timeout override  → filing
    3. objections == []  → clean draft       → filing
    4. else              → patch round       → advocate
    """
    elapsed = time.time() - state["start_time"]

    if state["round_number"] >= 2:
        logger.info(
            "[debate_graph] MEDIATOR OVERRIDE — round cap reached (round=%d)",
            state["round_number"],
        )
        return "filing"

    if elapsed > 90.0:
        logger.info(
            "[debate_graph] TIMEOUT OVERRIDE — %.1fs elapsed (limit=90s)",
            elapsed,
        )
        return "filing"

    if not state["objections"]:
        logger.info("[debate_graph] clean draft — no objections → filing")
        return "filing"

    logger.info(
        "[debate_graph] continuing debate | round=%d objections=%d elapsed=%.1fs",
        state["round_number"],
        len(state["objections"]),
        elapsed,
    )
    return "advocate"


# ---------------------------------------------------------------------------
# Graph node builders — take ai_router_fn via closure
# ---------------------------------------------------------------------------


def make_advocate_node(ai_router_fn: AiRouterFn):
    async def advocate_node(state: DebateState) -> dict:
        t0 = time.perf_counter()
        logger.info("[advocate_node] entry | round=%d", state["round_number"])
        draft = await run_advocate_agent(
            classified=state["classified_case"],
            legal_context=state["legal_context"],
            ai_router_fn=ai_router_fn,
            use_ai=True,
        )
        logger.info("[advocate_node] exit | %.0fms", (time.perf_counter() - t0) * 1000)
        return {"current_draft": draft}

    return advocate_node


def make_bureaucrat_node(ai_router_fn: AiRouterFn):
    async def bureaucrat_node(state: DebateState) -> dict:
        t0 = time.perf_counter()
        logger.info("[bureaucrat_node] entry | round=%d", state["round_number"])
        objections = await run_bureaucrat_agent(
            draft=state["current_draft"],
            classified=state["classified_case"],
            legal_context=state["legal_context"],
            ai_router_fn=ai_router_fn,
        )
        logger.info(
            "[bureaucrat_node] exit | objections=%d %.0fms",
            len(objections),
            (time.perf_counter() - t0) * 1000,
        )
        return {"objections": objections}

    return bureaucrat_node


def make_mediator_node(ai_router_fn: AiRouterFn):
    async def mediator_node(state: DebateState) -> dict:
        t0 = time.perf_counter()
        round_num = state["round_number"] + 1  # increment here (atomic)
        logger.info("[mediator_node] entry | completing round=%d", round_num)

        patched_draft, unresolved, patch_applied = await run_mediator_agent(
            draft=state["current_draft"],
            objections=state["objections"],
            classified=state["classified_case"],
            ai_router_fn=ai_router_fn,
        )

        # Record this debate round for the AgentTraceLog on frontend
        round_record = DebateRound(
            round_number=round_num,
            advocate_draft=state["current_draft"],
            advocate_points=[],   # evidentiary points tracked in advocate_agent
            bureaucrat_objections=state["objections"],
            objection_severity=[
                "critical" if "missing" in o.lower() else "moderate"
                for o in state["objections"]
            ],
            mediator_verdict=(
                f"Resolved {len(state['objections']) - len(unresolved)} objection(s). "
                f"{len(unresolved)} require user input."
            ),
            patch_applied=patch_applied,
            patched_draft=patched_draft if patch_applied else "",
        )

        logger.info(
            "[mediator_node] exit | round=%d patch=%s unresolved=%d %.0fms",
            round_num,
            patch_applied,
            len(unresolved),
            (time.perf_counter() - t0) * 1000,
        )

        return {
            "current_draft": patched_draft,
            "debate_rounds": [round_record],   # operator.add accumulates this
            "round_number": round_num,
            "objections": unresolved,          # only unresolved carry forward
        }

    return mediator_node


def make_filing_node():
    async def filing_node(state: DebateState) -> dict:
        t0 = time.perf_counter()
        logger.info("[filing_node] entry | rounds=%d", state["round_number"])

        mediator_override = state["round_number"] >= 2
        elapsed = time.time() - state["start_time"]
        if elapsed > 90.0:
            mediator_override = True

        document = run_filing_agent(
            final_draft=state["current_draft"],
            classified=state["classified_case"],
            legal_context=state["legal_context"],
            debate_rounds=state["debate_rounds"],
            unresolved_objections=state["objections"],
            mediator_override=mediator_override,
            session_id=state.get("session_id", ""),
            tier=state["tier"],
            provider_used=state.get("provider_used", ""),
        )

        logger.info(
            "[filing_node] exit | status=%s confidence=%.2f %.0fms",
            document.status,
            document.confidence_score,
            (time.perf_counter() - t0) * 1000,
        )
        return {"final_document": document}

    return filing_node


def make_ai_enrich_node(ai_router_fn: AiRouterFn):
    """
    Fills AI-generated fields: summary, summary_hindi, filing_instructions_hindi,
    next_steps, lawyer_note (premium only).
    """
    async def ai_enrich_node(state: DebateState) -> dict:
        from app.core.ai_router import generate_document_summary

        doc = state["final_document"]
        if doc is None:
            return {}

        t0 = time.perf_counter()
        logger.info("[ai_enrich_node] entry | tier=%s", state["tier"])

        try:
            enrichment = await generate_document_summary(
                document=doc,
                classified=state["classified_case"],
                tier=state["tier"],
                ai_router_fn=ai_router_fn,
            )
            updated_doc = doc.model_copy(update=enrichment)
            logger.info(
                "[ai_enrich_node] exit | %.0fms",
                (time.perf_counter() - t0) * 1000,
            )
            return {"final_document": updated_doc}
        except Exception as exc:
            logger.warning("[ai_enrich_node] enrichment failed (%s) — using unenriched doc", exc)
            return {}

    return ai_enrich_node


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------


def build_graph(ai_router_fn: AiRouterFn, checkpointer=None) -> Any:
    """
    Builds and compiles the LangGraph StateGraph.

    checkpointer: pass an AsyncPostgresSaver instance for crash-safe execution.
                  If None, uses in-memory (suitable for tests / local dev).
    """
    builder = StateGraph(DebateState)

    # Register nodes
    builder.add_node("advocate", make_advocate_node(ai_router_fn))
    builder.add_node("bureaucrat", make_bureaucrat_node(ai_router_fn))
    builder.add_node("mediator", make_mediator_node(ai_router_fn))
    builder.add_node("filing", make_filing_node())
    builder.add_node("ai_enrich", make_ai_enrich_node(ai_router_fn))

    # Edges
    builder.add_edge(START, "advocate")
    builder.add_edge("advocate", "bureaucrat")
    builder.add_edge("bureaucrat", "mediator")
    builder.add_conditional_edges(
        "mediator",
        should_continue_debate,
        {"advocate": "advocate", "filing": "filing"},
    )
    builder.add_edge("filing", "ai_enrich")
    builder.add_edge("ai_enrich", END)

    return builder.compile(checkpointer=checkpointer)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def run_debate(
    classified: ClassifiedCase,
    legal_context: LegalContext,
    tier: str,
    ai_router_fn: AiRouterFn,
    session_id: str = "",
    checkpointer=None,
) -> LegalDocument:
    """
    Main entry point called from app/api/analyze.py.

    1. Builds the initial document deterministically
    2. Creates the LangGraph initial state
    3. Runs the graph (with optional Postgres checkpointer for crash safety)
    4. Returns the final LegalDocument

    session_id: used as LangGraph thread_id for checkpoint resumption.
    checkpointer: AsyncPostgresSaver instance (None = in-memory, for local/test).
    """
    initial_draft = build_initial_document(
        classified.case_type,
        classified.extracted_entities,
        legal_context,
        user_name=classified.user_name,
        user_location=classified.user_location,
    )

    initial_state: DebateState = {
        "classified_case": classified,
        "legal_context": legal_context,
        "current_draft": initial_draft,
        "debate_rounds": [],
        "round_number": 0,
        "objections": [],
        "final_document": None,
        "start_time": time.time(),
        "tier": tier,
        "provider_used": "",
        "session_id": session_id,
    }

    graph = build_graph(ai_router_fn, checkpointer=checkpointer)

    config: dict = {}
    if session_id:
        config = {"configurable": {"thread_id": session_id}}

    logger.info(
        "[run_debate] starting | case=%s tier=%s session=%s",
        classified.case_type,
        tier,
        session_id or "anonymous",
    )

    t0 = time.perf_counter()
    final_state = await graph.ainvoke(initial_state, config=config)
    elapsed_ms = int((time.perf_counter() - t0) * 1000)

    doc: LegalDocument | None = final_state.get("final_document")
    if doc is None:
        logger.error("[run_debate] final_document is None — graph did not complete")
        raise RuntimeError("Debate graph did not produce a final document")

    # Attach processing time
    doc = doc.model_copy(update={"processing_time_ms": elapsed_ms})

    logger.info(
        "[run_debate] complete | status=%s rounds=%d time=%dms",
        doc.status,
        doc.total_rounds,
        elapsed_ms,
    )
    return doc
