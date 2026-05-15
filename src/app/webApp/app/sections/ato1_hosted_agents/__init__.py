"""Hosted Agents — Foundry-managed runtime for production agents."""

import logging
import os
import asyncio
import random
import time
from pathlib import Path
from typing import Literal, Optional

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from azure_clients import get_chat_deployment, get_openai_client, get_project_client
from demo_mode import is_real
from industry import get_pack

log = logging.getLogger("hosted_agents")

MENU_TITLE = "Hosted Agents"
MENU_ICON = "fa-solid fa-server"

_HERE = Path(__file__).parent
_GLOBAL_TEMPLATES = Path(__file__).resolve().parents[2] / "templates"
_templates = Jinja2Templates(directory=[str(_HERE / "templates"), str(_GLOBAL_TEMPLATES)])

SECTION = {
    "title": MENU_TITLE,
    "description": "Publicar o agente como Hosted Agent do Foundry: runtime gerenciado, "
                   "endpoint pronto, identidade no Entra e zero infraestrutura para operar.",
    "eyebrow": "Construir · LIVE DEMO",
    "eyebrow_icon": "fa-solid fa-server",
}


def _code_block(lang: str, code: str, caption: str = "") -> str:
    import html as _html
    safe = _html.escape(code)
    cap = f'<div class="code-caption">{caption}</div>' if caption else ""
    return f'{cap}<pre class="code-block"><code class="language-{lang}">{safe}</code></pre>'


CREATE_HOSTED_PY = '''# Publica um agente local (MAF / LangGraph / código próprio) como
# Hosted Agent no Foundry — o Foundry roda o SEU container.
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    HostedAgentDefinition,
    ProtocolVersionRecord,
    AgentProtocol,
)

project = AIProjectClient(
    endpoint="https://<seu-projeto>.services.ai.azure.com/api/projects/<projeto>",
    credential=DefaultAzureCredential(),
    allow_preview=True,
)

# 1) Build & push da imagem (linux/amd64) para o ACR ligado ao projeto Foundry
#    docker build --platform linux/amd64 -t <acr>.azurecr.io/mafw-contoso:v1 .
#    docker push <acr>.azurecr.io/mafw-contoso:v1
#    O container precisa expor o protocolo Responses (lib azure-ai-agentserver-responses)
#    na porta 8088 — o Foundry chama /readiness e /v1/responses.

# 2) Cria a versão do hosted agent apontando para a imagem
agent = project.agents.create_version(
    agent_name="mafw-contoso",
    definition=HostedAgentDefinition(
        container_protocol_versions=[
            ProtocolVersionRecord(protocol=AgentProtocol.RESPONSES, version="1.0.0"),
        ],
        cpu="1",
        memory="2Gi",
        image="<acr>.azurecr.io/mafw-contoso:v1",
        environment_variables={
            "MODEL_DEPLOYMENT_NAME": "gpt-4.1-mini",
            "AZURE_SEARCH_ENDPOINT":  "<search-endpoint>",
        },
    ),
)
print("Hosted agent criado:", agent.agent_name, agent.agent_version, agent.status)
'''

INVOKE_HOSTED_PY = '''# Invocar o Hosted Agent — Foundry expõe um endpoint OpenAI Responses
# por agente; sessões, scaling, RBAC e observabilidade são gerenciados.
openai_client = project.get_openai_client(agent_name="mafw-contoso")

response = openai_client.responses.create(
    input="Quais planos de fibra para home office?",
)
print(response.output_text)

# Sessão multi-turn (estado gerenciado pelo Foundry)
session_id = response.model_extra.get("agent_session_id")
followup = openai_client.responses.create(
    input="E para upload pesado?",
    extra_body={"agent_session_id": session_id},
)
print(followup.output_text)
'''


