import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

from langgraph.graph import StateGraph

from app.core.graph import build_case_graph, run_case
from app.agents.state import CaseState

@pytest.mark.asyncio
async def test_debate_round_never_exceeds_2_when_mediator_rejects():
    # We mock the node functions to simulate an endless debate loop
    
    async def mock_intake(state: CaseState):
        return {"case_type": "test"}
        
    async def mock_advocate(state: CaseState):
        return {"advocate_draft": "Draft version"}
        
    async def mock_adversarial(state: CaseState):
        return {"adversarial_critique": [{"defect": "bad"}]}
        
    async def mock_mediator(state: CaseState):
        # Mediator always rejects (score < 8.0) and increments debate_round
        return {
            "mediator_score": 0.0, 
            "debate_round": state.get("debate_round", 0) + 1
        }
        
    async def mock_filing(state: CaseState):
        return {"filing_status": "sent"}

    # Patch the node functions at their graph builder imports
    with patch("app.core.graph.intake_node", side_effect=mock_intake), \
         patch("app.core.graph.advocate_node", side_effect=mock_advocate), \
         patch("app.core.graph.adversarial_node", side_effect=mock_adversarial), \
         patch("app.core.graph.mediator_node", side_effect=mock_mediator), \
         patch("app.core.graph.filing_node", side_effect=mock_filing):
         
        graph = build_case_graph()
        initial_state = {
            "case_id": "TEST-CAP",
            "debate_round": 0,
            "mediator_score": 0.0
        }
        
        # Execute the compiled graph
        final_state = await graph.ainvoke(initial_state)
        
        # Even though mediator ALWAYS gives a 0.0 score, the hard cap prevents round > 2
        assert final_state["debate_round"] == 2
        # Ensure it actually hit Filing and finished
        assert final_state["filing_status"] == "sent"

@pytest.mark.asyncio
async def test_90_second_timeout_fallback_routes_to_filing():
    # We simulate a slow node by making it sleep for 100 seconds
    async def slow_intake(state: CaseState):
        await asyncio.sleep(100)
        return {"case_type": "slow"}

    mock_pool = AsyncMock()
    mock_saver = AsyncMock()
    
    # We mock the graph instance returned by build_case_graph
    mock_graph = MagicMock()
    mock_graph.astream = MagicMock(side_effect=asyncio.TimeoutError)

    with patch("app.core.graph.intake_node", side_effect=slow_intake), \
         patch("app.core.graph.AsyncConnectionPool", return_value=mock_pool), \
         patch("app.core.graph.AsyncPostgresSaver", return_value=mock_saver), \
         patch("app.core.graph.build_case_graph", return_value=mock_graph), \
         patch("app.core.graph.insert_agent_run"), \
         patch("app.core.graph.publish"):
            result = await run_case("TEST-TIMEOUT", "Raw Input")
            
            # The exception block should have forced it to filing_status = timeout_fallback
            assert result["filing_status"] == "timeout_fallback"
            assert "timeout fallback" in result["final_document"]["document_body"]

@pytest.mark.asyncio
async def test_checkpointing_writes_row_per_node_transition():
    # Mock astream to yield predictable node transitions
    async def mock_astream(*args, **kwargs):
        yield {"Intake": {"case_type": "fir"}}
        yield {"Advocate": {"advocate_draft": "Draft"}}
        yield {"Filing": {"filing_status": "sent"}}
        
    mock_pool = AsyncMock()
    mock_saver = AsyncMock()

    mock_graph = MagicMock()
    mock_graph.astream = mock_astream

    with patch("app.core.graph.settings.database_url", "postgresql://mock"), \
         patch("app.core.graph.AsyncConnectionPool", return_value=mock_pool), \
         patch("app.core.graph.AsyncPostgresSaver", return_value=mock_saver), \
         patch("app.core.graph.build_case_graph", return_value=mock_graph), \
         patch("app.core.graph.insert_agent_run") as mock_insert, \
         patch("app.core.graph.publish"):
         
        await run_case("TEST-CHECKPOINT", "Raw input")
        await asyncio.sleep(0.01)
        
        # We expect 3 inserts, one per yielded node state
        assert mock_insert.call_count == 3
        assert mock_insert.call_args_list[0].kwargs["agent_name"] == "Intake"
        assert mock_insert.call_args_list[1].kwargs["agent_name"] == "Advocate"
        assert mock_insert.call_args_list[2].kwargs["agent_name"] == "Filing"
