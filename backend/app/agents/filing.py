"""
app/agents/filing.py

Filing Agent Node for LangGraph Orchestrator.
Routes final hardened documents to the correct authority based on case_type.
Dispatches notifications to the citizen via Twilio, with 2G fallback.
Schedules a 7-day follow-up check against the eCourts API.
"""

import logging
import time
from datetime import datetime, timedelta

from app.agents.state import CaseState
from app.integrations.twilio_client import dispatch_with_2g_fallback, send_email
from app.integrations.utils import IntegrationError

logger = logging.getLogger(__name__)

# Explicit routing table mapping case_type to authorities
_ROUTING_TABLE = {
    "fir_not_registered": {
        "authority": "Judicial Magistrate First Class (JMFC) Office",
        "email": "magistrate.office@delhicourts.gov.in"
    },
    "domestic_violence": {
        "authority": "District Protection Officer / Family Court",
        "email": "protection.officer@wcd.gov.in"
    },
    "land_dispute": {
        "authority": "Sub-Divisional Magistrate (SDM) / Tehsildar",
        "email": "sdm.revenue@delhi.gov.in"
    },
    "consumer_complaint": {
        "authority": "District Consumer Disputes Redressal Commission",
        "email": "district.commission@consumer.gov.in"
    },
    "cyber_fraud": {
        "authority": "National Cyber Crime Reporting Portal Nodal Officer",
        "email": "nodal.officer@cybercrime.gov.in"
    },
    "crop_insurance_rejected": {
        "authority": "District Agriculture Officer (DAO)",
        "email": "dao.agriculture@state.gov.in"
    },
    "disaster_relief_denied": {
        "authority": "District Disaster Management Authority (DDMA)",
        "email": "ddma.relief@state.gov.in"
    },
    "other": {
        "authority": "District Court Registry",
        "email": "registry@districtcourts.gov.in"
    }
}

async def schedule_followup(case_id: str, case_type: str, citizen_phone: str):
    """
    Implements the 7-day follow-up scheduler.
    Writes an entry to the (placeholder) follow_ups table.
    """
    next_check = datetime.utcnow() + timedelta(days=7)
    
    # Placeholder for Prompt 9 DB schema insert
    # e.g., neon_client.insert_followup(case_id, next_check, status="pending")
    logger.info(f"[filing] Scheduled 7-day follow-up for case {case_id} at {next_check.isoformat()}")
    pass

async def check_pending_followups():
    """
    API endpoint/cron handler to re-send/escalate if no eCourts status change is detected.
    """
    from app.integrations.ecourts import check_case_status
    
    logger.info("[filing] Running check_pending_followups cron job...")
    # Placeholder: fetch from DB
    # pending = neon_client.get_due_followups()
    pending = [] # Mocked
    
    for followup in pending:
        case_id = followup["case_id"]
        try:
            status = await check_case_status(case_number=followup.get("cnr_number"))
            if status["status"] == "not yet filed" or status["status"] == "unknown":
                # Escalate
                logger.warning(f"[filing] Case {case_id} still not filed after 7 days. Escalating.")
                # Dispatch escalation SMS
                await dispatch_with_2g_fallback(
                    followup["phone_number"], 
                    f"NyaySetu Alert: No court update found for your petition {case_id[-6:]} after 7 days. Please contact 1800-NYAY-HELP.",
                    case_id
                )
            else:
                logger.info(f"[filing] Case {case_id} is active: {status['stage']}")
                # Mark followup completed
        except IntegrationError as e:
            logger.error(f"[filing] Could not check status for case {case_id} due to API error: {e}. Will retry next cron run.")

async def filing_node(state: CaseState) -> dict:
    """
    LangGraph node for the Filing Agent.
    """
    t0 = time.perf_counter()
    timestamps = state.get("timestamps", {})
    timestamps["filing_start"] = t0
    
    case_id = state.get("case_id", "UNKNOWN_CASE")
    case_type = state.get("case_type", "other")
    final_draft = state.get("advocate_draft", "No draft available.")
    
    # In a real app we extract user phone from state or DB. Mocking for now.
    user_phone = "+919999999999" 
    
    # 1. Routing
    route = _ROUTING_TABLE.get(case_type, _ROUTING_TABLE["other"])
    authority = route["authority"]
    auth_email = route["email"]
    
    # Dispatch email to authority
    logger.info(f"[filing] Routing final document for {case_type} to {authority} ({auth_email})")
    await send_email(
        to_email=auth_email,
        subject=f"New Petition Filed: {case_id}",
        body=final_draft
    )
    
    # 2. Dispatch to Citizen with 2G/offline fallback
    rich_text = (
        f"NyaySetu: Your petition for '{case_type.replace('_', ' ').title()}' is ready and has been "
        f"routed to {authority}. \n\n"
        f"Your Reference ID: {case_id[-6:]}\n"
        f"We will notify you of any court updates."
    )
    
    await dispatch_with_2g_fallback(user_phone, rich_text, case_id)
    
    # 3. Schedule 7-day followup
    await schedule_followup(case_id, case_type, user_phone)
    
    # Format the final document object
    final_document = {
        "status": "filed",
        "routed_to": authority,
        "document_body": final_draft,
        "case_type": case_type
    }
    
    timestamps["filing_end"] = time.perf_counter()
    
    return {
        "final_document": final_document,
        "filing_status": "sent",
        "timestamps": timestamps
    }
