"""
app/agents/advocate.py

Advocate Agent Node for the LangGraph Orchestrator.
Responsibilities:
- Consults IndianKanoon API for relevant laws/precedents.
- Builds a structured petition draft via AI router.
- Format: TO / SUBJECT / applicant submits...
- Explicitly addresses adversarial_critique on debate rounds > 0.
"""

import json
import logging
import time

from app.agents.state import CaseState
from app.integrations.indiankanoon import search_indiankanoon, get_fallback_provisions
from app.integrations.utils import IntegrationError
from app.core.ai_router import call_with_fallback

logger = logging.getLogger(__name__)

_DRAFT_SYSTEM_PROMPT = """
You are an expert Advocate practicing in the Indian justice system.
Your task is to draft a formal legal petition/complaint based on the citizen's intake facts.

Follow this exact structure:
TO
[Appropriate Authority]
[District, State]

SUBJECT: [Clear Subject Line specifying the main grievance and law]

RESPECTED SIR/MADAM,
The applicant most humbly submits as under:
1. [Facts section...]
2. [Specific law being invoked...]
3. [Relief sought...]

Make it professional, crisp, and legally sound. Use the provided IndianKanoon precedents to cite exact laws.

Respond ONLY with valid JSON in this exact schema:
{
  "draft": "<The complete structured text of the petition>",
  "revision_notes": ""
}
No markdown formatting or preamble.
"""

_REVISION_SYSTEM_PROMPT = """
You are an expert Advocate practicing in the Indian justice system.
You have drafted a petition, but an adversarial Magistrate/Bureaucrat has raised critiques.
You MUST revise your draft to explicitly address EVERY critique point raised.

Critiques:
{critiques}

Follow the exact same structure as before:
TO ... SUBJECT ... FACTS ... RELIEF.

Respond ONLY with valid JSON in this exact schema:
{
  "draft": "<The complete REVISED structured text of the petition>",
  "revision_notes": "<Explicitly list how you addressed each critique point in this revision>"
}
No markdown formatting or preamble.
"""

async def advocate_node(state: CaseState) -> dict:
    """
    LangGraph node for the Advocate Agent.
    """
    t0 = time.perf_counter()
    
    timestamps = state.get("timestamps", {})
    round_num = state.get("debate_round", 0)
    timestamps[f"advocate_start_r{round_num}"] = t0
    
    case_type = state.get("case_type", "other")
    raw_input = state.get("raw_input", "")
    
    # 1. Fetch IndianKanoon precedents
    try:
        precedents = await search_indiankanoon(case_type, raw_input)
    except IntegrationError as e:
        logger.warning(f"[advocate] IndianKanoon API failed: {e}. Using fallback.")
        precedents = get_fallback_provisions(case_type)
        
    precedent_text = "\n".join([f"- {p['title']}: {p['excerpt']}" for p in precedents])
    
    # 2. Build the LLM prompt based on round
    if round_num == 0:
        system_prompt = _DRAFT_SYSTEM_PROMPT
        user_prompt = (
            f"Case Type: {case_type}\n\n"
            f"Citizen's Facts:\n{raw_input}\n\n"
            f"Relevant Law / Precedents from IndianKanoon:\n{precedent_text}\n\n"
            f"Draft the petition."
        )
    else:
        # Revision mode
        critiques = "\n".join(state.get("adversarial_critique", []))
        system_prompt = _REVISION_SYSTEM_PROMPT.format(critiques=critiques)
        user_prompt = (
            f"Case Type: {case_type}\n\n"
            f"Previous Draft:\n{state.get('advocate_draft', '')}\n\n"
            f"Relevant Law / Precedents from IndianKanoon:\n{precedent_text}\n\n"
            f"Revise the petition to address the critiques."
        )
        
    # 3. Call AI Router
    try:
        response_text, provider = await call_with_fallback(
            prompt=user_prompt,
            preferred="gemini", # Default to free tier for drafting
            system=system_prompt,
            max_tokens=2000
        )
        
        # Clean markdown fences if present
        clean = response_text.replace("```json", "").replace("```", "").strip()
        data = json.loads(clean)
        
        new_draft = data.get("draft", state.get("advocate_draft", ""))
        revision_notes = data.get("revision_notes", "")
        
        logger.info(f"[advocate] Draft completed successfully. Provider: {provider}. Round: {round_num}")
        
    except Exception as e:
        logger.error(f"[advocate] LLM drafting failed: {e}")
        # Fallback to minimal draft
        new_draft = state.get("advocate_draft", f"TO\nAuthority\n\nSUBJECT: Grievance\n\nFacts: {raw_input}\n\nRelief sought.")
        revision_notes = "Failed to revise."
        
    timestamps[f"advocate_end_r{round_num}"] = time.perf_counter()
    
    return {
        "advocate_draft": new_draft,
        "timestamps": timestamps,
        "revision_notes": revision_notes
    }
