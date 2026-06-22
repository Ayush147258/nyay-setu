"""
app/integrations/ecourts.py

eCourts API Wrapper for NyaySetu.
Handles looking up case status via the public eCourts infrastructure.
"""

import logging
import httpx

from app.config import settings
from app.integrations.utils import IntegrationError, retry_with_backoff

logger = logging.getLogger(__name__)

_ECOURTS_MOCK_API = "https://mock.ecourts.gov.in/api/v1" # Simulated endpoint for the prototype

@retry_with_backoff(max_retries=2)
async def check_case_status(
    case_number: str | None = None, 
    district: str | None = None, 
    case_type: str | None = None
) -> dict:
    """
    Queries eCourts API for case status.
    If no case number exists yet (pre-filing), returns a clear "not yet filed" status.
    """
    # Pre-filing check
    if not case_number:
        logger.info("[ecourts] No case number provided (pre-filing). Returning 'not yet filed'.")
        return {
            "status": "not yet filed",
            "stage": "Drafting / Pre-filing",
            "hearing_date": None,
            "court": f"{district or 'Unknown'} District Court",
            "message": "Petition is ready but has not yet been registered with the court registry."
        }
        
    logger.info(f"[ecourts] Looking up status for CNR/Case Number: {case_number}")
    
    try:
        # In a real scenario, this would use the authorized eCourts API credentials
        # We simulate the API call here for the prototype.
        async with httpx.AsyncClient(timeout=10.0) as client:
            # response = await client.get(f"{_ECOURTS_MOCK_API}/status/{case_number}")
            # response.raise_for_status()
            # data = response.json()
            
            # Simulated successful active case
            return {
                "status": "active",
                "stage": "Notice Issued / Awaiting Reply",
                "hearing_date": "2026-07-15",
                "court": f"{district or 'Delhi'} District Court",
                "message": "Case is listed for next hearing on 15 July 2026."
            }
            
    except httpx.HTTPStatusError as exc:
        raise IntegrationError(f"eCourts HTTP Error: {exc.response.status_code}")
    except httpx.RequestError as exc:
        raise IntegrationError(f"eCourts Network Error: {exc}")
    except Exception as e:
        raise IntegrationError(f"eCourts Unexpected Error: {e}")
