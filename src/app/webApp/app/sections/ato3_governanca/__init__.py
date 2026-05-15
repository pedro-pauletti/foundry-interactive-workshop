"""Ato 3 · Governança & Guardrails — interactive chat with safety filters visualization."""

import logging
import os
import random
import re
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from azure_clients import get_chat_deployment, get_content_safety_client, get_credential, get_openai_client
from demo_mode import is_real
from industry import get_pack

log = logging.getLogger("guardrails")

MENU_TITLE = "Governança & Guardrails"
MENU_ICON = "fa-solid fa-shield-halved"

_HERE = Path(__file__).parent
_GLOBAL_TEMPLATES = Path(__file__).resolve().parents[2] / "templates"
_templates = Jinja2Templates(directory=[str(_HERE / "templates"), str(_GLOBAL_TEMPLATES)])

SECTION = {
    "title": MENU_TITLE,
    "description": "Foundry Control Plane + Guardrails (Content Safety, Prompt Shields, Groundedness).",
    "eyebrow": "Operar & Governar · LIVE DEMO",
    "eyebrow_icon": "fa-solid fa-shield-halved",
}

router = APIRouter(prefix="/sections/ato3_governanca", tags=["ato3_governanca"])


@router.get("", response_class=HTMLResponse)
async def index(request: Request):
    pack = get_pack(request)
    ok_chip = (pack.get("suggested_prompts") or {}).get("governance_ok_example") or {
        "label": "Pergunta legítima", "prompt": "Qual o preço do produto principal?"
    }
    return _templates.TemplateResponse(
        "index.html", {"request": request, "section": SECTION, "ok_chip": ok_chip}
    )


# ============================================================================
#  Guardrail engine (simulates Azure AI Content Safety + Prompt Shields)
# ============================================================================
def _evaluate_guardrails(text: str, enabled: List[str]) -> Dict:
    """Return per-filter scores 0..1 (severity) and verdict."""
    t = text.lower()
    scores = {}
    triggers = []

    if "content_safety" in enabled:
        sev = 0
        if any(w in t for w in ["hackear", "fraudar", "bomba", "matar", "drogas"]):
            sev = max(sev, 6)
            triggers.append("Violência/atividade ilegal")
        if any(w in t for w in ["sexo", "sexual"]):
            sev = max(sev, 4)
            triggers.append("Conteúdo sexual")
        if any(w in t for w in ["idiota", "burro", "lixo de"]):
            sev = max(sev, 3)
            triggers.append("Linguagem ofensiva")
        scores["content_safety"] = sev  # 0-7 scale

    if "prompt_shield" in enabled:
        sig = 0
        if any(w in t for w in ["ignore", "esqueça", "system override", "jailbreak", "dan", "sem restrições"]):
            sig = max(sig, 0.92)
            triggers.append("Prompt injection / jailbreak")
        if "[system" in t or "<system>" in t:
            sig = max(sig, 0.97)
            triggers.append("Tentativa de override de system prompt")
        scores["prompt_shield"] = round(sig, 2)

    if "pii" in enabled:
        pii = 0
        if any(w in t for w in ["cpf", "rg", "cartão de crédito", "telefone do cliente"]):
            pii = max(pii, 0.85)
            triggers.append("Solicitação de PII")
        scores["pii"] = round(pii, 2)

    if "groundedness" in enabled:
        # only relevant on output, mocked here
        scores["groundedness"] = round(random.uniform(0.85, 0.98), 2)

    if "protected_material" in enabled:
        # heuristic stub: only flagged for output via real path
        scores["protected_material"] = 0.0

    # verdict
    blocked = False
    if (
        scores.get("content_safety", 0) >= 4
        or scores.get("prompt_shield", 0) >= 0.7
        or scores.get("pii", 0) >= 0.7
        or scores.get("protected_material", 0) >= 0.7
    ):
        blocked = True

    return {"scores": scores, "triggers": triggers, "blocked": blocked}


# ============================================================================
#  API
# ============================================================================
class GuardChatRequest(BaseModel):
    message: str
    guardrails: List[str]