BLOCK_O_QUE_E = (
    "<p>Um <strong>Hosted Agent</strong> é o <em>seu próprio código de agente</em> "
    "(MAF, LangGraph, LangChain, Semantic Kernel ou framework próprio) empacotado "
    "como container e <strong>hospedado pelo Foundry Agent Service</strong>. "
    "Diferente dos <em>prompt-based agents</em> (criados no Foundry Portal só com "
    "modelo + instruções + tools), o Hosted Agent roda <strong>orquestração custom</strong> — "
    "qualquer loop, planner ou multi-agente que você programar.</p>"
    "<ul>"
    "<li><strong>Container Linux/amd64 na porta 8088</strong> que fala o protocolo "
    "<em>Responses</em> ou <em>Invocations</em> (lib <code>azure-ai-agentserver-responses</code>).</li>"
    "<li><strong>Imagem em ACR conectado ao projeto Foundry</strong> — o Foundry puxa, "
    "escala, dá rollback por versão e expõe um endpoint estável.</li>"
    "<li><strong>Sessões gerenciadas</strong> (<code>project.beta.agents.create_session</code>) "
    "com isolamento por <em>isolation_key</em> — substitui seu storage de threads.</li>"
    "<li><strong>Identidade no Entra:</strong> a Managed Identity do projeto autentica "
    "o pull no ACR e injeta variáveis (<code>FOUNDRY_PROJECT_ENDPOINT</code>, "
    "<code>FOUNDRY_AGENT_NAME</code>, <code>APPLICATIONINSIGHTS_CONNECTION_STRING</code>).</li>"
    "<li><strong>Mesmo endpoint OpenAI Responses</strong> — o cliente é o mesmo do Azure OpenAI: "
    "<code>project.get_openai_client(agent_name=...).responses.create(input=...)</code>.</li>"
    "</ul>"
    "<p class=\"muted\" style=\"font-size:13px;\">"
    "<i class=\"fa-solid fa-circle-info\"></i> "
    "Os agentes <code>orquestrador-atendimento</code>, <code>especialista-vendas</code>, "
    "<code>especialista-produtos</code> que aparecem no Foundry Portal são "
    "<strong>prompt-based agents</strong>, não hosted agents. "
    "Os hosted agents desta demo são os containers <code>mafw-contoso</code> e "
    "<code>langgraph-contoso</code> — código local da Contoso rodando dentro do Foundry."
    "</p>"
)

BLOCK_HOSTED_VS_SELF = (
    "<p>O mesmo container pode rodar em três regimes; o Hosted Agent é o caminho "
    "managed quando você quer o controle do código mas não quer operar o runtime.</p>"
    "<table class=\"req-table\" style=\"margin-top:10px;\">"
    "<thead><tr><th>Aspecto</th>"
    "<th>Prompt-based Agent</th>"
    "<th>Hosted Agent (seu container no Foundry)</th>"
    "<th>Self-hosted (você opera o runtime)</th></tr></thead>"
    "<tbody>"
    "<tr><td>O que é</td>"
    "<td>Modelo + instruções + tools no Portal</td>"
    "<td>Sua imagem MAF/LangGraph rodando no Foundry</td>"
    "<td>Sua imagem rodando em ACA/AKS/Functions</td></tr>"
    "<tr><td>Orquestração custom</td>"
    "<td>Limitada (tools nativas)</td>"
    "<td>Total — qualquer Python</td>"
    "<td>Total</td></tr>"
    "<tr><td>Infra</td>"
    "<td>Zero</td>"
    "<td>Zero (Foundry escala/atualiza)</td>"
    "<td>Você opera</td></tr>"
    "<tr><td>Sessões/estado</td>"
    "<td>Threads gerenciadas</td>"
    "<td>Sessions API + isolation_key</td>"
    "<td>Você implementa</td></tr>"
    "<tr><td>Identidade</td>"
    "<td>Workload identity nativa</td>"
    "<td>Managed Identity do projeto</td>"
    "<td>Você provisiona</td></tr>"
    "<tr><td>Tracing</td>"
    "<td>OTel + App Insights nativo</td>"
    "<td>OTel + App Insights nativo (env injetado)</td>"
    "<td>Instrumentação manual</td></tr>"
    "<tr><td>Quando usar</td>"
    "<td>Q&amp;A, RAG simples, tools off-the-shelf</td>"
    "<td>Multi-agente, planner, loops complexos</td>"
    "<td>On-prem, regulação, ferramentas legadas</td></tr>"
    "</tbody></table>"
)

