"""Foundry Hosted Agent entry-point for the MAFW orchestrator.

When this container runs **inside Microsoft Foundry Agent Service** as a
hosted agent, the platform expects the OpenAI-compatible **Responses** protocol
on port 8088 (default). This module wraps the existing MAF orchestrator in
`azure.ai.agentserver.responses.ResponsesAgentServerHost` and reuses the
`ORCHESTRATOR.run(...)` flow already implemented in `app.py` — same agent,
two runtimes:

    docker compose up        -> uvicorn ./app.py /chat   (port 8091)
    Foundry Hosted Agent     -> hypercorn ./responses_app.py /responses (port 8088)
"""
from __future__ import annotations

import asyncio

from azure.ai.agentserver.responses import (
    CreateResponse,
    ResponseContext,
    ResponsesAgentServerHost,
    TextResponse,
)

from app import ORCHESTRATOR  # reuse the same Microsoft Agent Framework agent

app = ResponsesAgentServerHost()


@app.response_handler
async def handler(
    request: CreateResponse,
    context: ResponseContext,
    cancellation_signal: asyncio.Event,
):
    """Single turn: hand the user input to the MAF orchestrator and return its
    final text. Tool routing and Foundry A2A calls happen inside the agent."""
    user_text = await context.get_input_text()
    try:
        result = await ORCHESTRATOR.run(user_text or "")
        answer = getattr(result, "text", None) or str(result)
    except Exception as exc:  # surface error to caller for debugging
        import traceback
        answer = f"[ERROR] {type(exc).__name__}: {exc}\n{traceback.format_exc()[:2000]}"
    return TextResponse(context, request, text=answer)


if __name__ == "__main__":
    app.run()
