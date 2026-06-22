"""
app/api/agents.py

Endpoints for the LangGraph multi-agent loop and PDF generation.
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import StreamingResponse, FileResponse
import tempfile
import os

from weasyprint import HTML

from app.core.graph import run_case
from app.core.pubsub import get_queue

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/run-agents")
async def run_agents_endpoint(background_tasks: BackgroundTasks, payload: dict):
    """
    Accepts case_id + raw_input. Kicks off graph.py's run_case() as a background task.
    Returns immediately.
    """
    case_id = payload.get("case_id") or str(uuid.uuid4())
    raw_input = payload.get("raw_input", "")
    
    if not raw_input:
        raise HTTPException(status_code=400, detail="raw_input is required")
        
    logger.info(f"[api] Queuing background run for case: {case_id}")
    
    # Run the 5-agent pipeline in the background
    background_tasks.add_task(run_case, case_id, raw_input)
    
    return {"case_id": case_id, "status": "running"}

@router.get("/stream/{case_id}")
async def stream_case(case_id: str, request: Request):
    """
    Server-Sent Events (SSE) endpoint that streams each agent's state transition as it happens.
    Reads from the in-memory pub/sub populated by graph.py.
    """
    queue = get_queue(case_id)
    
    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    logger.info(f"[api] Client disconnected from SSE stream for {case_id}")
                    break
                    
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=2.0)
                    yield f"data: {json.dumps(event)}\n\n"
                    
                    if event.get("status") in ["completed", "error"]:
                        break
                except asyncio.TimeoutError:
                    # Keep-alive heartbeat
                    yield ": keepalive\n\n"
        except Exception as e:
            logger.error(f"[api] SSE stream error: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            
    return StreamingResponse(event_generator(), media_type="text/event-stream")

@router.get("/petition/{case_id}/pdf")
async def generate_pdf(case_id: str):
    """
    Generates a real PDF from the final document using WeasyPrint.
    Uses styling that matches the doc-card aesthetic from the frontend.
    """
    # Retrieve final document from Postgres checkpoint
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from psycopg_pool import AsyncConnectionPool
    from app.config import settings
    
    db_uri = settings.database_url
    draft = "No draft available."
    
    try:
        async with AsyncConnectionPool(conninfo=db_uri, max_size=2) as pool:
            checkpointer = AsyncPostgresSaver(pool)
            await checkpointer.setup()
            
            config = {"configurable": {"thread_id": case_id}}
            checkpoint_tuple = await checkpointer.aget_tuple(config)
            
            if checkpoint_tuple:
                state = checkpoint_tuple.checkpoint.get("channel_values", {})
                draft = state.get("advocate_draft", draft)
    except Exception as e:
        logger.error(f"[api] Could not load checkpoint for PDF: {e}")
        # In a real system, we'd query the Neon DB if it's no longer in the checkpointer.
        raise HTTPException(status_code=500, detail="Database connection failed.")
        
    if draft == "No draft available.":
        raise HTTPException(status_code=404, detail="Case or final document not found.")
        
    html_content = f"""
    <html>
    <head>
        <style>
            @page {{ size: A4; margin: 2.5cm; }}
            body {{ font-family: monospace; font-size: 12pt; color: #1B2A38; line-height: 1.5; }}
            .header {{ text-align: center; border-bottom: 2px solid #B8965A; padding-bottom: 15px; margin-bottom: 30px; }}
            .header h1 {{ margin: 0; color: #1B2A38; font-family: sans-serif; font-size: 24pt; }}
            .header p {{ margin: 5px 0 0 0; font-size: 10pt; color: #555; text-transform: uppercase; letter-spacing: 2px; }}
            .content {{ white-space: pre-wrap; }}
            .footer {{ position: fixed; bottom: 0; width: 100%; border-top: 1px solid #ddd; padding-top: 10px; font-size: 8pt; color: #777; font-family: sans-serif; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>NYAYSETU</h1>
            <p>Autonomous Legal Rights Navigator</p>
        </div>
        <div class="content">{draft}</div>
        <div class="footer">
            Case Ref: {case_id} | Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")} | nyaysetu.in
        </div>
    </body>
    </html>
    """
    
    # We use tempfile to avoid permissions issues across platforms
    temp_dir = tempfile.gettempdir()
    pdf_path = os.path.join(temp_dir, f"{case_id}_petition.pdf")
    
    try:
        HTML(string=html_content).write_pdf(pdf_path)
    except Exception as e:
        logger.error(f"[api] WeasyPrint failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate PDF.")
        
    return FileResponse(pdf_path, media_type="application/pdf", filename=f"{case_id}_petition.pdf")
