"""Modelagem & Fine-tuning — SLMs, destilação, fine-tuning, RLHF e DPO.

Demo interativa: dois chats lado-a-lado, mesmo input → modelo base vs.
modelo "especializado" (fine-tuned p/ atendimento Contoso). Quando demo_mode=real
ambos chamam o `mafw-agent` com system prompts distintos; senão usa respostas
mockadas determinísticas.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import time
from pathlib import Path
from typing import Dict, Optional

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from demo_mode import is_real  # type: ignore
from industry import get_pack  # type: ignore

log = logging.getLogger("modelagem")

MENU_TITLE = "Modelagem e Fine-tuning"
MENU_ICON = "fa-solid fa-microchip"

_HERE = Path(__file__).parent
_GLOBAL_TEMPLATES = Path(__file__).resolve().parents[2] / "templates"
_templates = Jinja2Templates(directory=[str(_HERE / "templates"), str(_GLOBAL_TEMPLATES)])

SECTION = {
    "title": MENU_TITLE,
    "description": (
        "SLMs, destilação, fine-tuning, RLHF e DPO no Foundry Models — "
        "compare lado-a-lado o modelo base e o modelo especializado para Contoso."
    ),
    "eyebrow": "Construir · LIVE DEMO",
    "eyebrow_icon": "fa-solid fa-microchip",
}

router = APIRouter(prefix="/sections/ato1_modelagem", tags=["ato1_modelagem"])


TECHNIQUES = [
    {
        "id": "distillation",
        "name": "Destilação",
        "icon": "fa-solid fa-filter",
        "summary": (
            "Modelo grande (teacher) gera dados sintéticos para treinar um pequeno "
            "(student). 80–95% da qualidade com 5–10% do custo de inferência."
        ),
        "when": "Você já tem um GPT-4 funcionando e quer baratear inferência mantendo qualidade.",
        "contoso": "Destilar GPT-4o → Phi-4 para FAQ de planos (alta repetição, baixa variabilidade).",
    },
    {
        "id": "sft",
        "name": "Fine-tuning Supervisionado (SFT)",
        "icon": "fa-solid fa-screwdriver-wrench",
        "summary": (
            "Treina o modelo em pares (input, output ideal). No Foundry você sobe "
            "JSONL e o serviço gerencia compute e checkpoints."
        ),
        "when": "Domínio específico, vocabulário próprio, formato de saída rígido (JSON, XML).",
        "contoso": "Padronizar saída em JSON schema para integrar com CRM legado da Contoso.",
    },
    {
        "id": "rlhf",
        "name": "RLHF (Reinforcement Learning with Human Feedback)",
        "icon": "fa-solid fa-thumbs-up",
        "summary": (
            "Humanos rankeiam pares de respostas → treina um reward model → o LLM "
            "aprende via PPO a preferir respostas com maior score humano."
        ),
        "when": "Alinhar tom, segurança, persona — tarefas onde 'qualidade' é subjetiva.",
        "contoso": "Tom de marca Contoso: empático, direto, sem jargão técnico desnecessário.",
    },
    {
        "id": "dpo",
        "name": "DPO (Direct Preference Optimization)",
        "icon": "fa-solid fa-arrow-trend-up",
        "summary": (
            "Atalho do RLHF: otimiza direto sobre pares (preferida, rejeitada) sem "
            "reward model separado. Mais simples, estável e barato."
        ),
        "when": "Você tem dataset de preferências mas não quer infra de PPO.",
        "contoso": "Iteração rápida pós-RLHF para corrigir regressões pontuais.",
    },
]


class CompareRequest(BaseModel):
    message: str


# ===== Determinístico mock para o modo demo =====
def _mock_pair(message: str, pack: Optional[Dict] = None) -> Dict:
    """Resposta mockada — modelo base genérico vs. especializado p/ indústria ativa.

    O conteúdo dos exemplos vem do pack de indústria (`data/industries/*.json`),
    permitindo trocar telecom ↔ manufatura ↔ CPG ↔ financial ↔ energy sem código.
    """
    msg = message.lower()
    pack = pack or {}
    examples = pack.get("modelagem_examples") or []
    default = pack.get("modelagem_default") or {}

    base: Optional[str] = None
    ft: Optional[str] = None
    for ex in examples:
        kws = [k.lower() for k in (ex.get("keywords") or [])]
        if any(k in msg for k in kws):
            base = ex.get("base")
            ft = ex.get("ft")
            break

    if base is None or ft is None:
        base = default.get("base") or (
            "Olá! Sou um assistente de IA. Como posso ajudar?"
        )
        ft = default.get("ft") or (
            "Olá! Sou um assistente especializado. Em que posso ajudar?"
        )

    base_label = "gpt-4o-mini (base)"
    ft_label = pack.get("ft_model_label") or "gpt-4o-mini-ft (SFT + DPO)"

    # Métricas mockadas plausíveis
    base_metrics = {
        "model": base_label,
        "latency_ms": random.randint(800, 1400),
        "tokens_in": len(message.split()) + 12,
        "tokens_out": len(base.split()),
        "cost_usd": round(0.00015 * (len(base.split()) + 12) / 1000, 6),
        "groundedness": 0.42,
        "brand_alignment": 0.31,
    }
    ft_metrics = {
        "model": ft_label,
        "latency_ms": random.randint(450, 850),
        "tokens_in": len(message.split()) + 6,  # prompt mais curto
        "tokens_out": len(ft.split()),
        "cost_usd": round(0.00018 * (len(ft.split()) + 6) / 1000, 6),
        "groundedness": 0.91,
        "brand_alignment": 0.94,
    }

    return {
        "base": {"answer": base, "metrics": base_metrics},
        "finetuned": {"answer": ft, "metrics": ft_metrics},
    }


@router.get("", response_class=HTMLResponse)
async def index(request: Request):
    pack = get_pack(request)
    tech_overrides = pack.get("techniques_examples") or {}
    techniques = [
        {**t, "contoso": tech_overrides.get(t["id"], t.get("contoso", ""))}
        for t in TECHNIQUES
    ]
    return _templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "section": SECTION,
            "techniques": techniques,
            "chips": (pack.get("suggested_prompts") or {}).get("modelagem") or [],
        },
    )


@router.post("/api/compare")
async def compare(payload: CompareRequest, request: Request):
    msg = (payload.message or "").strip()
    if not msg:
        return JSONResponse({"error": "message vazio"}, status_code=400)

    t0 = time.time()
    use_real = is_real(request)
    pack = get_pack(request)
    result = None
    source = "mock"

    if use_real:
        result = await _call_pair_real(msg, pack)
        if result:
            source = "real"

    if not result:
        # Pequena pausa artificial para "sentir" inferência
        await asyncio.sleep(0.4)
        result = _mock_pair(msg, pack)

    result["duration_ms"] = int((time.time() - t0) * 1000)
    result["source"] = source
    return result


async def _call_pair_real(message: str, pack: Optional[Dict] = None) -> Optional[Dict]:
    """Tenta chamar mafw-agent duas vezes com system prompts diferentes.

    Não há fine-tuned real — o "especializado" é apenas um system prompt mais
    rico (vindo do pack de indústria ativo). Suficiente para a demo educativa.
    """
    pack = pack or {}
    url = os.getenv("MAFW_AGENT_URL", "http://mafw-agent:8091").rstrip("/") + "/chat"
    base_prompt = (
        "Você é um assistente genérico. Responda de forma curta e genérica, "
        "sem mencionar marcas ou políticas específicas."
    )
    ft_prompt = pack.get("ft_system_prompt") or (
        "Você é o assistente oficial da empresa. Cite produto específico, código de "
        "política interna e feche com call-to-action acionável."
    )
    ft_label_real = pack.get("ft_model_label_real") or "gpt-4o-mini (simulando FT)"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r_base = await client.post(url, json={"message": message, "system": base_prompt})
            r_ft = await client.post(url, json={"message": message, "system": ft_prompt})
            r_base.raise_for_status()
            r_ft.raise_for_status()
            base = r_base.json().get("answer") or ""
            ft = r_ft.json().get("answer") or ""
            if not base or not ft:
                return None
            return {
                "base": {
                    "answer": base,
                    "metrics": {
                        "model": "gpt-4o-mini (base · system genérico)",
                        "latency_ms": int(r_base.elapsed.total_seconds() * 1000),
                        "tokens_in": None, "tokens_out": None,
                        "cost_usd": None, "groundedness": None, "brand_alignment": None,
                    },
                },
                "finetuned": {
                    "answer": ft,
                    "metrics": {
                        "model": ft_label_real,
                        "latency_ms": int(r_ft.elapsed.total_seconds() * 1000),
                        "tokens_in": None, "tokens_out": None,
                        "cost_usd": None, "groundedness": None, "brand_alignment": None,
                    },
                },
            }
    except Exception as exc:
        log.warning("[modelagem] mafw-agent unreachable: %s", exc)
        return None
