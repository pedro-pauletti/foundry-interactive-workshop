"""MAFW Orchestrator — ConectaTel.

Multi-agent orchestration with the **Microsoft Agent Framework**:

    user ──► orquestrador (MAF) ──► especialista-produtos       (local MAF + Azure Search)
                                ──► especialista-regulamentos   (local MAF + Azure Search)
                                ──► especialista-vendas         (Foundry prompt-based agent)
                                ──► especialista-suporte        (Foundry prompt-based agent)
                                ──► langgraph-contoso           (Foundry Hosted Agent · container)

The orchestrator (MAF) exposes 5 tools — 2 wrap local specialists via
`Agent.as_tool()`, 2 wrap **Foundry prompt-based agents** (threads/runs API),
and 1 wraps a **Foundry Hosted Agent** (containerized agent invoked via the
OpenAI Responses protocol on `/agents/<name>/endpoint/protocols/openai`).
The LLM picks which to call.

Also exposes a streaming SSE endpoint (`/chat/stream`) that emits per-tool
events (start/end) plus the final answer — so the UI can render the
orchestration path live.
"""
from __future__ import annotations

import asyncio
import contextvars
import json
import logging
import os
import time
from pathlib import Path
from typing import Annotated, Any

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from azure.identity import DefaultAzureCredential
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizableTextQuery

from agent_framework import Agent, tool
from agent_framework.openai import OpenAIChatCompletionClient

# --------------------------------------------------------------------------- env
load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
load_dotenv()

AOAI_ENDPOINT     = os.environ.get("AZURE_OPENAI_ENDPOINT", "").rstrip("/")
AOAI_API_VERSION  = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21")
AOAI_CHAT_DEPLOY  = os.environ.get("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-4.1-mini")

SEARCH_ENDPOINT   = os.environ.get("AZURE_SEARCH_ENDPOINT", "")
INDEX_TELECOM     = os.environ.get("AZURE_SEARCH_INDEX_TELECOM", "telecom-products")
INDEX_REGULATIONS = os.environ.get("AZURE_SEARCH_INDEX_REGULATIONS", "internal-regulations")

# Foundry Hosted Agents (A2A — invocados como tools pelo orquestrador MAF)
FOUNDRY_PROJECT_ENDPOINT = os.environ.get("AZURE_AI_PROJECT_ENDPOINT", "").rstrip("/")
FOUNDRY_AGENT_VENDAS     = os.environ.get("AZURE_AI_AGENT_VENDAS",  "especialista-vendas")
FOUNDRY_AGENT_SUPORTE    = os.environ.get("AZURE_AI_AGENT_SUPORTE", "especialista-suporte-tecnico")
FOUNDRY_HOSTED_LANGGRAPH = os.environ.get("AZURE_AI_HOSTED_LANGGRAPH", "langgraph-contoso")

credential = DefaultAzureCredential()
log = logging.getLogger("mafw")


# --------------------------------------------------------------------------- streaming bus
# Per-request asyncio.Queue carried by contextvar so that any tool — even
# nested ones invoked deep inside `Agent.run()` — can emit progress events
# back to the SSE generator without changing tool signatures.
_event_bus: contextvars.ContextVar["asyncio.Queue[dict[str, Any]] | None"] = (
    contextvars.ContextVar("mafw_event_bus", default=None)
)


def _emit(event: dict[str, Any]) -> None:
    q = _event_bus.get()
    if q is None:
        return
    try:
        q.put_nowait({"ts": time.time(), **event})
    except Exception:
        pass


# --------------------------------------------------------------------------- search helpers
def _search_telecom(query: str) -> str:
    if not SEARCH_ENDPOINT:
        return "[ERRO] AZURE_SEARCH_ENDPOINT não configurado."
    sc = SearchClient(
        endpoint=SEARCH_ENDPOINT,
        index_name=INDEX_TELECOM,
        credential=credential,
        api_version="2025-11-01-preview",
    )
    hits = sc.search(
        search_text=query,
        vector_queries=[VectorizableTextQuery(text=query, k_nearest_neighbors=5, fields="groupFieldVector")],
        select=["sku", "productName", "category", "subcategory", "monthlyPriceBRL", "description"],
        top=5,
    )
    lines = []
    for h in hits:
        price = f"R${h['monthlyPriceBRL']:.2f}/mês" if h.get("monthlyPriceBRL") else ""
        lines.append(
            f"- [{h['sku']}] {h['productName']} ({h.get('subcategory','')}) {price} — {h.get('description','')}"
        )
    return "\n".join(lines) if lines else "Nenhum produto encontrado."


