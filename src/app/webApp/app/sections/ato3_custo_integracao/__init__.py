"""Custo, Quotas e Integração com Agentes Externos — A2A multi-agent demo.

Real-mode behavior
------------------
The orchestration is delegated to the sibling **mafw-agent** microservice,
which uses the **Microsoft Agent Framework** to coordinate four specialists:

  * `especialista-produtos`         — local MAF agent + Azure AI Search tool
  * `especialista-regulamentos`     — local MAF agent + Azure AI Search tool
  * `especialista-vendas`           — Foundry Hosted Agent (A2A)
  * `especialista-suporte-tecnico`  — Foundry Hosted Agent (A2A)

The MAF orchestrator decides which tool(s) to call. We render every tool the
LLM actually invoked (returned in `tool_calls`) as a turn in the chat and as a
highlighted node in the topology SVG.
"""

import logging
import os
import random
import time
from pathlib import Path
from typing import Dict, List, Optional

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from demo_mode import is_real

log = logging.getLogger("a2a")

MENU_TITLE = "Integração com Agentes Externos (A2A)"
MENU_ICON = "fa-solid fa-network-wired"

_HERE = Path(__file__).parent
_GLOBAL_TEMPLATES = Path(__file__).resolve().parents[2] / "templates"
_templates = Jinja2Templates(directory=[str(_HERE / "templates"), str(_GLOBAL_TEMPLATES)])

SECTION = {
    "title": MENU_TITLE,
    "description": "APIM AI Gateway, semantic caching e orquestração A2A real via Microsoft Agent Framework — agentes locais + Foundry Hosted Agents.",
    "eyebrow": "Operar & Governar · LIVE DEMO",
    "eyebrow_icon": "fa-solid fa-network-wired",
}

router = APIRouter(prefix="/sections/ato3_custo_integracao", tags=["ato3_custo_integracao"])


@router.get("", response_class=HTMLResponse)
async def index(request: Request):
    return _templates.TemplateResponse("index.html", {"request": request, "section": SECTION})


# ============================================================================
#  Agent topology metadata
# ============================================================================
_FOUNDRY_LABEL = "Foundry · prompt-based agent"
_LOCAL_LABEL = "Local · Microsoft Agent Framework"
_HOSTED_LABEL = "Foundry Hosted · container"

_AGENTS: Dict[str, Dict] = {
    "orchestrator": {
        "name": "Orquestrador (MAF)",
        "host": _LOCAL_LABEL,
        "model": os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-4.1-mini"),
        "icon": "fa-solid fa-route",
        "role": "Microsoft Agent Framework — decide qual(is) especialista(s) chamar via A2A.",
    },
    "especialista-produtos": {
        "name": "especialista-produtos",
        "host": _LOCAL_LABEL,
        "model": os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-4.1-mini"),
        "icon": "fa-solid fa-box",
        "role": "Catálogo de planos, fibra e dispositivos (Azure AI Search).",
    },
    "especialista-regulamentos": {
        "name": "especialista-regulamentos",
        "host": _LOCAL_LABEL,
        "model": os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-4.1-mini"),
        "icon": "fa-solid fa-scale-balanced",
        "role": "Políticas internas (RH, SegInfo, LGPD) via Azure AI Search.",
    },
    "especialista-vendas": {
        "name": os.getenv("AZURE_AI_AGENT_VENDAS", "especialista-vendas"),
        "host": _FOUNDRY_LABEL,
        "model": "gpt-4o",
        "icon": "fa-solid fa-bullhorn",
        "role": "Agente prompt-based no Microsoft Foundry — recomendação e contratação.",
    },
    "especialista-suporte-tecnico": {
        "name": os.getenv("AZURE_AI_AGENT_SUPORTE", "especialista-suporte-tecnico"),
        "host": _FOUNDRY_LABEL,
        "model": "gpt-4o-mini",
        "icon": "fa-solid fa-headset",
        "role": "Agente prompt-based no Microsoft Foundry — suporte técnico end-to-end.",
    },
    "langgraph-contoso": {
        "name": os.getenv("AZURE_AI_HOSTED_LANGGRAPH", "langgraph-contoso"),
        "host": _HOSTED_LABEL,
        "model": "gpt-4.1-mini",
        "icon": "fa-solid fa-diagram-project",
        "role": "Hosted Agent (container LangGraph) hospedado no Foundry Agent Service.",
    },
}