BLOCK_CRIAR = (
    "<p>O fluxo end-to-end: build da imagem do agente local → push para o ACR "
    "do projeto → <code>create_version</code> com <code>HostedAgentDefinition</code> "
    "→ poll até <code>status == \"active\"</code>.</p>"
    + _code_block("python", CREATE_HOSTED_PY, "deploy_hosted_agent.py")
    + "<p>Invocação via OpenAI Responses — o Foundry roteia para o seu container, "
    "gerencia sessão e instrumenta tracing automaticamente:</p>"
    + _code_block("python", INVOKE_HOSTED_PY, "invoke_hosted_agent.py")
)

BLOCK_PROXIMO = (
    "<p>O Hosted Agent expõe três protocolos por endpoint "
    "(<code>{project}/agents/{name}/endpoint/protocols/...</code>):</p>"
    "<ul>"
    "<li><strong>openai/v1/responses</strong> — chamada padrão (cliente OpenAI).</li>"
    "<li><strong>invocations</strong> — REST com header <code>Foundry-Features: HostedAgents=V1Preview</code>, "
    "para clientes que não usam o SDK.</li>"
    "<li><strong>a2a</strong> — agente-para-agente (Agent365, APIM Gateway).</li>"
    "</ul>"
    "<p>E entra automaticamente em:</p>"
    "<ul>"
    "<li><strong>Agent 365</strong> — Teams, Outlook, M365 chat.</li>"
    "<li><strong>Foundry Evaluations</strong> — batch e contínuo no mesmo endpoint.</li>"
    "<li><strong>Agent Monitoring</strong> — métricas, traces e ask-AI nativos.</li>"
    "</ul>"
)


BODY = {
    "pillars": ["Engenharia de Prompt", "Modelagem", "Operação"],
    "requisitos": [
        {"id": "1.1.6", "titulo": "Acelerar e popularizar a criação"},
        {"id": "1.2.5", "titulo": "Runtime gerenciado para agentes custom"},
        {"id": "1.3.1", "titulo": "Identidade e endpoint auditáveis"},
    ],
    "blocks": [
        {"titulo": "O que é um Hosted Agent", "html": BLOCK_O_QUE_E},
        {"titulo": "Hosted vs. prompt-based vs. self-hosted", "html": BLOCK_HOSTED_VS_SELF},
        {"titulo": "Build → push → create_version → invoke", "html": BLOCK_CRIAR},
        {"titulo": "O que destrava depois de virar Hosted", "html": BLOCK_PROXIMO},
    ],
    "tutorial_titulo": "Hospedar o agente local da Contoso no Foundry",
    "tutorial_passos": [
        {
            "titulo": "Empacotar o agente local (linux/amd64)",
            "html": "Em <code>src/app/mafwAgent</code> e <code>src/app/langgraphAgent</code> "
                    "estão os agentes Contoso (MAF + LangGraph). O notebook "
                    "<code>infra/scripts/deploy_hosted_agents.ipynb</code> faz "
                    "<code>docker build --platform linux/amd64</code>, push para o ACR e cria a versão.",
        },
        {
            "titulo": "Publicar como Hosted Agent",
            "html": "<code>project.agents.create_version(agent_name=\"mafw-contoso\", "
                    "definition=HostedAgentDefinition(image=..., "
                    "container_protocol_versions=[ProtocolVersionRecord(protocol=AgentProtocol.RESPONSES)]))</code>"
                    " — Foundry puxa do ACR e expõe o endpoint.",
        },
        {
            "titulo": "Comparar lado-a-lado",
            "html": "Na <strong>demo abaixo</strong>: escolha o agente (mafw / langgraph) "
                    "e alterne entre <em>Local container</em> (mesmo binário no Docker Desktop) "
                    "e <em>Foundry Hosted</em> (mesmo binário rodando no Agent Service). "
                    "Compare resposta, latência e fonte.",
        },
        {
            "titulo": "Promover para Agent 365 / Evaluations",
            "html": "O endpoint do Hosted Agent é direto consumível por Agent 365, APIM Gateway "
                    "e Foundry Evaluations — sem reempacotar nada.",
        },
    ],
    "mensagem_chave": (
        "<strong>Hosted Agent ≠ prompt-based agent.</strong> Hosted Agent é o "
        "<em>seu container</em> (MAF, LangGraph, código próprio) rodando dentro do "
        "Foundry Agent Service: você mantém o controle total da orquestração "
        "enquanto o Foundry cuida de runtime, escala, sessões, identidade e tracing."
    ),
}