def _search_regulations(query: str) -> str:
    if not SEARCH_ENDPOINT:
        return "[ERRO] AZURE_SEARCH_ENDPOINT não configurado."
    sc = SearchClient(
        endpoint=SEARCH_ENDPOINT,
        index_name=INDEX_REGULATIONS,
        credential=credential,
        api_version="2025-11-01-preview",
    )
    hits = sc.search(
        search_text=query,
        vector_queries=[VectorizableTextQuery(text=query, k_nearest_neighbors=5, fields="groupFieldVector")],
        select=["policyId", "title", "category", "subcategory", "owner", "version", "summary", "content"],
        top=5,
    )
    parts = []
    for h in hits:
        parts.append(
            f"[{h['policyId']} v{h.get('version','?')}] {h['title']} ({h.get('owner','')})\n"
            f"  Resumo: {h.get('summary','')}\n"
            f"  Trecho: {(h.get('content','') or '')[:400]}"
        )
    return "\n\n".join(parts) if parts else "Nenhuma política encontrada."


# --------------------------------------------------------------------------- specialist tools
@tool(description="Busca no catálogo de telecom (planos, fibra, dispositivos). Retorna até 5 itens.")
def search_telecom_catalog(
    query: Annotated[str, "Pergunta ou termo de busca em linguagem natural."],
) -> str:
    _emit({"type": "tool_start", "tool": "especialista-produtos", "host": "Local · MAF + Azure Search", "input": query})
    out = _search_telecom(query)
    _emit({"type": "tool_end", "tool": "especialista-produtos", "preview": (out or "")[:240]})
    return out


@tool(description="Busca políticas internas (RH, SegInfo, LGPD). Retorna até 5 políticas.")
def search_internal_regulations(
    query: Annotated[str, "Pergunta ou termo de busca em linguagem natural."],
) -> str:
    _emit({"type": "tool_start", "tool": "especialista-regulamentos", "host": "Local · MAF + Azure Search", "input": query})
    out = _search_regulations(query)
    _emit({"type": "tool_end", "tool": "especialista-regulamentos", "preview": (out or "")[:240]})
    return out


# --------------------------------------------------------------------------- Foundry Hosted Agent invocation (A2A)
_foundry_project = None
_foundry_init_error: str | None = None


def _get_foundry_project():
    """Lazy singleton for the AIProjectClient (Foundry Hosted Agents)."""
    global _foundry_project, _foundry_init_error
    if _foundry_project is not None or _foundry_init_error is not None:
        return _foundry_project
    if not FOUNDRY_PROJECT_ENDPOINT:
        _foundry_init_error = "AZURE_AI_PROJECT_ENDPOINT não configurado"
        return None
    try:
        from azure.ai.projects import AIProjectClient
        _foundry_project = AIProjectClient(
            endpoint=FOUNDRY_PROJECT_ENDPOINT,
            credential=credential,
        )
    except Exception as exc:
        _foundry_init_error = str(exc)
        return None
    return _foundry_project


def _invoke_foundry_agent(agent_name: str, message: str) -> str:
    """Invoke a Foundry Hosted Agent end-to-end (thread → run → wait → reply).

    Returns the final assistant text, or an error string the LLM can surface.
    """
    project = _get_foundry_project()
    if project is None:
        return f"[A2A · Foundry indisponível] {_foundry_init_error or 'projeto não inicializado'}"
    try:
        agent = project.agents.get_agent(agent_name)
    except Exception as exc:
        return f"[A2A · Foundry] não encontrei o agente '{agent_name}': {exc}"
    try:
        thread = project.agents.threads.create()
        project.agents.messages.create(thread_id=thread.id, role="user", content=message)
        run = project.agents.runs.create_and_process(thread_id=thread.id, agent_id=agent.id)
        if getattr(run, "status", "") == "failed":
            return f"[A2A · Foundry · {agent_name}] run failed: {getattr(run, 'last_error', '?')}"
        # Fetch latest assistant message
        msgs = project.agents.messages.list(thread_id=thread.id)
        for m in msgs:
            if getattr(m, "role", "") == "assistant":
                content = getattr(m, "content", None) or []
                parts: list[str] = []
                for block in content:
                    text_block = getattr(block, "text", None)
                    if text_block is not None:
                        val = getattr(text_block, "value", None)
                        if val:
                            parts.append(val)
                if parts:
                    return "\n".join(parts)
        return f"[A2A · Foundry · {agent_name}] sem resposta do agente."
    except Exception as exc:
        return f"[A2A · Foundry · {agent_name}] erro: {exc}"


