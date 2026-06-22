"""
app/core/graph.py

LangGraph orchestrator for the NyaySetu multi-agent adversarial loop.
Implements the Intake -> Advocate -> Adversarial -> Mediator -> Filing flow.
Enforces a 2-round hard cap, a 90-second wall-clock timeout, and Postgres checkpointing.
"""

import logging
import asyncio
import time
from typing import Any, cast

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool

from app.core.pubsub import publish
from app.db.neon_client import insert_agent_run
from app.config import settings
from app.agents.state import CaseState
from app.agents.intake import intake_node
from app.agents.advocate import advocate_node
from app.agents.adversarial import adversarial_node
from app.agents.mediator import mediator_node
from app.agents.filing import filing_node
from app.models.case import CaseInput, ClassifiedCase, LegalContext

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Node Functions
# ---------------------------------------------------------------------------
# The intake_node is now imported directly from app.agents.intake


# The advocate_node is now imported directly from app.agents.advocate

# The adversarial_node is now imported directly from app.agents.adversarial

# The mediator_node is now imported directly from app.agents.mediator

# The filing_node is now imported directly from app.agents.filing

# ---------------------------------------------------------------------------
# Routing Logic
# ---------------------------------------------------------------------------

def route_from_mediator(state: CaseState) -> str:
    """
    Evaluates whether to continue the debate or move to filing.
    HARD CAP: debate_round must never exceed 2.
    """
    if state["debate_round"] >= 2:
        logger.info("[graph] Hard cap reached (round >= 2). Routing to Filing.")
        return "Filing"
        
    if state["mediator_score"] >= 8.0:
        logger.info(f"[graph] Draft approved (score {state['mediator_score']:.1f}). Routing to Filing.")
        return "Filing"
        
    logger.info("[graph] Draft needs work. Routing back to Advocate.")
    return "Advocate"

# ---------------------------------------------------------------------------
# Graph Builder
# ---------------------------------------------------------------------------

def build_case_graph(checkpointer=None):
    builder = StateGraph(CaseState)
    
    builder.add_node("Intake", intake_node)
    builder.add_node("Advocate", advocate_node)
    builder.add_node("Adversarial", adversarial_node)
    builder.add_node("Mediator", mediator_node)
    builder.add_node("Filing", filing_node)
    
    builder.add_edge(START, "Intake")
    builder.add_edge("Intake", "Advocate")
    builder.add_edge("Advocate", "Adversarial")
    builder.add_edge("Adversarial", "Mediator")
    
    builder.add_conditional_edges(
        "Mediator",
        route_from_mediator,
        {"Advocate": "Advocate", "Filing": "Filing"}
    )
    
    builder.add_edge("Filing", END)
    
    return builder.compile(checkpointer=checkpointer)

# ---------------------------------------------------------------------------
# Public Invocation
# ---------------------------------------------------------------------------

async def run_case(case_id: str, raw_input: str) -> CaseState:
    """
    Executes the multi-agent orchestration for a given case input.
    Wraps the LangGraph invocation in a strict 90-second wall-clock timeout.
    """
    # 1. Setup Postgres Checkpointer using psycopg_pool
    # Neon allows standard postgres connection strings. We use the existing DATABASE_URL.
    db_uri = settings.database_url
    
    # We must enforce the timeout.
    timeout_seconds = 90.0
    
    initial_state: CaseState = {
        "case_id": case_id,
        "raw_input": raw_input,
        "detected_language": "en",
        "case_type": "other",
        "classification_confidence": 0.0,
        "advocate_draft": "",
        "adversarial_critique": [],
        "debate_round": 0,
        "mediator_score": 0.0,
        "mediator_annotations": [],
        "final_document": None,
        "filing_status": "pending",
        "timestamps": {"run_start": time.time()}
    }
    
    config = {"configurable": {"thread_id": case_id}}
    
    try:
        async with AsyncConnectionPool(conninfo=db_uri, max_size=5) as pool:
            checkpointer = AsyncPostgresSaver(pool)
            await checkpointer.setup()
            
            graph = build_case_graph(checkpointer=checkpointer)
            
            logger.info(f"Starting case {case_id} with 90s timeout.")
            
            async def run_stream():
                current_state = initial_state
                async for state_update in graph.astream(initial_state, config=config):
                    for node_name, partial_state in state_update.items():
                        # Push to pubsub
                        await publish(case_id, {
                            "agent": node_name,
                            "status": f"Agent {node_name} completed processing.",
                            "delta": partial_state
                        })
                        
                        # Save to agent_runs for the UI to replay
                        round_num = partial_state.get("debate_round", current_state.get("debate_round", 0))
                        score = partial_state.get("mediator_score")
                        input_sum = f"Processed state for case_id={case_id}"
                        output_sum = str({k: v for k, v in partial_state.items() if k not in ["advocate_draft", "timestamps"]})
                        
                        if settings.database_url:
                            asyncio.create_task(insert_agent_run(
                                case_id=case_id,
                                agent_name=node_name,
                                round_number=round_num,
                                input_summary=input_sum,
                                output_summary=output_sum,
                                score=score
                            ))
                            
                        current_state.update(partial_state)
                await publish(case_id, {"agent": "System", "status": "completed", "delta": {}})
                return current_state
            
            final_state = await asyncio.wait_for(
                run_stream(),
                timeout=timeout_seconds
            )
            return cast(CaseState, final_state)
            
    except asyncio.TimeoutError:
        logger.warning(f"Case {case_id} exceeded 90s timeout. Forcing fallback to Filing.")
        
        # On timeout, we must route straight to Filing with whatever draft exists.
        # We can extract the latest state from the checkpointer if we instantiated it outside,
        # but since the pool closed, we just use the initial_state mutated by reference if possible,
        # or we return a patched fallback state.
        
        fallback_state = initial_state.copy()
        fallback_state["filing_status"] = "timeout_fallback"
        fallback_state["final_document"] = {
            "status": "filed_with_gaps",
            "document_body": fallback_state.get("advocate_draft", "No draft completed.") + "\n\n[timeout fallback — unresolved gaps may remain.]"
        }
        fallback_state["timestamps"]["run_end"] = time.time()
        return cast(CaseState, fallback_state)
    except Exception as e:
        logger.error(f"Error in run_case for {case_id}: {e}", exc_info=True)
        initial_state["filing_status"] = "error"
        return initial_state
