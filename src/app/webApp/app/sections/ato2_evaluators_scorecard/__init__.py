"""Ato 2 · Custom Evaluators — content + interactive demo creating REAL Foundry custom evaluators.

Implements the public-preview workflow documented at:
  learn.microsoft.com/en-us/azure/ai-foundry/concepts/evaluation-evaluators/custom-evaluators

Real path:
  1. Lazily register two custom evaluator versions in the Foundry project
     (code-based `contoso_tom_de_voz` + prompt-based `contoso_friendliness`).
  2. Create an eval object with `oai.evals.create` referencing those evaluators.
  3. Submit dataset inline via `CreateEvalJSONLRunDataSourceParam`.
  4. Poll `oai.evals.runs.retrieve` until completed.
  5. Aggregate per-item scores from `oai.evals.runs.output_items.list`.

Mock fallback runs the same logic locally when SDK/network/RBAC fails.
"""

from __future__ import annotations

import logging
import random
import time
from pathlib import Path
from typing import Dict, List, Literal, Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from azure_clients import get_chat_deployment, get_project_client
from demo_mode import is_real
from industry import get_pack

log = logging.getLogger("custom_evaluators")

MENU_TITLE = "Evaluations & Custom Evaluators"
MENU_ICON = "fa-solid fa-clipboard-check"

_HERE = Path(__file__).parent
_GLOBAL_TEMPLATES = Path(__file__).resolve().parents[2] / "templates"
_templates = Jinja2Templates(directory=[str(_HERE / "templates"), str(_GLOBAL_TEMPLATES)])

SECTION = {
    "title": MENU_TITLE,
    "description": "Evaluators built-in do Foundry (Quality, Safety, Agent) + como construir e rodar Custom Evaluators.",
    "eyebrow": "Validar · LIVE DEMO",
    "eyebrow_icon": "fa-solid fa-vial-circle-check",
}

router = APIRouter(prefix="/sections/ato2_evaluators_scorecard", tags=["ato2_evaluators_scorecard"])


@router.get("", response_class=HTMLResponse)
async def index(request: Request):
    return _templates.TemplateResponse("index.html", {"request": request, "section": SECTION})


# ============================================================================
#  Shared dataset (used by mock + real)
# ============================================================================
_DATASET = [
    {
        "id": "ex-01",
        "pergunta": "Como faço portabilidade?",
        "resposta_modelo_a": "Para portabilidade você precisa de RG, CPF e conta da operadora atual. Processo leva 3 dias úteis.",
        "resposta_modelo_b": "É só ligar no *144 e pedir, é rápido!",
    },
    {
        "id": "ex-02",
        "pergunta": "Qual o preço do Contoso Controle 5GB?",
        "resposta_modelo_a": "O Contoso Controle 5GB custa R$54,99/mês com ligações ilimitadas e WhatsApp grátis.",
        "resposta_modelo_b": "Acho que está em torno de R$50, mas confirme no site.",
    },
    {
        "id": "ex-03",
        "pergunta": "Vocês são melhores que a Claro?",
        "resposta_modelo_a": "Cada operadora tem suas vantagens. Posso te mostrar os benefícios dos planos Contoso se quiser.",
        "resposta_modelo_b": "Claro é horrível, vem pra Contoso!",
    },
    {
        "id": "ex-04",
        "pergunta": "Como reset minha senha?",
        "resposta_modelo_a": "No app Contoso App clique em 'Esqueci minha senha' e você receberá SMS com código.",
        "resposta_modelo_b": "Hmm, não tenho certeza. Tenta no site.",
    },
    {
        "id": "ex-05",
        "pergunta": "Onde tem Contoso Fibra?",
        "resposta_modelo_a": "Contoso Fibra está disponível em mais de 4.000 municípios. Posso verificar seu CEP?",
        "resposta_modelo_b": "Em todo lugar, deve ter aí na sua cidade.",
    },
]


# ============================================================================
#  Custom evaluator definitions (registered into the Foundry project on demand)
# ============================================================================
TOM_CONTOSO_CODE = '''def grade(sample: dict, item: dict) -> float:
    """Tom de voz Contoso: formal-amigavel, sem menosprezar concorrente."""
    response = item.get("response", "") or item.get("sample", {}).get("output_text", "")
    if not response:
        return 0.0
    score = 1.0
    bad = ["horrivel", "horrivel", "pior", "lixo", "ruim"]
    if any(b in response.lower() for b in bad):
        score -= 0.5
    if len(response) < 30:
        score -= 0.2
    if "?" in response or "posso" in response.lower():
        score += 0.05
    return max(0.0, min(1.0, score))
'''