@tool(description=(
    "Especialista de VENDAS — agente prompt-based no Microsoft Foundry. "
    "Use para recomendação de planos, ofertas, comparação e contratação."
))
def call_foundry_vendas(
    question: Annotated[str, "Pergunta do cliente em pt-BR; reformule se ajudar."],
) -> str:
    _emit({"type": "tool_start", "tool": "especialista-vendas", "host": "Foundry · prompt-based agent", "input": question})
    out = _invoke_hosted_agent(FOUNDRY_AGENT_VENDAS, question)
    _emit({"type": "tool_end", "tool": "especialista-vendas", "preview": (out or "")[:240]})
    return out


@tool(description=(
    "Especialista de SUPORTE TÉCNICO — agente prompt-based no Microsoft Foundry. "
    "Use para problemas de internet, modem, Wi-Fi, 5G, app do cliente."
))
def call_foundry_suporte(
    question: Annotated[str, "Descrição do problema técnico em pt-BR."],
) -> str:
    _emit({"type": "tool_start", "tool": "especialista-suporte-tecnico", "host": "Foundry · prompt-based agent", "input": question})
    out = _invoke_hosted_agent(FOUNDRY_AGENT_SUPORTE, question)
    _emit({"type": "tool_end", "tool": "especialista-suporte-tecnico", "preview": (out or "")[:240]})
    return out


# --------------------------------------------------------------------------- Foundry Hosted Agent (container) invocation
# Hosted Agents são containers próprios (MAF / LangGraph / código custom)
# hospedados pelo Foundry Agent Service. Diferente dos prompt-based agents
# acima, esses são invocados via protocolo OpenAI Responses no endpoint
# `{project}/agents/{name}/endpoint/protocols/openai`.
_hosted_token_provider: Any = None


def _invoke_hosted_agent(hosted_name: str, message: str) -> str:
    """Invoke a Foundry Hosted Agent (container) via OpenAI Responses."""
    if not FOUNDRY_PROJECT_ENDPOINT:
        return "[Hosted Agent indisponível] AZURE_AI_PROJECT_ENDPOINT não configurado."
    try:
        global _hosted_token_provider
        from azure.identity import get_bearer_token_provider
        from openai import OpenAI
        if _hosted_token_provider is None:
            _hosted_token_provider = get_bearer_token_provider(
                credential, "https://ai.azure.com/.default"
            )
        base = f"{FOUNDRY_PROJECT_ENDPOINT}/agents/{hosted_name}/endpoint/protocols/openai"
        client = OpenAI(
            api_key=_hosted_token_provider,
            base_url=base,
            default_query={"api-version": "v1"},
        )
        resp = client.responses.create(input=message, model=AOAI_CHAT_DEPLOY)
        text = getattr(resp, "output_text", None) or ""
        if not text:
            try:
                outputs = getattr(resp, "output", []) or []
                parts: list[str] = []
                for item in outputs:
                    for c in getattr(item, "content", []) or []:
                        val = getattr(c, "text", None)
                        if val:
                            parts.append(val)
                text = "\n".join(parts)
            except Exception:
                pass
        return text or f"[Hosted Agent · {hosted_name}] sem resposta."
    except Exception as exc:
        return f"[Hosted Agent · {hosted_name}] erro: {exc}"


@tool(description=(
    "Catálogo telecom via LangGraph — agente CONTAINER hospedado no Foundry "
    "(Foundry Hosted Agent). Implementação alternativa do especialista de "
    "produtos usando LangGraph em vez de MAF. Use quando o cliente quiser uma "
    "consulta exploratória ao catálogo com raciocínio passo-a-passo."
))
def call_hosted_langgraph(
    question: Annotated[str, "Pergunta sobre planos, dispositivos, fibra em pt-BR."],
) -> str:
    _emit({
        "type": "tool_start",
        "tool": "langgraph-contoso",
        "host": "Foundry Hosted · container",
        "input": question,
    })
    out = _invoke_hosted_agent(FOUNDRY_HOSTED_LANGGRAPH, question)
    _emit({"type": "tool_end", "tool": "langgraph-contoso", "preview": (out or "")[:240]})
    return out



