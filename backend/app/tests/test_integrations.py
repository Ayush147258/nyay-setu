import pytest
from unittest.mock import patch
import httpx

from app.integrations.indiankanoon import search_indiankanoon
from app.integrations.twilio_client import dispatch_with_2g_fallback
from app.integrations.ecourts import check_case_status
from app.integrations.utils import IntegrationError

@pytest.fixture(autouse=True)
def mock_sleep():
    """Prevent retry decorator from actually sleeping in tests."""
    with patch("asyncio.sleep") as m:
        yield m

@pytest.mark.asyncio
async def test_indiankanoon_unreachable_raises_integration_error():
    # Test that when IndianKanoon is unreachable, it exhausts retries and raises IntegrationError
    with patch("app.integrations.indiankanoon.settings.indiankanoon_api_key", "test_key"), \
         patch("httpx.AsyncClient.post", side_effect=httpx.RequestError("Network down")), \
         patch("app.integrations.indiankanoon._ik_rate_limiter.acquire"): # Skip rate limiter
        with pytest.raises(IntegrationError) as exc_info:
            await search_indiankanoon("domestic_violence", "summary")
        assert "Network error" in str(exc_info.value)

@pytest.mark.asyncio
async def test_ecourts_no_record_yet():
    # Test the pre-filing fallback in eCourts where case_number is None
    res = await check_case_status(case_number=None, district="Delhi")
    assert res["status"] == "not yet filed"
    assert "not yet been registered" in res["message"]

@pytest.mark.asyncio
async def test_twilio_rejects_number_falls_back_to_sms():
    # Test that a WhatsApp rejection triggers the 2G offline SMS fallback
    with patch("app.integrations.twilio_client.send_whatsapp", side_effect=IntegrationError("WhatsApp delivery failed: Invalid number")):
        with patch("app.integrations.twilio_client.send_sms", return_value=True) as mock_sms:
            
            res = await dispatch_with_2g_fallback("+12345", "Rich text", "CASE123")
            
            # The function should still return True because the fallback succeeded
            assert res is True
            # Assert that the fallback text was sent instead of the rich text
            mock_sms.assert_called_once()
            called_number, called_text = mock_sms.call_args[0]
            assert "NyaySetu Alert" in called_text or "1800-NYAY-HELP" in called_text