class GuardChatResponse(BaseModel):
    user_message: str
    guardrail_input: Dict
    response: Optional[str]
    guardrail_output: Optional[Dict]
    blocked_at: Optional[str]
    duration_ms: int
    source: str = "mock"


_BENIGN_RESPONSES = [
    "Posso te ajudar com informações sobre planos Contoso, portabilidade, fatura ou suporte. Em que posso ser útil?",
    "Claro! O Contoso Controle 5GB custa R$54,99/mês com ligações ilimitadas.",
    "Contoso Fibra está disponível em mais de 4.000 municípios. Posso checar o seu CEP?",
]


# Intent-aware benign replies: keep the demo deterministic and make sure the
# mock answer makes sense for the suggested chips (telecom + manufacturing).
# Order matters — first keyword hit wins.
_BENIGN_INTENTS: list[tuple[tuple[str, ...], str]] = [
    # --- Manufacturing chips ---
    (("oee", "linha 3", "linha3"),
     "OEE de ontem · linha 3 = **76,2%** (Disponibilidade 90% · Performance 87% · "
     "Qualidade 97,2%). Maior perda: 28min em setup do torno CNC-3. Fonte: MES."),
    (("manutenção preditiva", "manutencao preditiva", "torno cnc"),
     "A manutenção preditiva do torno CNC-3 usa vibração (acelerômetro) + corrente do "
     "motor, com modelo treinado em 12 meses de histórico. Alerta dispara em ≥0,8 g RMS "
     "no eixo Z — janela típica de 72h antes da falha."),
    (("m-204", "m204", "defeito"),
     "**M-204** = falha de concentricidade no eixo usinado (>0,05mm). Ação padrão: "
     "isolar o lote, reverificar o setup do torno CNC-3 e abrir RNC no MES."),
    (("nr-12", "nr12", "loto", "epi"),
     "Toda intervenção em equipamento energizado exige **LOTO** conforme NR-10/NR-12. "
     "Cortinas de luz, proteções fixas e parada de emergência <600 ms são obrigatórias."),
    (("aql", "amostragem", "inspeção embalagem", "inspecao embalagem"),
     "Inspeção por amostragem **AQL 1.0** conforme NBR 5426 nível II — aceita até "
     "7 NC em amostra de 200 unidades."),
    # --- Telecom chips ---
    (("controle 5gb", "controle 5 gb", "controle"),
     "Contoso Controle 5GB custa **R$ 54,99/mês** com ligações ilimitadas e WhatsApp "
     "grátis. Quer que eu valide cobertura no seu CEP?"),
    (("fibra", "500mbps", "1gb", "cobertura"),
     "Contoso Fibra está disponível em mais de **4.000 municípios**. Plano 500 Mbps "
     "= R$ 119,90/mês, Wi-Fi 6 incluso, instalação gratuita."),
    (("portabilidade", "portar"),
     "Portabilidade Contoso leva até 3 dias úteis · gratuita · CPF do titular + última "
     "fatura da operadora atual."),
    (("fatura", "boleto", "segunda via", "2a via"),
     "Pra 2ª via da fatura: app Contoso → *Minhas Faturas* → escolher o mês → "
     "*Compartilhar PDF*. Posso enviar pelo WhatsApp cadastrado?"),
]


def _benign_reply(message: str, fallback: List[str]) -> str:
    """Pick a benign reply that actually relates to the user's prompt."""
    msg = (message or "").lower()
    for keywords, reply in _BENIGN_INTENTS:
        if any(k in msg for k in keywords):
            return reply
    return random.choice(fallback) if fallback else _BENIGN_RESPONSES[0]


