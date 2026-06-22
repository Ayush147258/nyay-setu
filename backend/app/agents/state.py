"""
app/agents/state.py

Defines the shared state object that flows through all 5 agents
in the NyaySetu LangGraph orchestration loop.
"""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict, Any

class CaseState(TypedDict):
    """
    Shared state object flowing through the Intake -> Advocate -> Adversarial -> Mediator -> Filing graph.
    """
    case_id: str
    raw_input: str
    detected_language: str
    case_type: str
    classification_confidence: float
    
    # Added per Prompt 3 requirements
    clarifying_question: str | None
    
    advocate_draft: str
    # Accumulated across rounds: one critique string per round
    adversarial_critique: Annotated[list[str], operator.add]
    
    debate_round: int
    mediator_score: float
    # Accumulated across rounds: one annotation set per round
    mediator_annotations: Annotated[list[str], operator.add]
    
    final_document: Any
    filing_status: str
    
    # Tracking execution times per agent node
    timestamps: dict[str, float]
    
    # Private internal fields for agents
    _legal_provision: str
    _classified_case: Any
    _legal_context: Any
    _objections: Any

    revision_notes: str
