import pytest
import json
from unittest.mock import patch, MagicMock
from app.agents.state import CaseState
from app.agents.intake import intake_node
from app.agents.advocate import advocate_node
from app.agents.adversarial import adversarial_node
from app.agents.mediator import mediator_node
from app.agents.filing import filing_node

@pytest.fixture
def base_state():
    return CaseState(
        case_id="TEST-123",
        raw_input="My neighbor blocked my land.",
        detected_language="en",
        debate_round=0,
        timestamps={}
    )

@pytest.mark.asyncio
async def test_intake_node_decision_logic(base_state):
    # Mock the classifier to simulate successful classification
    with patch("app.agents.intake.classify_case_llm", return_value=("land_dispute", 0.95, "Sec 145 CrPC")), \
         patch("app.agents.intake.call_with_fallback", return_value=("Normalized text", "mock")):
        result = await intake_node(base_state)
        assert result["case_type"] == "land_dispute"
        assert result["classification_confidence"] == 0.95
        assert "intake_end" in result["timestamps"]

@pytest.mark.asyncio
async def test_advocate_node_decision_logic(base_state):
    base_state["case_type"] = "land_dispute"
    # Mock IndianKanoon and the LLM
    with patch("app.agents.advocate.search_indiankanoon") as m_search, \
         patch("app.agents.advocate.call_with_fallback") as m_llm:
        
        m_search.return_value = [{"title": "Sec 145 CrPC", "excerpt": "Land dispute"}]
        m_llm.return_value = ('{"draft": "Mocked Draft Petition for Land Dispute", "revision_notes": ""}', "mock")
        
        result = await advocate_node(base_state)
        
        assert "Mocked Draft Petition" in result["advocate_draft"]
        m_search.assert_awaited_once_with("land_dispute", base_state["raw_input"])
        m_llm.assert_awaited_once()

@pytest.mark.asyncio
async def test_adversarial_node_decision_logic(base_state):
    base_state["advocate_draft"] = "Mocked Draft Petition"
    base_state["case_type"] = "land_dispute"
    
    # Mock LLM to return a structured critique
    mock_critique = """
    {
      "critiques": [
        {"severity": "blocking", "defect": "Missing property dimensions", "fix": "Add dimensions"}
      ]
    }
    """
    with patch("app.agents.adversarial.call_with_fallback", return_value=(mock_critique, "mock")):
        result = await adversarial_node(base_state)
        assert "adversarial_critique" in result
        assert len(result["adversarial_critique"]) == 1 # 1 round of critique added
        critiques_list = json.loads(result["adversarial_critique"][0])
        assert critiques_list[0]["severity"] == "blocking"

@pytest.mark.asyncio
async def test_mediator_node_decision_logic(base_state):
    base_state["advocate_draft"] = "Mocked Draft"
    base_state["adversarial_critique"] = [json.dumps([{"severity": "blocking", "defect": "Missing evidence"}])]
    base_state["debate_round"] = 2 # Force approval to test annotations
    
    # Mock LLM to return a low score
    mock_scoring = '{"scores": {"completeness": 4, "legal_accuracy": 4, "procedural_correctness": 4}, "unresolved_blocking_issues": ["Evidence required"]}'
    with patch("app.agents.mediator.call_with_fallback", return_value=(mock_scoring, "mock")):
        result = await mediator_node(base_state)
        assert result["mediator_score"] == 4
        assert any("Evidence required" in ann for ann in result["mediator_annotations"])
        assert any(k.startswith("mediator_end") for k in result["timestamps"])

@pytest.mark.asyncio
async def test_filing_node_decision_logic(base_state):
    base_state["advocate_draft"] = "Final Petition Text"
    base_state["case_type"] = "land_dispute"
    
    with patch("app.agents.filing.send_email") as m_email, \
         patch("app.agents.filing.dispatch_with_2g_fallback") as m_dispatch, \
         patch("app.agents.filing.schedule_followup") as m_schedule:
        
        result = await filing_node(base_state)
        
        assert result["filing_status"] == "sent"
        assert result["final_document"]["routed_to"] == "Sub-Divisional Magistrate (SDM) / Tehsildar"
        assert result["final_document"]["document_body"] == "Final Petition Text"
        
        m_email.assert_awaited_once()
        m_dispatch.assert_awaited_once()
        m_schedule.assert_awaited_once()