def _evaluate_guardrails_real(text: str, enabled: List[str], stage: str = "input") -> Optional[Dict]:
    """Real evaluation: Content Safety (analyze_text) + Prompt Shields (REST) + PII regex.
    Always overlays the heuristic so explicit attacks are caught even if a remote
    call fails. Returns None only when the Content Safety client itself is unreachable."""
    client = get_content_safety_client()
    if client is None:
        return None
    scores: Dict[str, float] = {}
    triggers: List[str] = []

    # --- Content Safety (hate/violence/sexual/selfharm, severity 0..7) ---
    try:
        from azure.ai.contentsafety.models import AnalyzeTextOptions
        result = client.analyze_text(AnalyzeTextOptions(text=text))
        cats = {c.category.lower(): int(c.severity) for c in (result.categories_analysis or [])}
    except Exception as exc:
        log.warning("[guardrails] CS analyze_text falhou: %s", exc)
        cats = {}

    if "content_safety" in enabled:
        sev = max(cats.get("hate", 0), cats.get("violence", 0),
                  cats.get("sexual", 0), cats.get("selfharm", 0))
        scores["content_safety"] = sev
        for cat in ("hate", "violence", "sexual", "selfharm"):
            if cats.get(cat, 0) >= 2:
                triggers.append(f"Content Safety · {cat} (sev={cats[cat]})")

    # --- Prompt Shields via REST ---
    # Input  : detect direct jailbreak / UPIA on the user prompt.
    # Output : run the same endpoint with the model response in `documents`
    #          to detect XPIA (cross-domain prompt injection) that may have
    #          leaked into the answer through grounding sources.
    if "prompt_shield" in enabled:
        sig = 0.0
        if stage == "input":
            shield_sig, shield_trig = _call_prompt_shields(text)
            if shield_sig is not None:
                sig = max(sig, shield_sig)
                if shield_trig:
                    triggers.append(shield_trig)
        else:  # output
            xpia_sig, xpia_trig = _call_prompt_shields_documents(text)
            if xpia_sig is not None:
                sig = max(sig, xpia_sig)
                if xpia_trig:
                    triggers.append(xpia_trig)
        scores["prompt_shield"] = round(sig, 2)

    # --- PII via regex (CPF, telefone, email, cartão, RG) ---
    if "pii" in enabled:
        pii_sig, pii_trig = _detect_pii(text, stage)
        scores["pii"] = round(pii_sig, 2)
        if pii_trig:
            triggers.append(pii_trig)

    # --- Protected Material (Content Safety) — só faz sentido na saída ---
    if "protected_material" in enabled and stage == "output":
        pm_sig, pm_trig = _call_protected_material(text)
        if pm_sig is not None:
            scores["protected_material"] = round(pm_sig, 2)
            if pm_trig:
                triggers.append(pm_trig)

    # --- Groundedness (placeholder — só faz sentido com contexto RAG) ---
    if "groundedness" in enabled:
        scores["groundedness"] = 0.95 if stage == "output" else 0.95

    # --- Overlay heurístico para garantir captura de ataques óbvios ---
    heur = _evaluate_guardrails(text, enabled)
    for k, v in heur["scores"].items():
        if k in scores:
            scores[k] = max(scores[k], v)
        else:
            scores[k] = v
    for t in heur["triggers"]:
        if t not in triggers:
            triggers.append(t)

    blocked = (
        scores.get("content_safety", 0) >= 2
        or scores.get("prompt_shield", 0) >= 0.7
        or scores.get("pii", 0) >= 0.7
        or scores.get("protected_material", 0) >= 0.7
    )
    return {"scores": scores, "triggers": triggers, "blocked": blocked}


# --- Prompt Shields (REST) ------------------------------------------------
_SHIELD_TOKEN_CACHE: Dict[str, Tuple[str, float]] = {}


def _shield_token() -> Optional[str]:
    """AAD token para Cognitive Services. Cache de ~50 min."""
    cred = get_credential()
    if cred is None:
        return None
    cached = _SHIELD_TOKEN_CACHE.get("t")
    now = time.time()
    if cached and cached[1] > now + 60:
        return cached[0]
    try:
        tok = cred.get_token("https://cognitiveservices.azure.com/.default")
        _SHIELD_TOKEN_CACHE["t"] = (tok.token, tok.expires_on)
        return tok.token
    except Exception as exc:
        log.warning("[shield] token AAD falhou: %s", exc)
        return None