# Map MAF tool-call names → topology agent ids.
# MAF sanitizes Agent.as_tool() names by replacing '-' with '_', so we accept
# both spellings. @tool-decorated callables keep their underscore name as-is.
_TOOL_TO_AGENT_ID = {
    "especialista-produtos":     "especialista-produtos",
    "especialista_produtos":     "especialista-produtos",
    "especialista-regulamentos": "especialista-regulamentos",
    "especialista_regulamentos": "especialista-regulamentos",
    "call_foundry_vendas":       "especialista-vendas",
    "call_foundry_suporte":      "especialista-suporte-tecnico",
    "call_hosted_langgraph":     "langgraph-contoso",
    "langgraph-contoso":            "langgraph-contoso",
    "langgraph_contoso":            "langgraph-contoso",
}

# ============================================================================
#  Mock fallback (used when demo_mode != real, or when mafw-agent unreachable)
# ============================================================================
_MOCK_RESPONSES = {
    "especialista-produtos": (
        "Catálogo Contoso Fibra: 300Mbps SKU FB-300 R$99/mês · 500Mbps SKU FB-500 "
        "R$129/mês · 1Gbps SKU FB-1000 R$179/mês. Todos com Wi-Fi 6 e instalação gratuita."
    ),
    "especialista-regulamentos": (
        "Política POL-EMAIL-002 v2 (Segurança da Informação): e-mail corporativo é "
        "exclusivo para uso profissional; encaminhamento externo bloqueado para "
        "labels Confidential e Restricted (Purview)."
    ),
    "especialista-vendas": (
        "Posso fechar o Contoso Fibra 500Mbps por R$129/mês com Wi-Fi 6 incluso, "
        "se você confirmar CEP e melhor horário de instalação."
    ),
    "especialista-suporte-tecnico": (
        "Modem com luz vermelha = sem sinal óptico. Passos: 1) verifique o cabo "
        "de fibra na ONT, 2) reinicie o modem por 30s, 3) se persistir, abro "
        "chamado técnico nível 2 com SLA de 24h."
    ),
    "langgraph-contoso": (
        "Visão consolidada (langgraph): Contoso Fibra tem 3 tiers — 300 / 500 / "
        "1000 Mbps a R$99 / R$129 / R$179 por mês. Todos incluem Wi-Fi 6, "
        "instalação grátis e fidelidade de 12 meses. Cobertura em 4.000+ municípios."
    ),
}


def _mock_route(query: str) -> str:
    q = query.lower()
    # Multi-agent intent: contratar + cancelamento/política → vendas (primário)
    # mas a mensagem cita ambos; mantemos vendas como rota principal.
    if "langgraph" in q:
        return "langgraph-contoso"
    if any(w in q for w in ["política", "politica", "lgpd", "rh", "segurança", "seguranca", "regulamento", "uso aceitável", "uso aceitavel", "cancelamento"]):
        # "cancelamento" cai em regulamentos só quando não tem "contratar"
        if "contratar" in q or "fechar" in q:
            return "especialista-vendas"
        return "especialista-regulamentos"
    if any(w in q for w in ["liste sku", "sku", "catálogo", "catalogo", "quais planos", "lista de planos"]):
        return "especialista-produtos"
    if any(w in q for w in ["modem", "luz vermelha", "wi-fi", "wifi", "internet caiu", "não funciona", "nao funciona", "erro", "senha", "5g"]):
        return "especialista-suporte-tecnico"
    if any(w in q for w in ["fatura", "boleto", "pagar", "pix", "débito", "debito", "plano", "preço", "preco", "oferta", "contratar", "fechar", "fibra"]):
        return "especialista-vendas"
    return "especialista-produtos"


# ============================================================================
#  Models
# ============================================================================
class A2ARequest(BaseModel):
    message: str
    enable_caching: bool = True


class AgentTurn(BaseModel):
    agent_id: str
    agent_name: str
    model: str
    host: str
    icon: str
    role: str
    content: str
    duration_ms: int


