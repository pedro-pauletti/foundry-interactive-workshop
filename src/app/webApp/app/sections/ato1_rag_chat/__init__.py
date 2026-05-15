"""Ato 1 · RAG com Foundry IQ — content + live chat com toggle de retrieval."""

import logging
import os
import asyncio
import random
import time
from pathlib import Path
from typing import List, Literal, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from azure_clients import (
    get_chat_deployment,
    get_openai_client,
    get_search_client,
    get_search_client_for,
    resolve_index_name,
)
from demo_mode import is_real
from industry import get_pack

log = logging.getLogger("rag_chat")

MENU_TITLE = "RAG com Foundry IQ"
MENU_ICON = "fa-solid fa-comments"

_HERE = Path(__file__).parent
_GLOBAL_TEMPLATES = Path(__file__).resolve().parents[2] / "templates"
_templates = Jinja2Templates(directory=[str(_HERE / "templates"), str(_GLOBAL_TEMPLATES)])

SECTION = {
    "title": MENU_TITLE,
    "description": "Curador de Conhecimento Contoso respondendo com base na documentação interna.",
    "eyebrow": "Construir · LIVE DEMO",
    "eyebrow_icon": "fa-solid fa-bolt",
}

router = APIRouter(prefix="/sections/ato1_rag_chat", tags=["ato1_rag_chat"])


@router.get("", response_class=HTMLResponse)
async def index(request: Request):
    pack = get_pack(request)
    chips = (pack.get("suggested_prompts") or {}).get("rag_chat") or []
    bases = pack.get("rag_bases") or {"products": "Telecom Products", "regulations": "Internal Regulations"}
    return _templates.TemplateResponse(
        "index.html",
        {"request": request, "section": SECTION, "chips": chips, "rag_bases": bases},
    )


# ============================================================================
#  Mock knowledge base (works offline — always available for the workshop)
# ============================================================================
_KB = [
    {
        "id": "doc-port-001",
        "titulo": "Procedimento de Portabilidade Numérica",
        "trecho": "Para realizar portabilidade na Contoso o cliente deve apresentar conta da operadora atual, "
                  "RG e CPF. A solicitação é processada em até 3 dias úteis pela ABR Telecom.",
        "tags": ["portabilidade", "atendimento"],
    },
    {
        "id": "doc-port-002",
        "titulo": "Documentação Necessária para Portabilidade",
        "trecho": "Documentos exigidos: documento oficial com foto, CPF, fatura recente. Em caso de "
                  "pessoa jurídica, é necessário o contrato social e procuração se aplicável.",
        "tags": ["portabilidade", "documentação"],
    },
    {
        "id": "doc-plano-014",
        "titulo": "Catálogo de Planos Pós-pago Contoso Controle",
        "trecho": "Contoso Controle 5GB R$54,99/mês inclui ligações ilimitadas, SMS ilimitados e WhatsApp grátis. "
                  "Renovação automática mensal com possibilidade de upgrade pelo app Contoso.",
        "tags": ["planos", "pós-pago"],
    },
    {
        "id": "doc-fibra-022",
        "titulo": "Contoso Fibra — Disponibilidade e Velocidades",
        "trecho": "Contoso Fibra disponível em 4.000+ municípios. Velocidades de 200Mbps a 1Gbps. "
                  "Instalação grátis em planos anuais. Roteador Wi-Fi 6 incluso nas opções acima de 500Mbps.",
        "tags": ["fibra", "internet"],
    },
    {
        "id": "doc-fatura-007",
        "titulo": "Como Consultar e Pagar a Fatura",
        "trecho": "A fatura pode ser consultada no app Contoso App, no site contoso.com.br ou via SMS *8486#. "
                  "Pagamento aceito via PIX, débito automático, boleto e cartão de crédito.",
        "tags": ["fatura", "atendimento"],
    },
    {
        "id": "doc-suporte-031",
        "titulo": "Reset de Senha do App Contoso App",
        "trecho": "Para resetar a senha clique em 'Esqueci minha senha' na tela de login do app. "
                  "Será enviado um SMS com código de verificação para o número cadastrado.",
        "tags": ["suporte", "app"],
    },
]


def _kb_for(request: Request) -> List[dict]:
    pack = get_pack(request)
    kb = pack.get("knowledge_base") or _KB
    return kb


def _fallback_for(request: Request) -> str:
    return get_pack(request).get(
        "no_answer_fallback",
        "Não encontrei informação sobre isso na base de conhecimento. Pode reformular a pergunta?",
    )