# --------------------------------------------------------------------------- chat client
def _chat_client() -> OpenAIChatCompletionClient:
    # Azure OpenAI via Entra ID (DefaultAzureCredential).
    return OpenAIChatCompletionClient(
        model=AOAI_CHAT_DEPLOY,
        azure_endpoint=AOAI_ENDPOINT,
        api_version=AOAI_API_VERSION,
        credential=credential,
    )


# --------------------------------------------------------------------------- specialist agents
INSTR_PRODUTOS = """Você é o especialista de produtos da ConectaTel. SEMPRE use a tool
`search_telecom_catalog` antes de responder. Cite SKU + nome do produto. Não invente
preços, fidelidade ou prazos. Português, cordial e direto."""

INSTR_REGULAMENTOS = """Você é o especialista de regulamentos internos da ConectaTel.
SEMPRE use a tool `search_internal_regulations`. Cite policyId + versão. Quando a
política não cobrir, oriente o canal correto (RH, DPO, CSIRT). Português profissional."""


SPEC_PRODUTOS = Agent(
    _chat_client(),
    instructions=INSTR_PRODUTOS,
    name="especialista-produtos",
    description="Tira dúvidas sobre planos móveis, fibra, TV e dispositivos da ConectaTel.",
    tools=[search_telecom_catalog],
)
SPEC_REGULAMENTOS = Agent(
    _chat_client(),
    instructions=INSTR_REGULAMENTOS,
    name="especialista-regulamentos",
    description="Responde dúvidas sobre RH, Segurança da Informação e LGPD.",
    tools=[search_internal_regulations],
)


# Outer wrappers (emit specialist-level events that the orchestrator can show)
@tool(description=(
    "Especialista de PRODUTOS — agente LOCAL (Microsoft Agent Framework + Azure Search). "
    "Use para perguntas sobre catálogo de planos, fibra, dispositivos."
))
async def especialista_produtos(
    pergunta: Annotated[str, "Pergunta do cliente em pt-BR."],
) -> str:
    _emit({"type": "tool_start", "tool": "especialista-produtos",
           "host": "Local · MAF + Azure Search", "input": pergunta})
    result = await SPEC_PRODUTOS.run(pergunta)
    out = getattr(result, "text", None) or str(result)
    _emit({"type": "tool_end", "tool": "especialista-produtos", "preview": (out or "")[:240]})
    return out


@tool(description=(
    "Especialista de REGULAMENTOS — agente LOCAL (Microsoft Agent Framework + Azure Search). "
    "Use para perguntas sobre políticas internas (RH, SegInfo, LGPD)."
))
async def especialista_regulamentos(
    pergunta: Annotated[str, "Pergunta do cliente em pt-BR."],
) -> str:
    _emit({"type": "tool_start", "tool": "especialista-regulamentos",
           "host": "Local · MAF + Azure Search", "input": pergunta})
    result = await SPEC_REGULAMENTOS.run(pergunta)
    out = getattr(result, "text", None) or str(result)
    _emit({"type": "tool_end", "tool": "especialista-regulamentos", "preview": (out or "")[:240]})
    return out


# --------------------------------------------------------------------------- orchestrator
INSTR_ORCH = """Você é o orquestrador de atendimento da ConectaTel, rodando no
Microsoft Agent Framework.

Sua missão é entender a intenção do usuário e delegar para o(s) especialista(s)
correto(s) chamando as tools disponíveis. Há TRÊS tipos de back-end:

LOCAL · Microsoft Agent Framework (containers ao lado deste orquestrador)
- `especialista_produtos`         → catálogo: planos, fibra, dispositivos
- `especialista_regulamentos`     → políticas internas (RH, SI, LGPD)

FOUNDRY · prompt-based agents (criados no Foundry Portal, sem container)
- `call_foundry_vendas`           → contratação, recomendação, ofertas
- `call_foundry_suporte`          → suporte técnico (internet, modem, Wi-Fi, 5G)

FOUNDRY · Hosted Agents (container próprio rodando dentro do Foundry)
- `call_hosted_langgraph`         → catálogo telecom via LangGraph (alternativa
                                    ao especialista_produtos, raciocínio passo-a-passo)

REGRAS:
- Escolha a ROTA mais apropriada — se o cliente já disse "via langgraph" ou
  "raciocínio detalhado", prefira `call_hosted_langgraph`. Caso contrário,
  para catálogo padrão use `especialista_produtos`.
- Para perguntas multi-tema, chame mais de uma tool e consolide as respostas.
- Reformule a pergunta para cada especialista quando ajudar.
- A resposta final é SUA: junte as respostas dos especialistas em uma única
  mensagem clara em português, mantendo as citações (SKU / policyId).
- Se nenhum especialista couber, responda educadamente que está fora do escopo.
"""

