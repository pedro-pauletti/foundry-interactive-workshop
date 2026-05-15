"""Classificação de Risco — alinhamento ao PL 2338 + Custom Azure Policy.

Demo conceitual + simulador: o usuário define o caso de uso (finalidade, público,
dados, criticidade) e o backend retorna a classificação (alto/médio/baixo) +
ação de enforcement (deny/audit/allow) — simulando o que uma Custom Azure
Policy for Foundry faria em runtime no Control Plane.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

log = logging.getLogger("classificacao_risco")

MENU_TITLE = "Classificação de Risco"
MENU_ICON = "fa-solid fa-triangle-exclamation"

_HERE = Path(__file__).parent
_GLOBAL_TEMPLATES = Path(__file__).resolve().parents[2] / "templates"
_templates = Jinja2Templates(directory=[str(_HERE / "templates"), str(_GLOBAL_TEMPLATES)])

SECTION = {
    "title": MENU_TITLE,
    "description": (
        "Critérios parametrizáveis, alinhamento ao PL 2338 e Custom Azure Policy "
        "for Foundry para enforcement automatizado de risco."
    ),
    "eyebrow": "Operar e Governar · DEMO",
    "eyebrow_icon": "fa-solid fa-triangle-exclamation",
}

router = APIRouter(prefix="/sections/ato3_classificacao_risco", tags=["ato3_classificacao_risco"])


# ============================================================================
#  Conceitos — exibidos como cards na página
# ============================================================================
DIMENSIONS = [
    {
        "id": "finalidade",
        "name": "Finalidade",
        "icon": "fa-solid fa-bullseye",
        "summary": "Para que o sistema de IA será usado? Decisões de crédito? Saúde? Vigilância biométrica?",
        "options": ["informacional", "atendimento", "recomendacao", "credito", "biometria"],
    },
    {
        "id": "publico",
        "name": "Público impactado",
        "icon": "fa-solid fa-users",
        "summary": "Quem é afetado pelas decisões? Funcionário, cliente cadastrado ou cidadão sem opt-in?",
        "options": ["interno", "cliente_optin", "externo"],
    },
    {
        "id": "dados",
        "name": "Sensibilidade dos dados",
        "icon": "fa-solid fa-lock",
        "summary": "Dados anonimizados, PII comum ou dados sensíveis (saúde, biométrico, racial)?",
        "options": ["anonimo", "pii", "sensivel_lgpd"],
    },
    {
        "id": "criticidade",
        "name": "Reversibilidade",
        "icon": "fa-solid fa-undo",
        "summary": "A decisão é facilmente reversível ou produz dano irreversível ao indivíduo?",
        "options": ["reversivel", "parcial", "irreversivel"],
    },
]

PL2338_PILLARS = [
    ("Categorização por risco", "Distingue sistemas de alto risco (saúde, crédito, biometria), risco aceitável e risco excessivo."),
    ("Avaliação de impacto algorítmico", "Documento obrigatório antes do go-live de sistemas de alto risco."),
    ("Direitos das pessoas afetadas", "Direito a explicação, revisão humana, contestação e correção de viés."),
    ("Governança e responsabilização", "Designação de responsável, registro público de sistemas de alto risco, auditoria."),
    ("Sanções", "Multas até 2% do faturamento ou R$ 50M por infração — alinhada à LGPD."),
]

POLICY_INTEGRATIONS = [
    ("Foundry Control Plane", "Onde a Custom Policy roda. Avalia toda criação/atualização de agente."),
    ("Microsoft Purview", "Classifica os dados utilizados pelo agente (label sensitivity)."),
    ("Entra ID Conditional Access", "Restringe quem pode criar agentes de alto risco."),
    ("Azure Monitor + Log Analytics", "Audit log de decisões deny/audit para evidência regulatória."),
    ("GRC externo (ServiceNow GRC, OneTrust)", "Receba via webhook os audit events para fechar o ciclo de risco corporativo."),
]


# ============================================================================
#  Custom Azure Policy — exemplo real (mostrado na UI como 'evidência')
# ============================================================================
AZURE_POLICY_JSON = json.dumps({
    "properties": {
        "displayName": "Contoso · Foundry Agent — Deny high-risk without Impact Assessment",
        "description": (
            "Bloqueia criação de agentes Foundry com finalidade=biometria OU "
            "público=externo sem tag impactAssessment=approved (PL 2338, art. 13)."
        ),
        "policyType": "Custom",
        "mode": "All",
        "metadata": {
            "category": "AI Foundry",
            "version": "1.2.0",
            "owner": "AI Governance Office",
            "regulatory": ["PL 2338/2023", "LGPD art. 20"],
        },
        "parameters": {
            "effect": {
                "type": "String",
                "allowedValues": ["Deny", "Audit", "Disabled"],
                "defaultValue": "Deny",
            },
        },
        "policyRule": {
            "if": {
                "allOf": [
                    {"field": "type", "equals": "Microsoft.CognitiveServices/accounts/projects/agents"},
                    {
                        "anyOf": [
                            {"field": "tags['purpose']", "equals": "biometria"},
                            {"field": "tags['audience']", "equals": "externo"},
                        ],
                    },
                    {"field": "tags['impactAssessment']", "notEquals": "approved"},
                ],
            },
            "then": {"effect": "[parameters('effect')]"},
        },
    },
}, indent=2, ensure_ascii=False)


# ============================================================================
#  Risk evaluation engine — determinístico
# ============================================================================
class EvalRequest(BaseModel):
    finalidade: str
    publico: str
    dados: str
    criticidade: str
    impact_assessment: bool = False


_SCORES = {
    "finalidade":   {"informacional": 1, "atendimento": 2, "recomendacao": 3, "credito": 4, "biometria": 5},
    "publico":      {"interno": 1, "cliente_optin": 3, "externo": 5},
    "dados":        {"anonimo": 1, "pii": 3, "sensivel_lgpd": 5},
    "criticidade":  {"reversivel": 1, "parcial": 3, "irreversivel": 5},
}


def _evaluate(req: EvalRequest) -> Dict:
    score = (
        _SCORES["finalidade"].get(req.finalidade, 0)
        + _SCORES["publico"].get(req.publico, 0)
        + _SCORES["dados"].get(req.dados, 0)
        + _SCORES["criticidade"].get(req.criticidade, 0)
    )

    if score >= 16:
        classification = "alto"
    elif score >= 9:
        classification = "medio"
    else:
        classification = "baixo"

    # Regras hard-coded do PL 2338 (alinhadas com a Custom Policy JSON)
    triggers: List[str] = []
    if req.finalidade == "biometria":
        triggers.append("finalidade=biometria → PL 2338 art. 13 (alto risco)")
    if req.publico == "externo" and req.dados in ("pii", "sensivel_lgpd"):
        triggers.append("público externo + PII/sensível → LGPD art. 20 (decisão automatizada)")
    if req.criticidade == "irreversivel":
        triggers.append("decisão irreversível → exige revisão humana obrigatória")

    must_have_assessment = classification == "alto" or bool(triggers)

    if must_have_assessment and not req.impact_assessment:
        effect = "deny"
        message = (
            "Custom Azure Policy BLOQUEOU a criação. Agente classificado como ALTO RISCO "
            "sem `impactAssessment=approved`. Anexe a Avaliação de Impacto Algorítmico (AIA) "
            "no Foundry Project e tente novamente."
        )
    elif classification == "alto":
        effect = "audit"
        message = (
            "Permitido com AUDIT ativo. Cada inferência será logada em Log Analytics; "
            "Purview aplica label `Confidential-AI-HighRisk`."
        )
    elif classification == "medio":
        effect = "audit"
        message = "Risco médio: deploy permitido com monitoramento padrão e revisão trimestral."
    else:
        effect = "allow"
        message = "Risco baixo: deploy livre, monitoramento mínimo."

    return {
        "score": score,
        "classification": classification,
        "effect": effect,
        "message": message,
        "triggers": triggers,
        "policy_path": (
            "Foundry Control Plane → Custom Azure Policy "
            "`Contoso-Foundry-Deny-HighRisk-WithoutAIA` → " + effect.upper()
        ),
    }


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
            "dimensions": DIMENSIONS,
            "pl2338": PL2338_PILLARS,
            "integrations": POLICY_INTEGRATIONS,
            "policy_json": AZURE_POLICY_JSON,
        },
    )


@router.post("/api/policy/evaluate")
async def evaluate(req: EvalRequest):
    try:
        return _evaluate(req)
    except Exception as exc:
        log.exception("evaluate failed")
        return JSONResponse({"error": str(exc)}, status_code=500)