class TraceStep(BaseModel):
    step: int
    agent: str
    action: str
    detail: str
    duration_ms: int
    cached: bool = False


class A2AResponse(BaseModel):
    final_response: str
    routed_to: str
    agents_called: List[str]
    turns: List[AgentTurn]
    trace: List[TraceStep]
    total_ms: int
    cache_hit: bool
    source: str = "mock"


_CACHE: Dict[str, "A2AResponse"] = {}


# ============================================================================
#  Real-mode helper — delegate orchestration to sibling mafw-agent service
# ============================================================================
def _call_mafw_orchestrator(message: str) -> Optional[Dict]:
    """POST /chat on the MAFW microservice. Returns dict or None on failure."""
    url = os.getenv("MAFW_AGENT_URL", "http://mafw-agent:8091").rstrip("/") + "/chat"
    try:
        with httpx.Client(timeout=90.0) as client:
            r = client.post(url, json={"message": message})
            r.raise_for_status()
            return r.json()
    except Exception as exc:
        log.warning("[a2a] mafw-agent unreachable: %s", exc)
        return None


def _agent_turn(agent_id: str, content: str, duration_ms: int) -> AgentTurn:
    meta = _AGENTS.get(agent_id, _AGENTS["orchestrator"])
    return AgentTurn(
        agent_id=agent_id,
        agent_name=meta["name"], model=meta["model"], host=meta["host"],
        icon=meta["icon"], role=meta["role"],
        content=content, duration_ms=duration_ms,
    )


# ============================================================================
#  API
# ============================================================================
@router.get("/api/agents")
async def list_agents():
    return {"agents": [{"id": k, **v} for k, v in _AGENTS.items()]}