FRIENDLINESS_PROMPT = (
    "Friendliness assesses the warmth and approachability of the response.\n"
    "Rate the friendliness of the response between one and five using the following scale:\n\n"
    "1 - Unfriendly or hostile\n"
    "2 - Mostly unfriendly\n"
    "3 - Neutral\n"
    "4 - Mostly friendly\n"
    "5 - Very friendly\n\n"
    "Assign a rating based on the tone and demeanor of the response.\n\n"
    "Response:\n{{response}}\n\n"
    "Output Format (JSON):\n"
    '{\n  "result": <integer from 1 to 5>,\n'
    '  "reason": "<brief explanation for the score>"\n}\n'
)

TOM_CONTOSO_NAME = "contoso_tom_de_voz_v2"
FRIENDLINESS_NAME = "contoso_friendliness_v2"


# ============================================================================
#  Mock evaluators (used when real path is unavailable)
# ============================================================================
def _mock_groundedness(text: str) -> float:
    has_specifics = any(k in text.lower() for k in ["r$", "dias", "app", "cep", "rg", "cpf", "%"])
    return round(random.uniform(0.85, 0.98), 2) if has_specifics else round(random.uniform(0.45, 0.7), 2)


def _mock_relevance(text: str) -> float:
    return round(random.uniform(0.7, 0.95) if len(text) > 40 else random.uniform(0.4, 0.7), 2)


def _mock_tom_contoso(text: str) -> Dict:
    issues, score = [], 1.0
    bad = ["horrível", "pior", "lixo", "ruim"]
    if any(b in text.lower() for b in bad):
        issues.append("Menciona concorrente de forma negativa")
        score -= 0.5
    if len(text) < 30:
        issues.append("Resposta muito curta para tom corporativo")
        score -= 0.2
    return {"score": round(max(0, score), 2), "passed": score >= 0.7, "issues": issues}


def _mock_friendliness(text: str) -> Dict:
    """Heuristic stand-in for the prompt-based judge."""
    score = 3
    low = text.lower()
    if any(w in low for w in ["posso", "claro", "será um prazer", "ajudar"]):
        score += 1
    if "?" in text and len(text) > 40:
        score += 1
    if any(b in low for b in ["horrível", "lixo", "ruim", "péssimo"]):
        score -= 2
    score = max(1, min(5, score))
    return {"score": score, "reason": "heurística local — palavras-chave de cordialidade/negativas"}


# ============================================================================
#  Real Foundry custom-evaluator workflow
# ============================================================================
def _register_evaluators(project) -> None:
    """Idempotently create the two custom evaluator versions in the project."""
    from azure.ai.projects.models import EvaluatorCategory, EvaluatorDefinitionType  # type: ignore

    # --- code-based ---
    try:
        project.beta.evaluators.create_version(
            name=TOM_CONTOSO_NAME,
            evaluator_version={
                "name": TOM_CONTOSO_NAME,
                "categories": [EvaluatorCategory.QUALITY],
                "display_name": "Contoso · Tom de Voz",
                "description": "Custom code-based: penaliza menosprezo a concorrente e respostas curtas demais.",
                "definition": {
                    "type": EvaluatorDefinitionType.CODE,
                    "code_text": TOM_CONTOSO_CODE,
                    "init_parameters": {
                        "type": "object",
                        "properties": {
                            "deployment_name": {"type": "string"},
                            "pass_threshold": {"type": "number"},
                        },
                        "required": ["deployment_name", "pass_threshold"],
                    },
                    "metrics": {
                        "result": {
                            "type": "continuous",
                            "desirable_direction": "increase",
                            "min_value": 0.0,
                            "max_value": 1.0,
                        }
                    },
                    "data_schema": {
                        "type": "object",
                        "required": ["response"],
                        "properties": {"response": {"type": "string"}},
                    },
                },
            },
        )
    except Exception as exc:
        log.info("[evaluators] code register: %s", exc)

    # --- prompt-based ---
    try:
        project.beta.evaluators.create_version(
            name=FRIENDLINESS_NAME,
            evaluator_version={
                "name": FRIENDLINESS_NAME,
                "categories": [EvaluatorCategory.QUALITY],
                "display_name": "Contoso · Friendliness (judge)",
                "description": "Custom prompt-based: LLM-as-judge avalia cordialidade da resposta (1-5).",
                "definition": {
                    "type": EvaluatorDefinitionType.PROMPT,
                    "prompt_text": FRIENDLINESS_PROMPT,
                    "init_parameters": {
                        "type": "object",
                        "properties": {
                            "deployment_name": {"type": "string"},
                            "threshold": {"type": "number"},
                        },
                        "required": ["deployment_name", "threshold"],
                    },
                    "data_schema": {
                        "type": "object",
                        "properties": {"response": {"type": "string"}},
                        "required": ["response"],
                    },
                    "metrics": {
                        "custom_prompt": {
                            "type": "ordinal",
                            "desirable_direction": "increase",
                            "min_value": 1,
                            "max_value": 5,
                        }
                    },
                },
            },
        )
    except Exception as exc:
        log.info("[evaluators] prompt register: %s", exc)


