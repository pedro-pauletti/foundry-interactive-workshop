"""Local LangGraph agent — assistente de catálogo telecom.

Demonstra um agente *local* (não hospedado no Foundry) que ainda usa
Azure OpenAI + Azure AI Search via Entra ID. Pode ser comparado lado a
lado com os Hosted Agents do Foundry.

Grafo:
    user -> llm -> (tool? loop : final)

Ferramenta:
    search_telecom_catalog(query: str) -> lista de produtos do índice
    `telecom-products` via vetorizador integrado.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Annotated, TypedDict

from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel, Field

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizableTextQuery

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import AzureChatOpenAI
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

# --------------------------------------------------------------------------- env
load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
load_dotenv()  # also pick up /app/.env in container

AOAI_ENDPOINT     = os.environ.get("AZURE_OPENAI_ENDPOINT", "").rstrip("/")
AOAI_API_VERSION  = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21")
AOAI_CHAT_DEPLOY  = os.environ.get("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-4o-mini")

SEARCH_ENDPOINT   = os.environ.get("AZURE_SEARCH_ENDPOINT", "")
INDEX_TELECOM     = os.environ.get("AZURE_SEARCH_INDEX_TELECOM", "telecom-products")

credential = DefaultAzureCredential()

# --------------------------------------------------------------------------- llm
def build_llm() -> AzureChatOpenAI:
    token_provider = get_bearer_token_provider(credential, "https://cognitiveservices.azure.com/.default")
    return AzureChatOpenAI(
        azure_endpoint=AOAI_ENDPOINT,
        azure_deployment=AOAI_CHAT_DEPLOY,
        api_version=AOAI_API_VERSION,
        azure_ad_token_provider=token_provider,
        temperature=0.2,
    )

# --------------------------------------------------------------------------- tool
@tool
def search_telecom_catalog(query: str) -> str:
    """Busca produtos no catálogo da operadora ConectaTel (planos móveis,
    fibra, TV e dispositivos). Retorna até 5 produtos relevantes em texto."""
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
        lines.append(f"- [{h['sku']}] {h['productName']} ({h.get('subcategory','')}) {price} — {h.get('description','')}")
    return "\n".join(lines) if lines else "Nenhum produto encontrado."

TOOLS = [search_telecom_catalog]

# --------------------------------------------------------------------------- graph
SYSTEM_PROMPT = """Você é um assistente local da ConectaTel rodando em LangGraph.
Sempre que o usuário perguntar sobre produtos, planos ou dispositivos, USE a tool
`search_telecom_catalog` antes de responder. Cite SKU + nome ao mencionar produtos.
Responda em português, tom cordial. Não invente preços ou condições."""

class GraphState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]

def llm_node(state: GraphState) -> dict:
    llm = build_llm().bind_tools(TOOLS)
    msgs: list[BaseMessage] = state["messages"]
    if not msgs or not isinstance(msgs[0], AIMessage):
        msgs = [HumanMessage(SYSTEM_PROMPT)] + msgs  # cheap system priming
    out = llm.invoke(msgs)
    return {"messages": [out]}

def tool_node(state: GraphState) -> dict:
    last = state["messages"][-1]
    out: list[BaseMessage] = []
    for call in getattr(last, "tool_calls", []) or []:
        if call["name"] == "search_telecom_catalog":
            result = search_telecom_catalog.invoke(call["args"])
            out.append(ToolMessage(content=str(result), tool_call_id=call["id"]))
    return {"messages": out}

def should_continue(state: GraphState) -> str:
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and getattr(last, "tool_calls", None):
        return "tool"
    return END

graph_builder = StateGraph(GraphState)
graph_builder.add_node("llm", llm_node)
graph_builder.add_node("tool", tool_node)
graph_builder.set_entry_point("llm")
graph_builder.add_conditional_edges("llm", should_continue, {"tool": "tool", END: END})
graph_builder.add_edge("tool", "llm")
GRAPH = graph_builder.compile()

# --------------------------------------------------------------------------- api
app = FastAPI(title="LangGraph Local Agent — ConectaTel")

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)

class ChatResponse(BaseModel):
    answer: str
    tool_calls: list[str]
    duration_ms: int
    runtime: str = "langgraph"

@app.get("/health")
def health() -> dict:
    return {"status": "ok", "runtime": "langgraph", "model": AOAI_CHAT_DEPLOY}

@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    start = time.time()
    state: GraphState = {"messages": [HumanMessage(content=req.message)]}
    final = GRAPH.invoke(state)
    msgs = final["messages"]
    answer = ""
    tool_calls: list[str] = []
    for m in msgs:
        if isinstance(m, AIMessage):
            if m.content:
                answer = str(m.content)
            for tc in getattr(m, "tool_calls", []) or []:
                tool_calls.append(tc["name"])
    return ChatResponse(
        answer=answer or "(sem resposta)",
        tool_calls=tool_calls,
        duration_ms=int((time.time() - start) * 1000),
    )