def _retrieve(query: str, mode: str, kb: Optional[List[dict]] = None) -> List[dict]:
    q = query.lower()
    source_kb = kb if kb is not None else _KB
    # naïve keyword score
    scored = []
    for doc in source_kb:
        text = (doc["titulo"] + " " + doc["trecho"] + " " + " ".join(doc["tags"])).lower()
        score = sum(1 for w in q.split() if len(w) > 2 and w in text)
        scored.append((score, doc))
    scored.sort(key=lambda x: -x[0])
    kw_hits = [s for s in scored if s[0] > 0]

    if mode == "simple":
        # keyword (BM25) — apenas 1 doc, sem rerank, score modesto.
        if not kw_hits:
            return []
        s, d = kw_hits[0]
        return [dict(d, score=round(0.42 + s * 0.06, 2), method="keyword")]

    if mode == "semantic":
        # vetor + reranker — recupera 2 docs (faz fallback p/ KB quando keyword falha).
        pool = kw_hits if len(kw_hits) >= 2 else (kw_hits + [t for t in scored if t not in kw_hits])
        top = pool[:2]
        return [
            dict(d, score=round(0.78 + max(s, 0) * 0.05 - i * 0.04, 2), method="hybrid+rerank")
            for i, (s, d) in enumerate(top)
        ]

    # agentic: query planning → sub-queries → fusion → sempre 3 docs.
    pool = kw_hits if len(kw_hits) >= 3 else (kw_hits + [t for t in scored if t not in kw_hits])
    top = pool[:3]
    return [
        dict(d, score=round(0.86 + max(s, 0) * 0.04 - i * 0.03, 2), method="agentic-fusion")
        for i, (s, d) in enumerate(top)
    ]


def _mock_answer(query: str, citations: List[dict], mode: str, fallback: Optional[str] = None) -> str:
    """Plain-text assistant-style answers. The chat bubble renders via
    ``textContent`` so we avoid Markdown (no **bold**, no leading ``#``)."""
    if not citations:
        return fallback or "Não encontrei informação sobre isso na base de conhecimento. Pode reformular a pergunta?"

    if mode == "simple":
        # Resposta curta e direta, baseada no único documento recuperado.
        c = citations[0]
        return f"{c['trecho']}\n\nFonte: [{c['id']}]"

    if mode == "semantic":
        # Síntese fluida de 2 documentos, sem preâmbulo nem bullets.
        a, b = citations[0], (citations[1] if len(citations) > 1 else citations[0])
        refs = ", ".join(f"[{c['id']}]" for c in citations[:2])
        return f"{a['trecho']}\n\n{b['trecho']}\n\nFontes: {refs}"

    # agentic: resposta consolidada usando até 3 fontes, em prosa contínua.
    paras = [c["trecho"] for c in citations[:3]]
    refs = ", ".join(f"[{c['id']}]" for c in citations[:3])
    body = "\n\n".join(paras)
    return f"{body}\n\nFontes: {refs}"


# ============================================================================
#  API
# ============================================================================
RetrievalMode = Literal["simple", "semantic", "agentic"]
DatasetChoice = Literal["auto", "telecom", "regulations"]


class ChatRequest(BaseModel):
    message: str
    mode: RetrievalMode = "agentic"
    dataset: DatasetChoice = "auto"
    previous_response_id: Optional[str] = None


class Citation(BaseModel):
    id: str
    titulo: str
    trecho: str
    score: float
    method: str


class ChatResponse(BaseModel):
    response_id: str
    content: str
    citations: List[Citation]
    mode: str
    latency_ms: int
    source: str  # "real" or "mock"


