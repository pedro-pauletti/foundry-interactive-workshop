"""Multi-Agentes com Microsoft Agent Framework (MAF) e Foundry Workflows.

Demo visual dos 5 padrões de orquestração do MAF (`Sequential`, `Concurrent`,
`Handoff`, `GroupChat`, `Magentic`) + Foundry Workflows declarativos (YAML).

Esta primeira passada é **visual-only**: trocar o padrão re-renderiza o diagrama
SVG e a ordem dos eventos. Quando `?live=1`, ainda usamos o `mafw-agent`
existente como backend para a mensagem (o orquestrador real continuará rodando
o padrão atual dele — refactor para usar os builders do MAF é follow-up).
"""

from __future__ import annotations

import asyncio
import json
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

from demo_mode import is_real  # type: ignore

log = logging.getLogger("multiagentes")

MENU_TITLE = "Multi-Agentes com MAF e Foundry Workflows"
MENU_ICON = "fa-solid fa-sitemap"

_HERE = Path(__file__).parent
_GLOBAL_TEMPLATES = Path(__file__).resolve().parents[2] / "templates"
_templates = Jinja2Templates(directory=[str(_HERE / "templates"), str(_GLOBAL_TEMPLATES)])

SECTION = {
    "title": MENU_TITLE,
    "description": (
        "Padrões de orquestração do Microsoft Agent Framework + Foundry Workflows declarativos — "
        "escolha o padrão e veja a topologia em tempo real."
    ),
    "eyebrow": "Construir · LIVE DEMO",
    "eyebrow_icon": "fa-solid fa-sitemap",
}

router = APIRouter(prefix="/sections/ato1_multiagentes", tags=["ato1_multiagentes"])


# ============================================================================
#  Patterns metadata — descreve cada padrão MAF e o layout que o diagrama usa
# ============================================================================
PATTERNS: Dict[str, Dict] = {
    "sequential": {
        "id": "sequential",
        "name": "Sequential",
        "icon": "fa-solid fa-arrow-right-long",
        "tagline": "Pipeline: cada agente recebe a saída do anterior.",
        "when": "Pipeline de etapas dependentes — extrai → resume → classifica.",
        "builder": "SequentialBuilder().participants([a, b, c]).build()",
        "ordering": ["produtos", "regulamentos", "vendas"],
    },
    "concurrent": {
        "id": "concurrent",
        "name": "Concurrent",
        "icon": "fa-solid fa-grip-vertical",
        "tagline": "Fan-out: a mesma entrada vai a todos em paralelo; o orquestrador agrega.",
        "when": "Reduzir latência quando os agentes são independentes (vários LLMs opinando).",
        "builder": "ConcurrentBuilder().participants([a, b, c]).build()",
        "ordering": ["produtos", "regulamentos", "vendas", "suporte"],
    },
    "handoff": {
        "id": "handoff",
        "name": "Handoff",
        "icon": "fa-solid fa-shuffle",
        "tagline": "Triagem: o agente atual decide passar o bastão para outro com mais expertise.",
        "when": "Atendimento ao cliente — triagem genérica passa para especialista certo.",
        "builder": "HandoffBuilder().add_handoff(from_=a, to=b).build()",
        "ordering": ["orchestrator", "vendas"],
    },
    "group_chat": {
        "id": "group_chat",
        "name": "Group Chat",
        "icon": "fa-solid fa-comments",
        "tagline": "Mesa redonda: agentes conversam até atingir consenso ou critério de parada.",
        "when": "Decisões colaborativas, debates, refinamento iterativo de soluções.",
        "builder": "GroupChatBuilder().participants([a, b, c]).termination(...).build()",
        "ordering": ["produtos", "regulamentos", "vendas", "suporte"],
    },
    "magentic": {
        "id": "magentic",
        "name": "Magentic",
        "icon": "fa-solid fa-route",
        "tagline": "Orquestrador-LLM no centro decide dinamicamente quem chamar (tools).",
        "when": "Tarefas abertas — usuário pede algo amplo e o orquestrador roteia em tempo real.",
        "builder": "MagenticBuilder().orchestrator(o).participants([a, b]).build()",
        "ordering": ["produtos", "vendas"],
    },
}