router = APIRouter(prefix="/sections/ato1_hosted_agents", tags=["ato1_hosted_agents"])


@router.get("", response_class=HTMLResponse)
async def index(request: Request):
    pack = get_pack(request)
    chips = (pack.get("suggested_prompts") or {}).get("hosted_agents") or []
    return _templates.TemplateResponse(
        "index.html",
        {"request": request, "section": SECTION, "section_body": BODY, "chips": chips},
    )


# ============================================================================
#  Interactive playground — same agent code, two runtimes
# ============================================================================
# Cada AGENT abaixo representa o MESMO código de agente da Contoso
# (em src/app/<agent>) — pode ser invocado:
#   • Local container (porta exposta no docker-compose)
#   • Foundry Hosted Agent (mesma imagem rodando dentro do Agent Service)
# O nome do hosted agent é configurado por env (AZURE_AI_HOSTED_<KEY>),
# definido pelo notebook infra/scripts/deploy_hosted_agents.ipynb.
AGENTS = {
    "mafw": {
        "label": "MAFW · orquestrador ConectaTel",
        "local_url_env": "MAFW_AGENT_URL",
        "local_url_default": "http://mafw-agent:8091",
        "hosted_env": "AZURE_AI_HOSTED_MAFW",
        "hosted_default": "mafw-contoso",
    },
    "langgraph": {
        "label": "LangGraph · catálogo telecom",
        "local_url_env": "LANGGRAPH_AGENT_URL",
        "local_url_default": "http://langgraph-agent:8090",
        "hosted_env": "AZURE_AI_HOSTED_LANGGRAPH",
        "hosted_default": "langgraph-contoso",
    },
}


def _agent_cfg(agent_id: str) -> dict:
    return AGENTS.get(agent_id) or AGENTS["mafw"]


def _hosted_name_for(agent_id: str) -> str:
    cfg = _agent_cfg(agent_id)
    return os.getenv(cfg["hosted_env"], cfg["hosted_default"])


class HostedChatRequest(BaseModel):
    message: str
    target: Literal["local", "hosted"] = "hosted"
    agent_id: str = "mafw"
    session_id: Optional[str] = None


class HostedChatResponse(BaseModel):
    content: str
    target: str
    detail: str
    session_id: Optional[str] = None
    latency_ms: int
    source: str  # "real" or "mock"


@router.get("/api/agents")
async def list_agents():
    """Return the list of agents and whether each runtime is reachable."""
    items = []
    for key, cfg in AGENTS.items():
        items.append({
            "id": key,
            "label": cfg["label"],
            "local_url": os.getenv(cfg["local_url_env"], cfg["local_url_default"]),
            "hosted_name": _hosted_name_for(key),
        })
    return {"agents": items}


def _call_local(agent_id: str, message: str) -> Optional[tuple[str, int]]:
    cfg = _agent_cfg(agent_id)
    url = os.getenv(cfg["local_url_env"], cfg["local_url_default"]).rstrip("/") + "/chat"
    t0 = time.time()
    try:
        with httpx.Client(timeout=30.0) as cli:
            r = cli.post(url, json={"message": message})
            r.raise_for_status()
            data = r.json()
        text = (
            data.get("answer") or data.get("response")
            or data.get("content") or data.get("output_text") or ""
        )
        if not text:
            return None
        return text, int((time.time() - t0) * 1000)
    except Exception as exc:
        log.warning("[hosted-demo/local %s] %s", agent_id, exc)
        return None