def _retrieve_real(query: str, mode: str, dataset: str = "auto") -> Optional[List[dict]]:
    """Hit Azure AI Search across one or both indexes (telecom / regulations).

    ``dataset`` ∈ ``{"telecom", "regulations", "auto"}``. ``auto`` queries
    BOTH indexes in parallel and merges the top results by score — this is
    what fixes "some prompts return no answer" because previously only the
    single env-configured index was searched.
    """
    targets: List[str] = []
    if dataset == "telecom":
        targets = ["telecom"]
    elif dataset == "regulations":
        targets = ["regulations"]
    else:
        targets = ["telecom", "regulations"]

    merged: List[dict] = []
    any_client = False
    for ds in targets:
        idx_name = resolve_index_name(ds)
        client = get_search_client_for(idx_name)
        if client is None:
            # fall back to the legacy single-client for telecom
            if ds == "telecom":
                client = get_search_client()
            if client is None:
                continue
        any_client = True
        try:
            kwargs = {"search_text": query, "top": 3}
            if mode == "semantic":
                kwargs["query_type"] = "semantic"
                kwargs["semantic_configuration_name"] = os.getenv(
                    "AZURE_SEARCH_SEMANTIC_CONFIG", "default"
                )
            results = list(client.search(**kwargs))
        except Exception as exc:
            log.exception("[real-retrieve:%s] search failed: %s", idx_name, exc)
            continue

        for r in results:
            friendly_id = (
                r.get("sku") or r.get("policyId")
                or r.get("chunk_id") or r.get("id") or "doc"
            )
            titulo = (
                r.get("productName") or r.get("title") or r.get("titulo")
                or r.get("summary") or friendly_id
            )
            trecho = (
                r.get("description") or r.get("content") or r.get("summary")
                or r.get("trecho") or r.get("chunk") or ""
            )
            extra_bits: List[str] = [idx_name]
            if r.get("category"):
                extra_bits.append(str(r.get("category")))
            if r.get("subcategory"):
                extra_bits.append(str(r.get("subcategory")))
            if r.get("monthlyPriceBRL") is not None:
                try:
                    extra_bits.append(f"R$ {float(r['monthlyPriceBRL']):.2f}/mês")
                except Exception:
                    pass
            if r.get("version"):
                extra_bits.append(f"v{r['version']}")
            if r.get("effectiveDate"):
                extra_bits.append(str(r.get("effectiveDate")))
            score = float(r.get("@search.score", 0.0))
            merged.append({
                "id": str(friendly_id),
                "titulo": str(titulo)[:140],
                "trecho": str(trecho)[:600],
                "score": round(score, 3),
                "method": " · ".join(extra_bits),
            })

    if not any_client:
        return None
    # sort by score desc and return top-3 across indexes
    merged.sort(key=lambda d: -d["score"])
    return merged[:3]


def _chat_real(message: str, citations: List[dict]) -> Optional[str]:
    """Use Azure OpenAI (Foundry endpoint) to generate a grounded answer."""
    client = get_openai_client()
    if client is None:
        log.warning("[real-chat] openai client unavailable (check AZURE_OPENAI_ENDPOINT & credential)")
        return None
    try:
        ctx = "\n\n".join(
            f"[{c['id']}] {c['titulo']}\n{c['trecho']}" for c in citations
        ) or "(nenhum documento encontrado)"
        sys = (
            "Você é o Curador de Conhecimento Contoso. Responda em português, de forma "
            "objetiva, citando os documentos no formato [doc-id]. Se a base não cobrir "
            "a pergunta, diga que não encontrou."
        )
        resp = client.chat.completions.create(
            model=get_chat_deployment(),
            messages=[
                {"role": "system", "content": sys},
                {"role": "system", "content": f"Documentos:\n{ctx}"},
                {"role": "user", "content": message},
            ],
            temperature=0.2,
            max_tokens=600,
        )
        return resp.choices[0].message.content
    except Exception as exc:
        log.exception("[real-chat] completion failed: %s", exc)
        return None