# Agentes participantes — reusam a topologia já existente em ato3_custo_integracao
AGENTS: Dict[str, Dict] = {
    "orchestrator": {
        "id": "orchestrator",
        "name": "Orquestrador (MAF)",
        "kind": "orchestrator",
        "icon": "fa-solid fa-route",
        "host": "Local · Microsoft Agent Framework",
    },
    "produtos": {
        "id": "produtos",
        "name": "agente-produtos",
        "kind": "local",
        "icon": "fa-solid fa-box",
        "host": "Local · MAF + Azure Search",
    },
    "regulamentos": {
        "id": "regulamentos",
        "name": "agente-regulamentos",
        "kind": "local",
        "icon": "fa-solid fa-scale-balanced",
        "host": "Local · MAF + Azure Search",
    },
    "vendas": {
        "id": "vendas",
        "name": "agente-vendas",
        "kind": "foundry",
        "icon": "fa-solid fa-bullhorn",
        "host": "Foundry · prompt-based",
    },
    "suporte": {
        "id": "suporte",
        "name": "agente-suporte",
        "kind": "foundry",
        "icon": "fa-solid fa-headset",
        "host": "Foundry · prompt-based",
    },
}


# ============================================================================
#  Foundry Workflows YAML sample — usado no bloco "Foundry Workflows"
# ============================================================================
FOUNDRY_WORKFLOW_YAML = """# contoso-atendimento/workflow.yaml — declarative agent workflow
name: contoso-atendimento
description: Triagem multi-agente de atendimento Contoso
agents:
  - id: agente-triagem
    model: gpt-4.1-mini
    instructions: Classifique a pergunta em [vendas, suporte, regulamentos].
  - id: agente-vendas
    model: gpt-4.1
    instructions: Recomende plano com base no perfil do cliente.
  - id: agente-suporte
    model: gpt-4.1-mini
    instructions: Resolva problemas técnicos passo a passo.

flow:
  - call: agente-triagem
    output: intent
  - branch:
      on: intent
      cases:
        vendas:    { call: agente-vendas }
        suporte:   { call: agente-suporte }
        default:   { respond: "Encaminhando para atendimento humano." }
"""

MAF_PYTHON_SAMPLE = """# Microsoft Agent Framework — pro-code, padrões reais
from agent_framework import SequentialBuilder, ConcurrentBuilder, HandoffBuilder
from agent_framework.openai import OpenAIChatCompletionClient

client = OpenAIChatCompletionClient(...)
agente_produtos     = Agent(name="agente-produtos", client=client, tools=[search_catalog])
agente_regulamentos = Agent(name="agente-regulamentos", client=client, tools=[search_policies])
agente_vendas       = Agent(name="agente-vendas", client=client)

# 1. Sequential — pipeline determinístico
pipeline = SequentialBuilder().participants([agente_produtos, agente_regulamentos, agente_vendas]).build()

# 2. Concurrent — fan-out paralelo
broadcast = ConcurrentBuilder().participants([agente_produtos, agente_regulamentos]).build()

# 3. Handoff — triagem dinâmica
triage = (
    HandoffBuilder()
        .add_handoff(from_=agente_produtos, to=agente_vendas)
        .add_handoff(from_=agente_vendas, to=agente_produtos)
        .build()
)
"""


# ============================================================================
#  Models
# ============================================================================
class RunRequest(BaseModel):
    message: str
    pattern: str = "magentic"


class TraceEvent(BaseModel):
    type: str  # start | hop | tool_start | tool_end | done
    agent_id: Optional[str] = None
    detail: Optional[str] = None
    ts_ms: int = 0


# ============================================================================
#  Routes
# ============================================================================
@router.get("", response_class=HTMLResponse)
async def index(request: Request):
    return _templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "section": SECTION,
            "patterns": list(PATTERNS.values()),
            "agents": list(AGENTS.values()),
            "foundry_workflow_yaml": FOUNDRY_WORKFLOW_YAML,
            "maf_python_sample": MAF_PYTHON_SAMPLE,
        },
    )


@router.get("/api/patterns")
async def list_patterns():
    """Expor metadata dos padrões para o front-end re-renderizar diagramas."""
    return {"patterns": PATTERNS, "agents": AGENTS}


_MOCK_REPLIES = {
    "sequential": (
        "Resultado do pipeline:\n1) agente-produtos identificou Contoso Fibra 500Mbps.\n"
        "2) agente-regulamentos validou política de fidelização.\n"
        "3) agente-vendas formatou a oferta final."
    ),
    "concurrent": (
        "Três opiniões agregadas:\n• agente-produtos: Contoso Fibra 500Mbps.\n"
        "• agente-regulamentos: política POL-VEN-007 permite oferta.\n"
        "• agente-vendas: desconto promocional aplicável."
    ),
    "handoff": (
        "[agente-triagem→agente-vendas] Identifiquei intenção de contratação. "
        "Encaminhei para o agente-vendas que fechou a proposta."
    ),
    "group_chat": (
        "Discussão (3 turnos):\n— agente-produtos propôs plano A.\n— agente-vendas sugeriu plano B com desconto.\n"
        "— agente-regulamentos validou plano B. Consenso: **plano B**."
    ),
    "magentic": (
        "Magentic orquestrou dinamicamente: chamei `agente-produtos` para listar opções e em seguida "
        "`agente-vendas` para fechar — resposta final consolidada abaixo."
    ),
}