def _call_foundry_hosted(agent_id: str, message: str,
                         session_id: Optional[str]) -> Optional[tuple[str, int, str, Optional[str]]]:
    """Invoke a Foundry Hosted Agent via the OpenAI Responses endpoint exposed
    by the Foundry project. Uses the explicit base_url pattern documented for
    Hosted Agents (Preview): {project}/agents/{name}/endpoint/protocols/openai
    with api-version=v1, AAD bearer scoped to https://ai.azure.com/.default."""
    endpoint = os.getenv("AZURE_AI_PROJECT_ENDPOINT")
    if not endpoint:
        return None
    hosted_name = _hosted_name_for(agent_id)
    try:
        from azure.identity import get_bearer_token_provider
        from openai import OpenAI
        from azure_clients import get_credential
        cred = get_credential()
        if cred is None:
            return None
        token_provider = get_bearer_token_provider(cred, "https://ai.azure.com/.default")
        base_url = f"{endpoint.rstrip('/')}/agents/{hosted_name}/endpoint/protocols/openai"
        oai = OpenAI(
            api_key=token_provider,
            base_url=base_url,
            default_query={"api-version": "v1"},
        )
    except Exception as exc:
        log.warning("[hosted-demo/foundry] init OpenAI(%s): %s", hosted_name, exc)
        return None
    try:
        t0 = time.time()
        extra: dict = {}
        if session_id:
            extra["agent_session_id"] = session_id
        resp = oai.responses.create(
            input=message,
            model=hosted_name,
            **({"extra_body": extra} if extra else {}),
        )
        text = getattr(resp, "output_text", None) or ""
        if not text:
            # fallback to manual extraction (Responses API)
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
        new_session = None
        try:
            new_session = (resp.model_extra or {}).get("agent_session_id") if hasattr(resp, "model_extra") else None
        except Exception:
            pass
        if not text:
            return None
        return text, int((time.time() - t0) * 1000), hosted_name, new_session or session_id
    except Exception as exc:
        log.warning("[hosted-demo/foundry %s] responses.create falhou: %s", hosted_name, exc)
        return None


_MOCK_LOCAL = "Local container: {agent} simulando '{q}…' — suba o microsserviço com docker compose."
_MOCK_HOSTED = "Foundry Hosted Agent '{name}' não publicado — rode infra/scripts/deploy_hosted_agents.ipynb."


@router.post("/api/chat", response_model=HostedChatResponse)
async def chat(payload: HostedChatRequest, request: Request) -> HostedChatResponse:
    use_real = is_real(request)
    t0 = time.time()
    cfg = _agent_cfg(payload.agent_id)

    if payload.target == "local":
        if use_real:
            got = _call_local(payload.agent_id, payload.message)
            if got is not None:
                content, lat = got
                return HostedChatResponse(
                    content=content, target="local",
                    detail=f"POST {os.getenv(cfg['local_url_env'], cfg['local_url_default'])}/chat",
                    latency_ms=lat, source="real",
                )
        await asyncio.sleep(1.8 + random.uniform(0, 0.7))
        return HostedChatResponse(
            content=_MOCK_LOCAL.format(agent=cfg["label"], q=payload.message[:40]),
            target="local",
            detail="microsserviço local indisponível — usando simulação offline",
            latency_ms=int((time.time() - t0) * 1000), source="mock",
        )

    # target == "hosted" (Foundry)
    if use_real:
        got = _call_foundry_hosted(payload.agent_id, payload.message, payload.session_id)
        if got is not None:
            content, lat, hosted_name, new_session = got
            return HostedChatResponse(
                content=content, target="hosted",
                detail=f"Foundry Hosted · agent={hosted_name} · /protocols/openai/v1/responses",
                session_id=new_session, latency_ms=lat, source="real",
            )
    await asyncio.sleep(2.6 + random.uniform(0, 1.0))
    return HostedChatResponse(
        content=_MOCK_HOSTED.format(name=_hosted_name_for(payload.agent_id)),
        target="hosted",
        detail="hosted agent indisponível — usando simulação offline (rode o notebook de deploy)",
        latency_ms=int((time.time() - t0) * 1000), source="mock",
    )


__all__ = ["router", "MENU_TITLE", "MENU_ICON"]

