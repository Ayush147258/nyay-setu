"""
app/agents/mediator.py

Mediator Agent Node for LangGraph Orchestrator.
Scores the Advocate's draft against the Adversarial critiques using a strict rubric.
Appends unresolved blocking issues as explicit caveats to the final document if forced to approve at the round cap.
"""

import json
import logging
import time

from app.agents.state import CaseState
from app.core.ai_router import call_with_fallback

logger = logging.getLogger(__name__)

_MEDIATOR_SYSTEM_PROMPT = """
You are an impartial Senior Judge presiding over a draft petition.
You have the Advocate's latest draft and the Opposing Counsel/Clerk's critiques.

Your task is to SCORE the draft objectively against the critiques using this rubric:
1. Completeness (0-10): Are all necessary facts, dates, and amounts explicitly stated?
2. Legal Accuracy (0-10): Are the correct sections/laws invoked based on the facts?
3. Procedural Correctness (0-10): Is jurisdiction correct and are all procedural prerequisites (like prior notices or forms) addressed?

Also, identify any "blocking" critiques that remain COMPLETELY UNRESOLVED in the current draft.

Respond ONLY with valid JSON in this exact schema:
{
  "scores": {
    "completeness": 8,
    "legal_accuracy": 9,
    "procedural_correctness": 7
  },
  "unresolved_blocking_issues": [
    "The applicant did not mention submitting a prior police complaint under 154(1) CrPC."
  ]
}

If all blocking issues have been adequately addressed or mitigated, the list should be empty.
Do not use markdown fences. Return ONLY raw JSON.
"""

async def mediator_node(state: CaseState) -> dict:
    """
    LangGraph node for the Mediator Agent.
    """
    t0 = time.perf_counter()
    
    round_num = state.get("debate_round", 0)
    timestamps = state.get("timestamps", {})
    timestamps[f"mediator_start_r{round_num}"] = t0
    
    draft = state.get("advocate_draft", "")
    critiques = state.get("adversarial_critique", [])
    latest_critique = critiques[-1] if critiques else "[]"
    
    user_prompt = (
        f"Latest Advocate Draft:\n{draft}\n\n"
        f"Adversarial Critiques to address:\n{latest_critique}\n\n"
        f"Score the draft and list unresolved blocking issues."
    )
    
    try:
        response_text, provider = await call_with_fallback(
            prompt=user_prompt,
            preferred="gemini", # Standard free tier for evaluation
            system=_MEDIATOR_SYSTEM_PROMPT,
            max_tokens=600
        )
        
        clean = response_text.replace("```json", "").replace("```", "").strip()
        data = json.loads(clean)
        
        scores = data.get("scores", {})
        c_score = float(scores.get("completeness", 0))
        l_score = float(scores.get("legal_accuracy", 0))
        p_score = float(scores.get("procedural_correctness", 0))
        
        overall_score = (c_score + l_score + p_score) / 3.0
        unresolved = data.get("unresolved_blocking_issues", [])
        
    except Exception as e:
        logger.error(f"[mediator] Scoring failed: {e}")
        overall_score = 5.0
        unresolved = ["Unable to automatically verify procedural compliance due to system error."]
        
    THRESHOLD = 8.0
    will_approve = (overall_score >= THRESHOLD) or (round_num >= 2)
    
    hardened_draft = draft
    annotations = []
    
    # "No blind confidence" principle implementation
    if will_approve and unresolved:
        caveat_text = "\n\n" + "="*40 + "\n"
        caveat_text += "SYSTEM CAVEATS & UNRESOLVED ISSUES\n"
        caveat_text += "="*40 + "\n"
        caveat_text += "The following critical issues could not be independently verified or resolved by the system. "
        caveat_text += "You must manually ensure these are addressed before filing:\n"
        for i, issue in enumerate(unresolved, 1):
            caveat_text += f"{i}. {issue}\n"
            annotations.append(f"Unresolved: {issue}")
            
        hardened_draft += caveat_text
    
    if not unresolved:
        annotations.append("All blocking issues resolved.")
        
    timestamps[f"mediator_end_r{round_num}"] = time.perf_counter()
    
    logger.info(f"[mediator] Round {round_num} | Score: {overall_score:.1f} | Unresolved: {len(unresolved)}")
    
    # The graph routes from this score. It relies on the updated debate_round.
    return {
        "advocate_draft": hardened_draft,
        "mediator_score": overall_score,
        "mediator_annotations": [f"Round {round_num} Score: {overall_score:.1f}. " + " | ".join(annotations)],
        "debate_round": round_num + 1,
        "timestamps": timestamps
    }
