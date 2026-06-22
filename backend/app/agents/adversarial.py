"""
app/agents/adversarial.py

Adversarial Agent Node for LangGraph Orchestrator.
Simulates a skeptical bureaucrat or opposing counsel reviewing the draft petition.
Highlights defects that lead to real-world rejections at the filing counter.
Always outputs at least one critique in round 0 to ensure the adversarial loop functions.
"""

import json
import logging
import time

from app.agents.state import CaseState
from app.core.ai_router import call_with_fallback

logger = logging.getLogger(__name__)

# Reference table of real rejection patterns based on common procedural defects 
# frequently cited in Indian High Court guidelines and District Court filing counter circulars.
_REJECTION_PATTERNS = {
    "fir_not_registered": [
        "Failure to enclose proof of prior complaint to Police Station under Section 154(1) CrPC.",
        "Failure to enclose proof of dispatch of complaint to Superintendent of Police under Section 154(3) CrPC before approaching Magistrate under 156(3).",
        "Missing date and time of the incident or delay not explained."
    ],
    "domestic_violence": [
        "Failure to specify the exact nature of domestic relationship.",
        "Not enclosing the Domestic Incident Report (DIR) or failing to mention whether Protection Officer was approached.",
        "Reliefs sought under Section 18, 19, 20 are mixed without specific itemization."
    ],
    "land_dispute": [
        "Failure to explicitly state that breach of peace is imminent (essential for Sec 144/145 CrPC).",
        "Missing specific boundaries/khasra numbers of the disputed land.",
        "Not attaching latest Jamabandi / revenue record."
    ],
    "consumer_complaint": [
        "Failure to quantify the compensation sought accurately, affecting pecuniary jurisdiction.",
        "Missing proof of serving legal notice to the opposite party before filing.",
        "Cause of action date not clearly established (limitation is 2 years)."
    ],
    "cyber_fraud": [
        "Missing 14-digit National Cyber Crime Reporting Portal acknowledgement number.",
        "Bank statement highlighting the fraudulent transaction is not annexed.",
        "Missing Certificate under Section 65B of Indian Evidence Act for electronic records."
    ],
    "crop_insurance_rejected": [
        "Missing intimation given to insurance company within 72 hours of crop loss.",
        "Policy/Application number not cited in the subject or facts.",
        "Khasra/Khatauni documents establishing tenancy/ownership not attached."
    ],
    "disaster_relief_denied": [
        "Missing Panchnama / preliminary damage assessment report from Patwari.",
        "Failure to state the exact date of the natural calamity.",
        "Aadhar or Bank Account details for DBT missing."
    ],
    "other": [
        "Verification clause missing or incorrectly formatted.",
        "Jurisdiction paragraph missing (why this specific authority has power to hear this).",
        "Vague prayer/relief sought."
    ]
}

_ADVERSARIAL_SYSTEM_PROMPT = """
You are a highly skeptical Court Clerk (Ahlmad) or Opposing Counsel at an Indian District Court.
Your job is to review a drafted petition and find reasons to reject it at the filing counter.

Look for:
- Missing supporting documents
- Incorrect or missing jurisdiction
- Vague facts or missing critical dates
- Missing procedural prerequisites (e.g., prior notices)
- Incorrect authority addressed

Common rejection reasons for this case type:
{patterns}

Evaluate the drafted petition thoroughly.
You MUST output your critique as a structured JSON list of issues.
Each issue must follow this exact schema:
{{
  "critiques": [
    {{
      "severity": "blocking" or "minor",
      "defect": "<What is wrong or missing in the draft>",
      "fix": "<What the Advocate needs to add or change>"
    }}
  ]
}}

CRITICAL INSTRUCTION: If this is the FIRST draft (round 0), you MUST find AT LEAST ONE defect (even a minor one). Do NOT return an empty list.

Return ONLY valid JSON. No markdown fences. No preamble.
"""

async def adversarial_node(state: CaseState) -> dict:
    """
    LangGraph node for the Adversarial Agent.
    """
    t0 = time.perf_counter()
    
    round_num = state.get("debate_round", 0)
    timestamps = state.get("timestamps", {})
    timestamps[f"adversarial_start_r{round_num}"] = t0
    
    case_type = state.get("case_type", "other")
    draft = state.get("advocate_draft", "")
    
    patterns = "\n".join([f"- {p}" for p in _REJECTION_PATTERNS.get(case_type, _REJECTION_PATTERNS["other"])])
    
    system_prompt = _ADVERSARIAL_SYSTEM_PROMPT.format(patterns=patterns)
    
    user_prompt = f"Case Type: {case_type}\n\nDraft Petition to Review:\n{draft}"
    if round_num == 0:
        user_prompt += "\n\n(Reminder: This is the first draft. You MUST find at least one defect.)"
    
    try:
        response_text, provider = await call_with_fallback(
            prompt=user_prompt,
            preferred="gemini", # Using free tier
            system=system_prompt,
            max_tokens=1500
        )
        
        # Parse JSON output
        clean = response_text.replace("```json", "").replace("```", "").strip()
        data = json.loads(clean)
        
        critiques_list = data.get("critiques", [])
        
        # Enforce round 0 constraint programmatically just in case the LLM disobeys
        if round_num == 0 and len(critiques_list) == 0:
            critiques_list.append({
                "severity": "minor",
                "defect": "Missing explicit verification clause or formal prayer.",
                "fix": "Add a standard verification clause at the end of the petition."
            })
            
        # Serialize the structured critiques as a JSON string so Mediator can parse it
        final_critique_str = json.dumps(critiques_list)
        logger.info(f"[adversarial] Generated critique with {len(critiques_list)} issues. Provider: {provider}")
        
    except Exception as e:
        logger.error(f"[adversarial] LLM critique failed: {e}")
        # Fallback ensuring the loop continues at least once
        fallback_issue = [{"severity": "minor", "defect": "Missing verification clause.", "fix": "Add a formal verification clause at the end."}]
        final_critique_str = json.dumps(fallback_issue) if round_num == 0 else "[]"
            
    timestamps[f"adversarial_end_r{round_num}"] = time.perf_counter()
    
    return {
        "adversarial_critique": [final_critique_str],
        "timestamps": timestamps
    }