def _call_prompt_shields(text: str) -> Tuple[Optional[float], Optional[str]]:
    """POST /contentsafety/text:shieldPrompt — devolve (score 0..1, trigger)."""
    endpoint = os.getenv("AZURE_CONTENT_SAFETY_ENDPOINT")
    if not endpoint:
        return None, None
    url = endpoint.rstrip("/") + "/contentsafety/text:shieldPrompt?api-version=2024-09-01"
    key = os.getenv("AZURE_CONTENT_SAFETY_KEY")
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Ocp-Apim-Subscription-Key"] = key
    else:
        tok = _shield_token()
        if not tok:
            return None, None
        headers["Authorization"] = f"Bearer {tok}"
    body = {"userPrompt": text[:9999], "documents": []}
    try:
        with httpx.Client(timeout=8.0) as c:
            r = c.post(url, headers=headers, json=body)
        if r.status_code != 200:
            log.warning("[shield] %s %s", r.status_code, r.text[:200])
            return None, None
        data = r.json()
        attack = bool(((data.get("userPromptAnalysis") or {}).get("attackDetected")))
        if attack:
            return 0.95, "Prompt Shields · jailbreak/UPIA detectado"
        return 0.0, None
    except Exception as exc:
        log.warning("[shield] erro: %s", exc)
        return None, None


def _call_prompt_shields_documents(text: str) -> Tuple[Optional[float], Optional[str]]:
    """Output-stage Prompt Shields: roda o mesmo endpoint com a resposta no
    array ``documents`` para detectar XPIA (cross-domain prompt injection)
    que tenha vazado para a saída via grounding/tools."""
    endpoint = os.getenv("AZURE_CONTENT_SAFETY_ENDPOINT")
    if not endpoint:
        return None, None
    url = endpoint.rstrip("/") + "/contentsafety/text:shieldPrompt?api-version=2024-09-01"
    key = os.getenv("AZURE_CONTENT_SAFETY_KEY")
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Ocp-Apim-Subscription-Key"] = key
    else:
        tok = _shield_token()
        if not tok:
            return None, None
        headers["Authorization"] = f"Bearer {tok}"
    # userPrompt is required by the API; pass empty string and put the model
    # output in `documents` so only the documentsAnalysis path is exercised.
    body = {"userPrompt": "", "documents": [text[:9999]]}
    try:
        with httpx.Client(timeout=8.0) as c:
            r = c.post(url, headers=headers, json=body)
        if r.status_code != 200:
            log.warning("[shield-docs] %s %s", r.status_code, r.text[:200])
            return None, None
        data = r.json()
        docs = data.get("documentsAnalysis") or []
        if any(bool(d.get("attackDetected")) for d in docs):
            return 0.95, "Prompt Shields · XPIA na saída (documents)"
        return 0.0, None
    except Exception as exc:
        log.warning("[shield-docs] erro: %s", exc)
        return None, None


def _call_protected_material(text: str) -> Tuple[Optional[float], Optional[str]]:
    """Content Safety · Protected Material — detecta material sob copyright
    (letras de música, código protegido) na saída do modelo."""
    endpoint = os.getenv("AZURE_CONTENT_SAFETY_ENDPOINT")
    if not endpoint:
        return None, None
    url = endpoint.rstrip("/") + "/contentsafety/text:detectProtectedMaterial?api-version=2024-09-01"
    key = os.getenv("AZURE_CONTENT_SAFETY_KEY")
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Ocp-Apim-Subscription-Key"] = key
    else:
        tok = _shield_token()
        if not tok:
            return None, None
        headers["Authorization"] = f"Bearer {tok}"
    try:
        with httpx.Client(timeout=8.0) as c:
            r = c.post(url, headers=headers, json={"text": text[:9999]})
        if r.status_code != 200:
            log.warning("[protected-mat] %s %s", r.status_code, r.text[:200])
            return None, None
        data = r.json()
        detected = bool(((data.get("protectedMaterialAnalysis") or {}).get("detected")))
        if detected:
            return 0.95, "Content Safety · Protected Material detectado na saída"
        return 0.0, None
    except Exception as exc:
        log.warning("[protected-mat] erro: %s", exc)
        return None, None