def _build_testing_criteria(evaluators: List[str], deployment: str) -> List[Dict]:
    crits: List[Dict] = []
    if "tom_contoso" in evaluators:
        crits.append({
            "type": "azure_ai_evaluator",
            "name": TOM_CONTOSO_NAME,
            "evaluator_name": TOM_CONTOSO_NAME,
            "data_mapping": {"response": "{{item.response}}"},
            "initialization_parameters": {
                "deployment_name": deployment,
                "pass_threshold": 0.7,
            },
        })
    if "friendliness" in evaluators:
        crits.append({
            "type": "azure_ai_evaluator",
            "name": FRIENDLINESS_NAME,
            "evaluator_name": FRIENDLINESS_NAME,
            "data_mapping": {"response": "{{item.response}}"},
            "initialization_parameters": {
                "deployment_name": deployment,
                "threshold": 3,
            },
        })
    return crits


def _run_real_eval(evaluators: List[str], target_field: str,
                    timeout_s: int = 240,
                    items: Optional[List[Dict]] = None) -> Optional[Dict]:
    """Execute a real Foundry evaluation. Returns aggregated dict or None on failure."""
    project = get_project_client()
    if project is None:
        log.warning("[real-eval] project client unavailable")
        return None
    try:
        oai = project.get_openai_client()
    except Exception as exc:
        log.warning("[real-eval] openai client: %s", exc)
        return None

    custom = [e for e in evaluators if e in ("tom_contoso", "friendliness")]
    if not custom:
        return None

    deployment = get_chat_deployment() or "gpt-4o-mini"

    try:
        _register_evaluators(project)
    except Exception as exc:
        log.warning("[real-eval] register failed: %s", exc)
        return None

    try:
        from openai.types.eval_create_params import DataSourceConfigCustom  # type: ignore
        from openai.types.evals.create_eval_jsonl_run_data_source_param import (  # type: ignore
            CreateEvalJSONLRunDataSourceParam,
            SourceFileContent,
            SourceFileContentContent,
        )
    except Exception as exc:
        log.warning("[real-eval] openai types missing: %s", exc)
        return None

    data_source_config = DataSourceConfigCustom(
        type="custom",
        item_schema={
            "type": "object",
            "properties": {"response": {"type": "string"}, "id": {"type": "string"}},
            "required": ["response"],
        },
    )

    testing_criteria = _build_testing_criteria(custom, deployment)
    if not testing_criteria:
        return None

    try:
        eval_object = oai.evals.create(
            name=f"contoso-custom-eval-{int(time.time())}",
            data_source_config=data_source_config,
            testing_criteria=testing_criteria,
        )
        contents = [
            SourceFileContentContent(item={"id": ex["id"], "response": ex[target_field]})
            for ex in (items or _DATASET)
        ]
        eval_run = oai.evals.runs.create(
            eval_id=eval_object.id,
            name=f"run-{int(time.time())}",
            data_source=CreateEvalJSONLRunDataSourceParam(
                type="jsonl",
                source=SourceFileContent(type="file_content", content=contents),
            ),
        )

        deadline = time.time() + timeout_s
        run = None
        while time.time() < deadline:
            run = oai.evals.runs.retrieve(run_id=eval_run.id, eval_id=eval_object.id)
            if run.status in ("completed", "failed", "canceled"):
                break
            time.sleep(3)
        if run is None or run.status != "completed":
            log.warning("[real-eval] run did not complete: %s", getattr(run, "status", "?"))
            return None

        items = list(oai.evals.runs.output_items.list(run_id=eval_run.id, eval_id=eval_object.id))
        per_item: Dict[str, Dict] = {}
        for it in items:
            sample_id = None
            for attr in ("datasource_item", "sample"):
                obj = getattr(it, attr, None)
                if obj:
                    try:
                        sample_id = obj.get("id") if isinstance(obj, dict) else getattr(obj, "id", None)
                    except Exception:
                        pass
                    if sample_id:
                        break
            if not sample_id:
                sample_id = f"row-{len(per_item)}"

            entry = per_item.setdefault(sample_id, {})
            results_attr = getattr(it, "results", None) or []
            for r in results_attr:
                if isinstance(r, dict):
                    name, score, passed = r.get("name"), r.get("score"), r.get("passed")
                else:
                    name = getattr(r, "name", None)
                    score = getattr(r, "score", None)
                    passed = getattr(r, "passed", None)
                if name:
                    entry[name] = {"score": score, "passed": passed}

        return {
            "eval_id": eval_object.id,
            "run_id": eval_run.id,
            "report_url": getattr(run, "report_url", None),
            "per_item": per_item,
        }
    except Exception as exc:
        log.exception("[real-eval] failure: %s", exc)
        return None