@router.post("/api/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, request: Request) -> ChatResponse:
    t0 = time.time()
    citations_raw: List[dict] = []
    content: Optional[str] = None
    source = "mock"

    if is_real(request):
        retrieved = _retrieve_real(payload.message, payload.mode, payload.dataset)
        if retrieved is not None:
            citations_raw = retrieved
            real_answer = _chat_real(payload.message, retrieved)
            if real_answer:
                content = real_answer
                source = "real"

    synthetic_latency_ms: Optional[int] = None
    if content is None:
        # Mock path (também usado quando real falha)
        citations_raw = _retrieve(payload.message, payload.mode, kb=_kb_for(request))
        # Latência sintética por estratégia — reflete o custo real esperado:
        #   simple   ~120ms  (keyword puro, sem rerank)
        #   semantic ~520ms  (vetor + reranker)
        #   agentic  ~1900ms (planejamento + múltiplas chamadas + fusão)
        lat_band = {
            "simple":   (90, 180),
            "semantic": (420, 680),
            "agentic":  (1700, 2300),
        }.get(payload.mode, (400, 800))
        synthetic_latency_ms = random.randint(*lat_band)
        if not os.getenv("STATIC_BUILD"):
            time.sleep(synthetic_latency_ms / 1000.0)
        content = _mock_answer(payload.message, citations_raw, payload.mode, fallback=_fallback_for(request))

    citations = [Citation(**c) for c in citations_raw]
    latency_ms = synthetic_latency_ms if synthetic_latency_ms is not None else int((time.time() - t0) * 1000)
    return ChatResponse(
        response_id=f"resp-{int(time.time()*1000)}",
        content=content,
        citations=citations,
        mode=payload.mode,
        latency_ms=latency_ms,
        source=source,
    )


# ============================================================================
#  RAG Evaluation API — métricas conforme Foundry RAG evaluators
#    docs: learn.microsoft.com/en-us/azure/foundry/concepts/evaluation-evaluators/rag-evaluators
# ============================================================================
_EVAL_DATASET = [
    {
        "question": "Quais planos móveis têm suporte a 5G?",
        "ground_truth": "Os planos pós-pagos das famílias Light/Plus/Max possuem suporte a 5G; planos controle e pré-pago geralmente não.",
        "expected_doc_ids": [],
        "dataset": "telecom",
    },
    {
        "question": "Qual o plano controle mais barato com WhatsApp grátis?",
        "ground_truth": "O plano controle de entrada com WhatsApp/Telegram/Messenger zero-rating, em torno de R$49,90/mês.",
        "expected_doc_ids": [],
        "dataset": "telecom",
    },
    {
        "question": "Quais opções de banda larga fibra acima de 500Mbps?",
        "ground_truth": "Planos fibra de 500Mbps a 1Gbps com instalação grátis e roteador Wi-Fi 6 incluído nos planos anuais.",
        "expected_doc_ids": [],
        "dataset": "telecom",
    },
    {
        "question": "Qual a política de trabalho híbrido da empresa?",
        "ground_truth": "Mínimo de 2 dias presenciais por semana e até 3 dias remotos, sujeito a aprovação do gestor.",
        "expected_doc_ids": ["RH-001"],
        "dataset": "regulations",
    },
    {
        "question": "Como funciona o fracionamento de férias?",
        "ground_truth": "Até 3 períodos, sendo um obrigatoriamente de 14 dias corridos e os demais com mínimo de 5 dias.",
        "expected_doc_ids": ["RH-002"],
        "dataset": "regulations",
    },
    {
        "question": "Qual o limite para aceitar brindes de fornecedores?",
        "ground_truth": "Brindes acima de R$200 exigem aprovação do Comitê de Ética.",
        "expected_doc_ids": ["RH-003"],
        "dataset": "regulations",
    },
]


class EvaluationRequest(BaseModel):
    mode: RetrievalMode = "agentic"
    dataset: DatasetChoice = "auto"


class PerQuestionResult(BaseModel):
    question: str
    answer: str
    expected_doc_ids: List[str]
    retrieved_doc_ids: List[str]
    groundedness: float
    relevance: float
    retrieval: float
    response_completeness: float
    passed: bool


class EvaluationSummary(BaseModel):
    mode: str
    n: int
    pass_rate: float
    metrics_avg: dict
    threshold: float
    per_question: List[PerQuestionResult]
    duration_ms: int


def _token_overlap(a: str, b: str) -> float:
    ta = {w.lower().strip(".,;:!?") for w in a.split() if len(w) > 3}
    tb = {w.lower().strip(".,;:!?") for w in b.split() if len(w) > 3}
    if not ta or not tb:
        return 0.0
    return round(len(ta & tb) / len(ta | tb), 3)


def _llm_judge(question: str, answer: str, context: str, ground_truth: str) -> Optional[dict]:
    """LLM-as-judge: pede ao gpt para avaliar groundedness/relevance/completeness em 0-1."""
    client = get_openai_client()
    if client is None:
        return None
    sys = (
        "Você é um avaliador de respostas RAG. Retorne APENAS JSON válido com as chaves "
        "groundedness, relevance, response_completeness — cada uma com float 0..1. "
        "groundedness = quanto da resposta está sustentada pelo CONTEXTO; "
        "relevance = quanto a resposta endereça a PERGUNTA; "
        "response_completeness = quanto da GROUND_TRUTH foi coberta."
    )
    user = (
        f"PERGUNTA:\n{question}\n\nCONTEXTO:\n{context[:1800]}\n\n"
        f"RESPOSTA:\n{answer}\n\nGROUND_TRUTH:\n{ground_truth}"
    )
    try:
        resp = client.chat.completions.create(
            model=get_chat_deployment(),
            messages=[{"role": "system", "content": sys}, {"role": "user", "content": user}],
            temperature=0.0,
            max_tokens=120,
            response_format={"type": "json_object"},
        )
        import json as _json
        data = _json.loads(resp.choices[0].message.content or "{}")
        return {
            "groundedness": float(data.get("groundedness", 0.0)),
            "relevance": float(data.get("relevance", 0.0)),
            "response_completeness": float(data.get("response_completeness", 0.0)),
        }
    except Exception as exc:
        log.exception("[llm-judge] failed: %s", exc)
        return None


@router.post("/api/evaluate", response_model=EvaluationSummary)
async def evaluate_rag(payload: EvaluationRequest, request: Request) -> EvaluationSummary:
    """Run RAG evaluators. When in REAL mode: real retrieval + real answer + LLM-as-judge.
    When MOCK or real services unavailable: deterministic mock metrics with same shape."""
    t0 = time.time()
    threshold = 0.6
    use_real = is_real(request)
    if not use_real:
        # Make the demo feel like a real evaluator suite is running.
        if not os.getenv("STATIC_BUILD"):
            await asyncio.sleep(2.8 + random.uniform(0, 1.0))
    per_q: List[PerQuestionResult] = []

    # When the user picks a specific dataset, only run questions that target it.
    eval_items = _EVAL_DATASET
    if payload.dataset in ("telecom", "regulations"):
        eval_items = [it for it in _EVAL_DATASET if it.get("dataset") == payload.dataset]
        if not eval_items:
            eval_items = _EVAL_DATASET  # safety fallback

    for item in eval_items:
        retrieved: List[dict] = []
        answer: Optional[str] = None
        used_real = False

        if use_real:
            real_ret = _retrieve_real(item["question"], payload.mode, payload.dataset)
            if real_ret is not None:
                retrieved = real_ret
                real_ans = _chat_real(item["question"], retrieved)
                if real_ans:
                    answer = real_ans
                    used_real = True

        if not used_real:
            retrieved = _retrieve(item["question"], payload.mode, kb=_kb_for(request))
            answer = _mock_answer(item["question"], retrieved, payload.mode, fallback=_fallback_for(request))

        retrieved_ids = [d["id"] for d in retrieved]
        ctx = " ".join(d["trecho"] for d in retrieved)

        # Try LLM judge first (only meaningful in real mode)
        judge: Optional[dict] = None
        if used_real:
            judge = _llm_judge(item["question"], answer or "", ctx, item["ground_truth"])

        if judge is not None:
            groundedness = round(min(1.0, max(0.0, judge["groundedness"])), 3)
            relevance = round(min(1.0, max(0.0, judge["relevance"])), 3)
            response_completeness = round(min(1.0, max(0.0, judge["response_completeness"])), 3)
        else:
            # mock metrics
            if not retrieved:
                groundedness = 1.0 if (answer and "não encontrei" in answer.lower()) else 0.2
            else:
                groundedness = min(1.0, 0.55 + _token_overlap(answer or "", ctx) * 0.6)
            relevance = min(1.0, 0.50 + _token_overlap(answer or "", item["question"]) * 0.7)
            response_completeness = min(1.0, 0.45 + _token_overlap(answer or "", item["ground_truth"]) * 0.7)
            boost = {"simple": -0.05, "semantic": 0.05, "agentic": 0.10}.get(payload.mode, 0.0)
            groundedness = round(min(1.0, max(0.0, groundedness + boost)), 3)
            relevance = round(min(1.0, max(0.0, relevance + boost)), 3)
            response_completeness = round(min(1.0, max(0.0, response_completeness + boost)), 3)

        # Retrieval: if expected_doc_ids provided, compute precision; otherwise heuristic
        if item["expected_doc_ids"]:
            hit = len(set(retrieved_ids) & set(item["expected_doc_ids"]))
            retrieval = round(hit / len(item["expected_doc_ids"]), 3)
        else:
            # sem ground-truth ids: usa proporção de docs com score >= mediano
            retrieval = 1.0 if retrieved else 0.0

        avg = (groundedness + relevance + retrieval + response_completeness) / 4
        per_q.append(PerQuestionResult(
            question=item["question"],
            answer=answer or "",
            expected_doc_ids=item["expected_doc_ids"],
            retrieved_doc_ids=retrieved_ids,
            groundedness=groundedness,
            relevance=relevance,
            retrieval=retrieval,
            response_completeness=response_completeness,
            passed=avg >= threshold,
        ))

    n = len(per_q)
    metrics_avg = {
        "groundedness": round(sum(p.groundedness for p in per_q) / n, 3),
        "relevance": round(sum(p.relevance for p in per_q) / n, 3),
        "retrieval": round(sum(p.retrieval for p in per_q) / n, 3),
        "response_completeness": round(sum(p.response_completeness for p in per_q) / n, 3),
    }
    pass_rate = round(sum(1 for p in per_q if p.passed) / n, 3)

    return EvaluationSummary(
        mode=payload.mode,
        n=n,
        pass_rate=pass_rate,
        metrics_avg=metrics_avg,
        threshold=threshold,
        per_question=per_q,
        duration_ms=int((time.time() - t0) * 1000),
    )


__all__ = ["router", "MENU_TITLE", "MENU_ICON"]
