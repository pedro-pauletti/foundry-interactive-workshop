"""Foundry Hosted Agent entry-point for the LangGraph telecom agent.

See `responses_app.py` in mafwAgent for the design rationale. This module
wraps the existing LangGraph compiled graph in `ResponsesAgentServerHost`
so the same code can be deployed as a Foundry Hosted Agent on port 8088.
"""
from __future__ import annotations

import asyncio

from azure.ai.agentserver.responses import (
    CreateResponse,
    ResponseContext,
    ResponsesAgentServerHost,
    TextResponse,
)
from langchain_core.messages import AIMessage, HumanMessage

from app import GRAPH  # reuse the compiled LangGraph

app = ResponsesAgentServerHost()


def _run_graph(user_text: str) -> str:
    state = {"messages": [HumanMessage(content=user_text or "")]}
    final = GRAPH.invoke(state)
    answer = ""
    for m in final["messages"]:
        if isinstance(m, AIMessage) and m.content:
            answer = str(m.content)
    return answer or "(sem resposta)"


@app.response_handler
async def handler(
    request: CreateResponse,
    context: ResponseContext,
    cancellation_signal: asyncio.Event,
):
    user_text = await context.get_input_text()
    # LangGraph's `invoke` is sync; offload so we don't block the event loop.
    try:
        answer = await asyncio.to_thread(_run_graph, user_text or "")
    except Exception as exc:
        import traceback
        answer = f"[ERROR] {type(exc).__name__}: {exc}\n{traceback.format_exc()[:2000]}"
    return TextResponse(context, request, text=answer)


if __name__ == "__main__":
    app.run()