# ============================================================================
#  API
# ============================================================================
class EvalRequest(BaseModel):
    evaluators: List[Literal["groundedness", "relevance", "tom_contoso", "friendliness"]]
    target: Literal["modelo_a", "modelo_b"]


class ExampleResult(BaseModel):
    id: str
    pergunta: str
    resposta: str
    scores: Dict[str, float]
    custom: Dict


class EvalResponse(BaseModel):
    target: str
    aggregate: Dict[str, float]
    pass_rate: float
    examples: List[ExampleResult]
    duration_ms: int
    source: str  # "real" or "mock"
    eval_id: Optional[str] = None
    run_id: Optional[str] = None
    report_url: Optional[str] = None


@router.get("/api/dataset")
async def dataset(request: Request):
    pack = get_pack(request)
    return {"items": pack.get("evaluator_dataset") or _DATASET}


@router.post("/api/run", response_model=EvalResponse)
async def run_eval(payload: EvalRequest, request: Request) -> EvalResponse:
    t0 = time.time()
    target_field = f"resposta_{payload.target}"
    use_real = is_real(request)
    pack = get_pack(request)
    items = pack.get("evaluator_dataset") or _DATASET

    real_data: Optional[Dict] = None
    if use_real and any(e in payload.evaluators for e in ("tom_contoso", "friendliness")):
        real_data = _run_real_eval(payload.evaluators, target_field, items=items)

    source = "real" if real_data else "mock"
    if not real_data:
        time.sleep(1.8 + random.uniform(0, 0.8))

    results: List[ExampleResult] = []
    agg: Dict[str, List[float]] = {ev: [] for ev in payload.evaluators}
    passes = 0

    for ex in items:
        text = ex[target_field]
        scores: Dict[str, float] = {}
        custom: Dict = {}
        per_item = (real_data or {}).get("per_item", {}).get(ex["id"], {}) if real_data else {}

        # Built-ins (groundedness/relevance) stay on local heuristic — they
        # require ground_truth/context fields the dataset doesn't carry.
        if "groundedness" in payload.evaluators:
            scores["groundedness"] = _mock_groundedness(text)
            agg["groundedness"].append(scores["groundedness"])
        if "relevance" in payload.evaluators:
            scores["relevance"] = _mock_relevance(text)
            agg["relevance"].append(scores["relevance"])

        if "tom_contoso" in payload.evaluators:
            real_score = per_item.get(TOM_CONTOSO_NAME, {}).get("score") if per_item else None
            if real_score is not None:
                s = round(float(real_score), 2)
                custom = {"score": s, "passed": s >= 0.7,
                          "issues": [] if s >= 0.7 else ["score abaixo do threshold (Foundry code-evaluator)"],
                          "source": "real"}
            else:
                r = _mock_tom_contoso(text)
                s = r["score"]
                custom = {**r, "source": "mock"}
            scores["tom_contoso"] = s
            agg["tom_contoso"].append(s)

        if "friendliness" in payload.evaluators:
            real_score = per_item.get(FRIENDLINESS_NAME, {}).get("score") if per_item else None
            if real_score is not None:
                raw = float(real_score)
                norm = round((raw - 1) / 4.0, 2)
                scores["friendliness"] = norm
                agg["friendliness"].append(norm)
                custom.setdefault("friendliness", {"raw": raw, "source": "real"})
            else:
                fr = _mock_friendliness(text)
                norm = round((fr["score"] - 1) / 4.0, 2)
                scores["friendliness"] = norm
                agg["friendliness"].append(norm)
                custom.setdefault("friendliness", {"raw": fr["score"], "reason": fr["reason"], "source": "mock"})

        passed = all(v >= 0.7 for v in scores.values())
        if passed:
            passes += 1
        results.append(ExampleResult(
            id=ex["id"], pergunta=ex["pergunta"], resposta=text,
            scores=scores, custom=custom,
        ))

    aggregate = {k: round(sum(v) / len(v), 2) for k, v in agg.items() if v}
    return EvalResponse(
        target=payload.target,
        aggregate=aggregate,
        pass_rate=round(passes / max(len(items), 1), 2),
        examples=results,
        duration_ms=int((time.time() - t0) * 1000),
        source=source,
        eval_id=(real_data or {}).get("eval_id"),
        run_id=(real_data or {}).get("run_id"),
        report_url=(real_data or {}).get("report_url"),
    )


__all__ = ["router", "MENU_TITLE", "MENU_ICON"]
