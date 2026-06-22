"""
app/core/pubsub.py

In-memory pub/sub for SSE streaming of agent state transitions.
Justification: For a prototype, an in-memory dictionary of asyncio Queues 
is vastly simpler and faster than polling Postgres or setting up Redis pub/sub. 
It avoids DB contention and is perfect for real-time streaming from a single-node FastAPI instance.
"""

import asyncio

_STREAM_QUEUES = {}

def get_queue(case_id: str) -> asyncio.Queue:
    if case_id not in _STREAM_QUEUES:
        _STREAM_QUEUES[case_id] = asyncio.Queue()
    return _STREAM_QUEUES[case_id]

async def publish(case_id: str, event_data: dict):
    if case_id in _STREAM_QUEUES:
        await _STREAM_QUEUES[case_id].put(event_data)