ORCHESTRATOR = Agent(
    _chat_client(),
    instructions=INSTR_ORCH,
    name="orquestrador-mafw",
    description="Orquestrador multi-agente da ConectaTel (MAF + Foundry prompt agents + Foundry Hosted Agents).",
    tools=[
        especialista_produtos,
        especialista_regulamentos,
        call_foundry_vendas,
        call_foundry_suporte,
        call_hosted_langgraph,
    ],
)


# --------------------------------------------------------------------------- api
app = FastAPI(title="MAFW Orchestrator — ConectaTel")


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)


class ChatResponse(BaseModel):
    answer: str
    tool_calls: list[str]
    duration_ms: int
    runtime: str = "microsoft-agent-framework"


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "runtime": "microsoft-agent-framework",
        "model": AOAI_CHAT_DEPLOY,
        "specialists": [
            {"name": "especialista-produtos",     "host": "local-maf"},
            {"name": "especialista-regulamentos", "host": "local-maf"},
            {"name": FOUNDRY_AGENT_VENDAS,        "host": "foundry-hosted"},
            {"name": FOUNDRY_AGENT_SUPORTE,       "host": "foundry-hosted"},
        ],
        "foundry_endpoint": FOUNDRY_PROJECT_ENDPOINT or None,
    }


async def _run_chat(message: str) -> tuple[str, list[str]]:
    result = await ORCHESTRATOR.run(message)
    text = getattr(result, "text", None) or str(result)
    tool_calls: list[str] = []
    for msg in getattr(result, "messages", []) or []:
        for c in getattr(msg, "contents", []) or []:
            name = getattr(c, "name", None) or getattr(c, "tool_name", None)
            if name:
                tool_calls.append(name)
    return text, tool_calls


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    start = time.time()
    answer, tool_calls = asyncio.run(_run_chat(req.message))
    return ChatResponse(
        answer=answer,
        tool_calls=tool_calls,
        duration_ms=int((time.time() - start) * 1000),
    )


# --------------------------------------------------------------------------- streaming endpoint
def _sse(event: dict[str, Any]) -> bytes:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode("utf-8")


@app.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    """Server-Sent Events stream of orchestration events.

    Event types pushed by the tool wrappers + this endpoint:
      • start           — { ts }
      • tool_start      — { tool, host, input }
      • tool_end        — { tool, preview }
      • done            — { answer, tool_calls, duration_ms }
      • error           — { message }
    """
    async def gen():
        bus: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        token = _event_bus.set(bus)
        t0 = time.time()
        yield _sse({"type": "start", "ts": t0, "message": req.message})

        async def runner() -> tuple[str, list[str]]:
            return await _run_chat(req.message)

        task = asyncio.create_task(runner())
        try:
            while True:
                # race: queue.get vs task done
                getter = asyncio.create_task(bus.get())
                done, _ = await asyncio.wait({getter, task}, return_when=asyncio.FIRST_COMPLETED)
                if getter in done:
                    evt = getter.result()
                    yield _sse(evt)
                else:
                    getter.cancel()
                if task.done():
                    # drain remaining events
                    while not bus.empty():
                        yield _sse(bus.get_nowait())
                    break
            answer, tool_calls = task.result()
            yield _sse({
                "type": "done",
                "answer": answer,
                "tool_calls": tool_calls,
                "duration_ms": int((time.time() - t0) * 1000),
            })
        except Exception as exc:
            log.exception("stream error")
            yield _sse({"type": "error", "message": f"{type(exc).__name__}: {exc}"})
        finally:
            _event_bus.reset(token)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    })