@router.post("/api/orchestrate", response_model=A2AResponse)
async def orchestrate(payload: A2ARequest, request: Request) -> A2AResponse:
    t0 = time.time()
    trace: List[TraceStep] = []
    turns: List[AgentTurn] = []
    cache_key = payload.message.lower().strip()
    use_real = is_real(request)

    # ---- 1. APIM gateway + semantic cache ---------------------------------
    if payload.enable_caching and cache_key in _CACHE:
        cached = _CACHE[cache_key]
        trace.append(TraceStep(
            step=1, agent="APIM AI Gateway",
            action="semantic cache HIT",
            detail=f"key={cache_key[:40]}…", duration_ms=8, cached=True,
        ))
        return A2AResponse(
            final_response=cached.final_response,
            routed_to=cached.routed_to,
            agents_called=cached.agents_called,
            turns=cached.turns,
            trace=trace + cached.trace,
            total_ms=int((time.time() - t0) * 1000),
            cache_hit=True,
            source=cached.source,
        )

    trace.append(TraceStep(
        step=1, agent="APIM AI Gateway",
        action="semantic cache MISS · token bucket OK",
        detail="passing through", duration_ms=12,
    ))

    # ---- 2. Real path: delegate to MAFW orchestrator ----------------------
    if use_real:
        mafw = _call_mafw_orchestrator(payload.message)
        if mafw is not None and mafw.get("answer"):
            answer = mafw["answer"]
            tool_calls = mafw.get("tool_calls", []) or []
            mafw_dur = int(mafw.get("duration_ms", 0))

            # Map tool_calls → topology agent ids (preserve order, dedupe)
            agents_called: List[str] = []
            for tc in tool_calls:
                aid = _TOOL_TO_AGENT_ID.get(tc)
                if aid and aid not in agents_called:
                    agents_called.append(aid)

            # Orchestrator turn (announce routing)
            if agents_called:
                names = ", ".join(_AGENTS[a]["name"] for a in agents_called)
                announce = (
                    f"Microsoft Agent Framework rotou para: **{names}** "
                    f"({len(agents_called)} especialista(s) via A2A)."
                )
            else:
                announce = (
                    "Microsoft Agent Framework respondeu sem invocar especialistas "
                    "(resposta direta pelo orquestrador)."
                )
            turns.append(_agent_turn(
                "orchestrator", announce, max(50, mafw_dur // (len(agents_called) + 1))
            ))
            trace.append(TraceStep(
                step=2, agent="Orchestrator (MAF)",
                action="route via A2A",
                detail=f"tool_calls={tool_calls or '∅'}", duration_ms=120,
            ))

            # Specialist turns — surface consolidated answer on the LAST specialist
            step_n = 3
            for i, aid in enumerate(agents_called):
                is_last = (i == len(agents_called) - 1)
                content = answer if is_last else (
                    "_(invocado pelo orquestrador via A2A — resposta consolidada abaixo)_"
                )
                per_dur = mafw_dur // max(1, len(agents_called))
                turns.append(_agent_turn(aid, content, per_dur))
                trace.append(TraceStep(
                    step=step_n, agent=_AGENTS[aid]["name"],
                    action=f"invoke ({_AGENTS[aid]['model']})",
                    detail=f"A2A · host={_AGENTS[aid]['host']}", duration_ms=per_dur,
                ))
                step_n += 1

            if not agents_called:
                turns.append(_agent_turn("orchestrator", answer, mafw_dur))

            response = A2AResponse(
                final_response=answer,
                routed_to=agents_called[0] if agents_called else "orchestrator",
                agents_called=agents_called or ["orchestrator"],
                turns=turns,
                trace=trace,
                total_ms=int((time.time() - t0) * 1000),
                cache_hit=False,
                source="real",
            )
            if payload.enable_caching:
                _CACHE[cache_key] = response
            return response
        # else fall through to mock

    # ---- 3. Mock fallback -------------------------------------------------
    time.sleep(0.9 + random.uniform(0, 0.3))
    target = _mock_route(payload.message)
    orch_meta = _AGENTS["orchestrator"]
    turns.append(AgentTurn(
        agent_id="orchestrator",
        agent_name=orch_meta["name"], model=orch_meta["model"],
        host=orch_meta["host"], icon=orch_meta["icon"], role=orch_meta["role"],
        content=(
            f"Detectei que essa pergunta é melhor respondida pelo "
            f"**{_AGENTS[target]['name']}** ({_AGENTS[target]['host']}). "
            f"Encaminhando via A2A protocol."
        ),
        duration_ms=180,
    ))
    trace.append(TraceStep(
        step=2, agent="Orchestrator",
        action="route via A2A",
        detail=f"→ {_AGENTS[target]['name']}", duration_ms=180,
    ))

    time.sleep(1.8 + random.uniform(0, 0.7))
    primary_response = _MOCK_RESPONSES[target]
    primary_dur = 420 + random.randint(0, 100)
    turns.append(_agent_turn(target, primary_response, primary_dur))
    trace.append(TraceStep(
        step=3, agent=_AGENTS[target]["name"],
        action=f"invoke ({_AGENTS[target]['model']})",
        detail="A2A · resposta local", duration_ms=primary_dur,
    ))

    response = A2AResponse(
        final_response=primary_response,
        routed_to=target,
        agents_called=[target],
        turns=turns,
        trace=trace,
        total_ms=int((time.time() - t0) * 1000),
        cache_hit=False,
        source="mock",
    )
    if payload.enable_caching:
        _CACHE[cache_key] = response
    return response


# ============================================================================
#  STREAMING (Server-Sent Events) — proxies mafw-agent /chat/stream and enriches
#  tool_start/tool_end events with agent_id + topology metadata so the
#  front-end can highlight diagram nodes/edges in real time.
# ============================================================================
@router.post("/api/orchestrate/stream")
async def orchestrate_stream(payload: A2ARequest, request: Request):
    use_real = is_real(request)

    # Fallback to mock when not in real mode: emit a small synthetic SSE stream.
    if not use_real:
        async def mock_gen():
            import asyncio as _a
            import json as _j

            q = payload.message.lower()
            # Multi-agent intent: contratar + cancelamento → vendas + regulamentos
            is_multi = ("contratar" in q or "fechar" in q) and any(
                w in q for w in ["cancelamento", "política", "politica", "regulamento", "fidelidade", "rescisão", "rescisao"]
            )

            yield f"data: {_j.dumps({'type':'start','message':payload.message})}\n\n"
            await _a.sleep(1.0)

            if is_multi:
                targets = ["especialista-vendas", "especialista-regulamentos"]
                previews = {
                    "especialista-vendas": (
                        "Posso fechar o Contoso Fibra 500Mbps por R$129/mês com Wi-Fi 6 "
                        "incluso. Para encerrar a contratação preciso do CEP e melhor "
                        "horário de instalação."
                    ),
                    "especialista-regulamentos": (
                        "Política POL-CANC-014: cancelamento sem multa após 12 meses de "
                        "fidelidade. Antes disso, multa proporcional (R$40/mês restante). "
                        "Solicitação por app, telefone ou loja com efeito em até 2 dias úteis."
                    ),
                }
                # fan-out — both tool_start emitted close together
                for t in targets:
                    meta = _AGENTS[t]
                    yield f"data: {_j.dumps({'type':'tool_start','tool':t,'agent_id':t,'agent_name':meta['name'],'host':meta['host'],'icon':meta['icon'],'input':payload.message})}\n\n"
                    await _a.sleep(0.25)
                await _a.sleep(1.6)
                # tool_end — vendas first, then regulamentos
                for t in targets:
                    yield f"data: {_j.dumps({'type':'tool_end','tool':t,'agent_id':t,'preview':previews[t]})}\n\n"
                    await _a.sleep(0.9)
                final = (
                    "**Resposta consolidada (2 agentes):**\n\n"
                    "• **Vendas** — " + previews["especialista-vendas"] + "\n\n"
                    "• **Regulamentos** — " + previews["especialista-regulamentos"]
                )
                yield f"data: {_j.dumps({'type':'done','answer':final,'tool_calls':targets,'duration_ms':3800,'source':'mock'})}\n\n"
                return

            target = _mock_route(payload.message)
            meta = _AGENTS[target]
            yield f"data: {_j.dumps({'type':'tool_start','tool':target,'agent_id':target,'agent_name':meta['name'],'host':meta['host'],'icon':meta['icon'],'input':payload.message})}\n\n"
            await _a.sleep(2.0)
            preview = _MOCK_RESPONSES[target][:240]
            yield f"data: {_j.dumps({'type':'tool_end','tool':target,'agent_id':target,'preview':preview})}\n\n"
            await _a.sleep(1.0)
            yield f"data: {_j.dumps({'type':'done','answer':_MOCK_RESPONSES[target],'tool_calls':[target],'duration_ms':1100,'source':'mock'})}\n\n"
        return StreamingResponse(
            mock_gen(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    mafw_url = os.getenv("MAFW_AGENT_URL", "http://mafw-agent:8091")

    async def proxy_gen():
        import json as _j
        client = httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=10.0))
        try:
            async with client.stream(
                "POST",
                f"{mafw_url}/chat/stream",
                json={"message": payload.message},
            ) as resp:
                if resp.status_code >= 400:
                    body = await resp.aread()
                    yield f"data: {_j.dumps({'type':'error','status':resp.status_code,'detail':body.decode('utf-8','replace')[:600]})}\n\n"
                    return
                async for raw_line in resp.aiter_lines():
                    if not raw_line:
                        # blank line = SSE event separator; forward as-is
                        yield "\n"
                        continue
                    if not raw_line.startswith("data:"):
                        yield raw_line + "\n"
                        continue
                    data_str = raw_line[5:].strip()
                    try:
                        evt = _j.loads(data_str)
                    except Exception:
                        yield raw_line + "\n\n"
                        continue
                    # Enrich tool events with agent metadata
                    if evt.get("type") in ("tool_start", "tool_end"):
                        tool = evt.get("tool") or ""
                        agent_id = _TOOL_TO_AGENT_ID.get(tool)
                        if agent_id and agent_id in _AGENTS:
                            meta = _AGENTS[agent_id]
                            evt["agent_id"] = agent_id
                            evt["agent_name"] = meta["name"]
                            evt["icon"] = meta["icon"]
                            if "host" not in evt:
                                evt["host"] = meta["host"]
                    yield f"data: {_j.dumps(evt, ensure_ascii=False)}\n\n"
        except httpx.HTTPError as exc:
            yield f"data: {_j.dumps({'type':'error','detail':f'mafw-agent unreachable: {exc.__class__.__name__}: {exc}'})}\n\n"
        finally:
            await client.aclose()

    return StreamingResponse(
        proxy_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ============================================================================
#  MCP Tools governadas pelo APIM AI Gateway (req 1.5.2)
# ============================================================================
# Demo determinística: toggle ON → request passa pelo gateway corporativo
# (auth, rate-limit, content-safety, audit). OFF → chamada direta sem governança.

_MCP_TOOLS: Dict[str, Dict] = {
    "Salesforce.lookup_account": {
        "label": "Salesforce · lookup_account",
        "icon": "fa-brands fa-salesforce",
        "args_preview": '{"account_name": "Contoso Empresas RJ"}',
        "result": {
            "account_id": "001Hp00002kQz3xIAC",
            "name": "Contoso Empresas RJ",
            "owner": "ana.lima@contoso.com.br",
            "arr_brl": 12_400_000,
            "tier": "Enterprise",
        },
    },
    "ServiceNow.create_incident": {
        "label": "ServiceNow · create_incident",
        "icon": "fa-solid fa-headset",
        "args_preview": '{"category": "telecom-fibra", "priority": 2, "short_description": "Cliente sem sinal"}',
        "result": {
            "incident_id": "INC0012345",
            "status": "new",
            "assignment_group": "NOC-Fibra-SP",
            "sla_minutes": 240,
        },
    },
}

# Stable token preview (NOT a real token — masked mock JWT-ish header)
_MOCK_TOKEN_PREVIEW = "eyJhbGciOiJSUzI1NiIsImtpZCI6ImFwaW0tdml2by0yMDI1In0...sig"

_MCP_RATE_LIMIT_QUOTA = 100
_mcp_rate_counter = {"used": 42}  # demo state, persisted in-process


class MCPInvokeRequest(BaseModel):
    tool: str
    gateway: bool = True


@router.get("/api/mcp/tools")
async def list_mcp_tools():
    return {
        "tools": [
            {"id": k, "label": v["label"], "icon": v["icon"], "args_preview": v["args_preview"]}
            for k, v in _MCP_TOOLS.items()
        ]
    }


@router.post("/api/mcp/invoke")
async def mcp_invoke(payload: MCPInvokeRequest):
    tool = _MCP_TOOLS.get(payload.tool)
    if not tool:
        return {"ok": False, "error": f"unknown tool: {payload.tool}"}

    # increment demo rate counter
    _mcp_rate_counter["used"] = min(_MCP_RATE_LIMIT_QUOTA, _mcp_rate_counter["used"] + 1)
    used = _mcp_rate_counter["used"]

    trace: List[Dict] = []
    if payload.gateway:
        trace.append({"step": "auth",           "ms": 12,  "status": "ok",
                      "detail": f"Bearer {_MOCK_TOKEN_PREVIEW}"})
        trace.append({"step": "rate-limit",     "ms": 3,   "status": "ok",
                      "detail": f"{used}/{_MCP_RATE_LIMIT_QUOTA} req/min · tenant=contoso-prod"})
        trace.append({"step": "content-safety", "ms": 18,  "status": "ok",
                      "detail": "no PII / no jailbreak detected"})
        trace.append({"step": "invoke",         "ms": random.randint(180, 420), "status": "ok",
                      "detail": f"tool={payload.tool}"})
        trace.append({"step": "audit",          "ms": 5,   "status": "logged",
                      "detail": "azure-log-analytics · workspace=contoso-ai-audit"})
    else:
        # bypassed governance — only the raw tool call happens
        trace.append({"step": "invoke",         "ms": random.randint(180, 420), "status": "ok",
                      "detail": f"DIRECT (no gateway) · tool={payload.tool}"})

    total_ms = sum(s["ms"] for s in trace)

    return {
        "ok": True,
        "tool": payload.tool,
        "gateway": payload.gateway,
        "trace": trace,
        "total_ms": total_ms,
        "token_preview": _MOCK_TOKEN_PREVIEW if payload.gateway else None,
        "rate_limit": {"used": used, "quota": _MCP_RATE_LIMIT_QUOTA,
                       "remaining": _MCP_RATE_LIMIT_QUOTA - used},
        "result": tool["result"],
        "audit_entry": {
            "timestamp": int(time.time()),
            "tool": payload.tool,
            "via_gateway": payload.gateway,
            "status": "ok",
        } if payload.gateway else None,
    }


__all__ = ["router", "MENU_TITLE", "MENU_ICON"]