@router.post("/api/run/stream")
async def run_stream(payload: RunRequest, request: Request):
    """SSE: emite eventos visualizando o padrão escolhido.

    Implementação visual-only: os eventos seguem a `ordering` declarada por
    padrão e disparam `tool_start`/`tool_end` no mesmo formato consumido pela
    UI a2a (compatível com o JS de `ato3_custo_integracao`).
    """
    pattern_id = (payload.pattern or "magentic").lower()
    pattern = PATTERNS.get(pattern_id, PATTERNS["magentic"])
    use_real = is_real(request)
    t0 = time.time()

    async def gen():
        # 1) start
        yield _sse({"type": "start", "pattern": pattern_id, "message": payload.message})
        await asyncio.sleep(0.35)

        # 2) orchestrator hop (sempre)
        yield _sse({
            "type": "hop",
            "agent_id": "orchestrator",
            "detail": f"padrão={pattern['name']}",
            "ts_ms": int((time.time() - t0) * 1000),
        })
        await asyncio.sleep(0.45)

        # 3) per-pattern emissão
        ordering: List[str] = list(pattern["ordering"])

        if pattern_id == "concurrent":
            # fan-out: dispara todos os tool_start praticamente juntos
            for aid in ordering:
                if aid == "orchestrator":
                    continue
                meta = AGENTS[aid]
                yield _sse({
                    "type": "tool_start", "agent_id": aid,
                    "agent_name": meta["name"], "host": meta["host"], "icon": meta["icon"],
                    "input": payload.message[:120],
                })
                await asyncio.sleep(0.08)
            await asyncio.sleep(1.0 + random.uniform(0, 0.4))
            for aid in ordering:
                if aid == "orchestrator":
                    continue
                yield _sse({
                    "type": "tool_end", "agent_id": aid,
                    "preview": f"(opinião de {AGENTS[aid]['name']})",
                })
                await asyncio.sleep(0.05)

        elif pattern_id == "group_chat":
            # roda 2 voltas
            for turn in range(2):
                for aid in ordering:
                    meta = AGENTS[aid]
                    yield _sse({
                        "type": "tool_start", "agent_id": aid,
                        "agent_name": meta["name"], "host": meta["host"], "icon": meta["icon"],
                        "input": f"turno {turn+1}",
                    })
                    await asyncio.sleep(0.35 + random.uniform(0, 0.2))
                    yield _sse({
                        "type": "tool_end", "agent_id": aid,
                        "preview": f"contribuição turno {turn+1}",
                    })
                    await asyncio.sleep(0.15)

        else:
            # sequential | handoff | magentic — encadeado
            for aid in ordering:
                if aid == "orchestrator":
                    continue
                meta = AGENTS[aid]
                yield _sse({
                    "type": "tool_start", "agent_id": aid,
                    "agent_name": meta["name"], "host": meta["host"], "icon": meta["icon"],
                    "input": payload.message[:120],
                })
                await asyncio.sleep(0.55 + random.uniform(0, 0.3))
                yield _sse({
                    "type": "tool_end", "agent_id": aid,
                    "preview": f"(resposta de {meta['name']})",
                })
                await asyncio.sleep(0.2)

        # 4) done — tenta backend real, senão usa mock
        answer = None
        if use_real:
            answer = await _call_mafw(payload.message)
        if not answer:
            answer = _MOCK_REPLIES.get(pattern_id, _MOCK_REPLIES["magentic"])

        yield _sse({
            "type": "done",
            "answer": answer,
            "pattern": pattern_id,
            "duration_ms": int((time.time() - t0) * 1000),
            "source": "real" if use_real and answer else "mock",
        })

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _sse(payload: Dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def _call_mafw(message: str) -> Optional[str]:
    url = os.getenv("MAFW_AGENT_URL", "http://mafw-agent:8091").rstrip("/") + "/chat"
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(url, json={"message": message})
            r.raise_for_status()
            data = r.json()
            return data.get("answer")
    except Exception as exc:
        log.warning("[multiagentes] mafw-agent unreachable: %s", exc)
        return None