# --- PII regex ------------------------------------------------------------
_PII_PATTERNS = [
    ("CPF",      re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")),
    ("Telefone", re.compile(r"\b(?:\+?55\s?)?(?:\(?\d{2}\)?\s?)?9?\d{4}-?\d{4}\b")),
    ("Email",    re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("Cartão",   re.compile(r"\b(?:\d[ -]?){13,16}\b")),
    ("RG",       re.compile(r"\b\d{1,2}\.?\d{3}\.?\d{3}-?[\dxX]\b")),
]
_PII_REQUEST_TERMS = (
    "cpf", "rg ", " rg,", " rg.", "rg dos", "rg do",
    "cartão de crédito", "cartao de credito", "número do cartão", "numero do cartao",
    "telefone do cliente", "telefones dos clientes",
    "endereço do cliente", "endereco do cliente",
    "dados pessoais",
)


def _detect_pii(text: str, stage: str) -> Tuple[float, Optional[str]]:
    """Marca alta severidade quando o texto pede PII (input) ou contém PII (output)."""
    t = text.lower()
    found_kinds: List[str] = []
    for kind, pat in _PII_PATTERNS:
        if pat.search(text):
            found_kinds.append(kind)
    if found_kinds:
        return 0.95, f"PII · {stage} contém {', '.join(found_kinds)}"
    if stage == "input" and any(term in t for term in _PII_REQUEST_TERMS):
        return 0.85, "PII · solicitação explícita de dados pessoais"
    return 0.0, None


def _generate_real(message: str, system_prompt: Optional[str] = None) -> Optional[str]:
    client = get_openai_client()
    if client is None:
        return None
    try:
        resp = client.chat.completions.create(
            model=get_chat_deployment(),
            messages=[
                {"role": "system", "content": system_prompt or "Você é um atendente. Responda em pt-BR, breve."},
                {"role": "user", "content": message},
            ],
            temperature=0.3,
            max_tokens=300,
        )
        return resp.choices[0].message.content
    except Exception as exc:
        log.warning("[guardrails-gen] %s", exc)
        return None


@router.post("/api/chat", response_model=GuardChatResponse)
async def chat(payload: GuardChatRequest, request: Request) -> GuardChatResponse:
    t0 = time.time()
    use_real = is_real(request)
    pack = get_pack(request)
    benign = pack.get("governance_benign_responses") or _BENIGN_RESPONSES
    sys_prompt = pack.get("governance_system_prompt")
    source = "mock"

    # --- INPUT guardrail ---
    inp: Optional[Dict] = None
    if use_real:
        inp = _evaluate_guardrails_real(payload.message, payload.guardrails, stage="input")
        if inp is not None:
            source = "real"
    if inp is None:
        inp = _evaluate_guardrails(payload.message, payload.guardrails)

    if inp["blocked"]:
        return GuardChatResponse(
            user_message=payload.message,
            guardrail_input=inp,
            response=None,
            guardrail_output=None,
            blocked_at="input",
            duration_ms=int((time.time() - t0) * 1000),
            source=source,
        )

    # --- Model call ---
    raw: Optional[str] = None
    if use_real:
        raw = _generate_real(payload.message, system_prompt=sys_prompt)
    if raw is None:
        time.sleep(1.4 + random.uniform(0, 0.7))
        raw = _benign_reply(payload.message, benign)
        # Keep source="real" if the input guardrail call was real — a model
        # refusal/content-filter is itself a real guardrail signal.

    # --- OUTPUT guardrail ---
    out: Optional[Dict] = None
    if use_real:
        out = _evaluate_guardrails_real(raw, payload.guardrails, stage="output")
    if out is None:
        out = _evaluate_guardrails(raw, payload.guardrails)

    if out["blocked"]:
        return GuardChatResponse(
            user_message=payload.message,
            guardrail_input=inp,
            response=None,
            guardrail_output=out,
            blocked_at="output",
            duration_ms=int((time.time() - t0) * 1000),
            source=source,
        )
    return GuardChatResponse(
        user_message=payload.message,
        guardrail_input=inp,
        response=raw,
        guardrail_output=out,
        blocked_at=None,
        duration_ms=int((time.time() - t0) * 1000),
        source=source,
    )


__all__ = ["router", "MENU_TITLE", "MENU_ICON"]
