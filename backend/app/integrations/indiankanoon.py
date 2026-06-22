"""
app/integrations/indiankanoon.py

Wraps the IndianKanoon API to fetch relevant judgments and sections based on
case type and summary. Implements a hardcoded fallback table so the demo never fails
if the API key is missing or the network flakes.
"""

import logging
import httpx

from app.config import settings
from app.integrations.utils import IntegrationError, retry_with_backoff, RateLimiter

logger = logging.getLogger(__name__)

# IndianKanoon free tier limits: usually 30 requests per minute
_ik_rate_limiter = RateLimiter(calls=30, period=60.0)

_IKANOON_BASE = "https://api.indiankanoon.org"

# Hardcoded fallback provisions per case_type
_FALLBACK_PROVISIONS = {
    "fir_not_registered": [
        {"title": "Section 156(3) CrPC", "excerpt": "Power of Magistrate to direct police to register an FIR and investigate."},
        {"title": "Lalita Kumari vs Govt. of U.P.", "excerpt": "Registration of FIR is mandatory under Section 154 CrPC if information discloses commission of a cognizable offence."}
    ],
    "domestic_violence": [
        {"title": "Section 12 PWDVA, 2005", "excerpt": "Application to Magistrate seeking relief under Protection of Women from Domestic Violence Act."},
        {"title": "Section 498A IPC", "excerpt": "Husband or relative of husband of a woman subjecting her to cruelty."}
    ],
    "land_dispute": [
        {"title": "Section 144 CrPC", "excerpt": "Power to issue order in urgent cases of nuisance or apprehended danger regarding land."},
        {"title": "Section 145 CrPC", "excerpt": "Procedure where dispute concerning land or water is likely to cause breach of peace."}
    ],
    "consumer_complaint": [
        {"title": "Section 35, Consumer Protection Act, 2019", "excerpt": "Manner in which complaint shall be made to the District Commission."},
        {"title": "Section 38, Consumer Protection Act, 2019", "excerpt": "Procedure on admission of complaint regarding defective goods or deficient services."}
    ],
    "cyber_fraud": [
        {"title": "Section 66D, IT Act, 2000", "excerpt": "Punishment for cheating by personation by using computer resource."},
        {"title": "Section 420 IPC", "excerpt": "Cheating and dishonestly inducing delivery of property."}
    ],
    "crop_insurance_rejected": [
        {"title": "Pradhan Mantri Fasal Bima Yojana (PMFBY) Guidelines", "excerpt": "Grievance redressal mechanism for farmers against insurance companies for rejected claims."},
        {"title": "Consumer Protection Act, 2019", "excerpt": "Farmer can approach Consumer Forum for deficiency in service by insurance company."}
    ],
    "disaster_relief_denied": [
        {"title": "State Disaster Response Fund (SDRF) Norms", "excerpt": "Application process and norms for assistance to families affected by natural calamities."},
        {"title": "Disaster Management Act, 2005", "excerpt": "Mandates authorities to provide relief and compensation in notified disasters."}
    ],
    "other": [
        {"title": "Article 226, Constitution of India", "excerpt": "Power of High Courts to issue certain writs for enforcement of Fundamental Rights."},
        {"title": "Section 154 CrPC", "excerpt": "Information in cognizable cases to police."}
    ]
}

def get_fallback_provisions(case_type: str) -> list[dict]:
    """Exposes fallback provisions to the agent layer if the API fails."""
    return _FALLBACK_PROVISIONS.get(case_type, _FALLBACK_PROVISIONS["other"])

@retry_with_backoff(max_retries=2)
async def search_indiankanoon(case_type: str, summary: str) -> list[dict]:
    """
    Searches IndianKanoon API.
    Returns list of dicts: {"title": str, "citation": str, "court": str, "year": str, "excerpt": str}
    Raises IntegrationError on failure.
    """
    if not settings.indiankanoon_api_key:
        raise IntegrationError("IndianKanoon API key is missing.")

    query = f"{case_type.replace('_', ' ')} {summary[:100]}"
    
    try:
        await _ik_rate_limiter.acquire()
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{_IKANOON_BASE}/search/",
                headers={"Authorization": f"Token {settings.indiankanoon_api_key}"},
                data={"formInput": query, "pagenum": 0}
            )
            response.raise_for_status()
            data = response.json()
            
            docs = data.get("docs", [])
            if not docs:
                return []
                
            results = []
            for doc in docs[:5]:
                # Extract basic text, stripping basic HTML
                title_raw = doc.get("title", "Unknown Title")
                import re
                title_clean = re.sub(r"<[^>]+>", "", title_raw)
                excerpt_clean = re.sub(r"<[^>]+>", "", doc.get("headline", ""))
                
                results.append({
                    "title": title_clean,
                    "citation": doc.get("docsource", ""),
                    "court": "Indian Courts",  # API doesn't always split cleanly
                    "year": "",
                    "excerpt": excerpt_clean
                })
            
            logger.info(f"[indiankanoon] Retrieved {len(results)} results from API.")
            return results

    except httpx.HTTPStatusError as exc:
        raise IntegrationError(f"HTTP Error {exc.response.status_code}")
    except httpx.RequestError as exc:
        raise IntegrationError(f"Network error: {exc}")
    except Exception as e:
        raise IntegrationError(f"Unexpected error: {e}")
