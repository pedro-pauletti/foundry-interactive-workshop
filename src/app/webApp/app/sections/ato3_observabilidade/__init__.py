"""Observabilidade em Produção — dashboard customizado.

Real path: KQL via `azure-monitor-query` contra o Log Analytics Workspace
(`LOG_ANALYTICS_WORKSPACE_ID`). Quando o workspace ainda não tem dados (Diagnostic
Settings / OTel não configurados ou sem tráfego), cai automaticamente no mock —
mantendo a UI do workshop funcional.

KQL alinhado ao tutorial referência:
https://github.com/pedro-pauletti/foundry-observability  (Modules 8 + 9)
"""

from __future__ import annotations

import logging
import os
import asyncio
import random
import sys
import time
from datetime import timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

# `demo_mode` lives at app/demo_mode.py — make it importable from this sub-package.
_APP_DIR = Path(__file__).resolve().parents[2]
if str(_APP_DIR) not in sys.path:
    sys.path.insert(0, str(_APP_DIR))
from demo_mode import is_real  # type: ignore  # noqa: E402

from azure_clients import (  # type: ignore  # noqa: E402
    get_log_analytics_workspace_id,
    get_logs_query_client,
)

log = logging.getLogger("contoso.observabilidade")

MENU_TITLE = "Observabilidade em Produção"
MENU_ICON = "fa-solid fa-chart-line"

_HERE = Path(__file__).parent
_GLOBAL_TEMPLATES = Path(__file__).resolve().parents[2] / "templates"
_templates = Jinja2Templates(directory=[str(_HERE / "templates"), str(_GLOBAL_TEMPLATES)])

SECTION = {
    "title": MENU_TITLE,
    "description": "Dashboard customizado de métricas dos agentes/modelos do Foundry, coletadas via APIM AI Gateway → Log Analytics.",
    "eyebrow": "Operar & Governar · LIVE DEMO",
    "eyebrow_icon": "fa-solid fa-tower-broadcast",
}

router = APIRouter(prefix="/sections/ato3_observabilidade", tags=["ato3_observabilidade"])


@router.get("", response_class=HTMLResponse)
async def index(request: Request):
    return _templates.TemplateResponse("index.html", {"request": request, "section": SECTION})


# ============================================================================
#  Pydantic models
# ============================================================================
class MetricsRequest(BaseModel):
    window_hours: int = 24


class TimeBucket(BaseModel):
    t: str
    tokens: int
    requests: int
    p95_latency_ms: int
    cache_hit_rate: float


class AgentRow(BaseModel):
    agent: str
    model: str
    requests: int
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    p50_latency_ms: int
    p95_latency_ms: int
    error_rate: float
    cache_hit_rate: float


class ModelRow(BaseModel):
    model: str
    requests: int
    tokens: int
    cost_usd: float
    share: float


class LatencyHistogram(BaseModel):
    buckets: List[str]
    counts: List[int]


class MetricsResponse(BaseModel):
    window_hours: int
    generated_at: str
    source: str = "mock"
    workspace: Optional[str] = None
    notes: List[str] = []
    kpis: dict
    timeseries: List[TimeBucket]
    by_agent: List[AgentRow]
    by_model: List[ModelRow]
    latency_hist: LatencyHistogram
    top_alerts: List[dict]


# ============================================================================
#  Pricing table (USD per 1M tokens) — alinhado ao Module 9
# ============================================================================
_PRICE = {
    # input, output (USD per 1M tokens)
    "gpt-4o":          (2.50, 10.00),
    "gpt-4o-mini":     (0.15,  0.60),
    "gpt-4.1":         (2.00,  8.00),
    "gpt-4.1-mini":    (0.15,  0.60),
    "o3-mini":         (1.10,  4.40),
    "claude":          (3.00, 15.00),
    "mistral":         (2.00,  6.00),
    "deepseek":        (0.80,  2.00),
    "kimi":            (1.00,  4.00),
}


def _price_for(model: str) -> tuple[float, float]:
    m = (model or "").lower()
    for key, p in _PRICE.items():
        if key in m:
            return p
    return (1.0, 5.0)


def _hour_label(h: int) -> str:
    return f"{(h % 24):02d}:00"


# ============================================================================
#  REAL path — KQL queries against Log Analytics
# ============================================================================
# APIM diagnostic settings use the *resource-specific* destination, so logs
# land in `ApiManagementGatewayLogs` (not `AzureDiagnostics`). Token counts
# come from the AzureMetrics namespace `Microsoft.CognitiveServices/accounts`,
# joined back by time window.

# Per-deployment latency / volume / errors — derived from APIM gateway logs.
_KQL_BY_DEPLOYMENT = """
ApiManagementGatewayLogs
| where TimeGenerated > ago({h}h)
| where isnotempty(Url)
| extend Deployment = coalesce(extract(@"/openai/deployments/([^/?]+)", 1, Url), "unknown")
| extend Project = tostring(ApimSubscriptionId)
| summarize
    Calls          = count(),
    Errors         = countif(ResponseCode >= 400),
    Throttled      = countif(ResponseCode == 429),
    AvgLatencyMs   = avg(TotalTime),
    P50LatencyMs   = percentile(TotalTime, 50),
    P95LatencyMs   = percentile(TotalTime, 95),
    AvgBackendMs   = avg(BackendTime),
    TotalRequestKB = sum(RequestSize) / 1024.0,
    TotalResponseKB= sum(ResponseSize) / 1024.0,
    Project        = any(Project)
  by Deployment
| order by Calls desc
"""

# Time series per hour — APIM gateway logs.
_KQL_TIMESERIES = """
ApiManagementGatewayLogs
| where TimeGenerated > ago({h}h)
| summarize
    Calls         = count(),
    Errors        = countif(ResponseCode >= 400),
    P95LatencyMs  = percentile(TotalTime, 95),
    BytesIn       = sum(RequestSize),
    BytesOut      = sum(ResponseSize)
  by bin(TimeGenerated, 1h)
| order by TimeGenerated asc
"""

# Latency histogram — APIM gateway logs.
_KQL_LATENCY_HIST = """
ApiManagementGatewayLogs
| where TimeGenerated > ago({h}h)
| extend Bucket = case(
    TotalTime < 200, "<200",
    TotalTime < 500, "200-500",
    TotalTime < 800, "500-800",
    TotalTime < 1200, "800-1.2k",
    TotalTime < 2000, "1.2k-2k",
    TotalTime < 3000, "2k-3k",
    ">3k")
| summarize Count = count() by Bucket
"""

# Total tokens by hour — from Foundry-emitted AzureMetrics
# (the APIM `azure-openai-emit-token-metric` policy also lands here once
# allMetrics is enabled on the APIM resource).
_KQL_TOKENS_TIMESERIES = """
AzureMetrics
| where TimeGenerated > ago({h}h)
| where MetricName == "TotalTokens"
| summarize Tokens = toint(sum(Total)) by bin(TimeGenerated, 1h)
| order by TimeGenerated asc
"""

# Aggregate tokens for the whole window — used for KPI cards.
_KQL_TOKENS_TOTAL = """
AzureMetrics
| where TimeGenerated > ago({h}h)
| where MetricName in ("TotalTokens", "InputTokens", "OutputTokens",
                       "ProcessedPromptTokens", "GeneratedTokens")
| summarize Value = sum(Total) by MetricName
"""


def _row_to_dict(table, row) -> Dict[str, Any]:
    """LogsTable row → {col: value} dict."""
    cols = [c.name if hasattr(c, "name") else c for c in table.columns]
    return dict(zip(cols, row))


def _query_real(window_hours: int) -> Optional[MetricsResponse]:
    """Try Log Analytics. Returns MetricsResponse(source='real') or None on failure / no data."""
    workspace_id = get_log_analytics_workspace_id()
    client = get_logs_query_client()
    if not workspace_id or client is None:
        log.info("LAW workspace_id ou client indisponível — fallback mock")
        return None

    try:
        from azure.monitor.query import LogsQueryStatus  # type: ignore
    except Exception:
        LogsQueryStatus = None  # type: ignore

    h = max(1, min(72, window_hours))
    timespan = timedelta(hours=h)
    notes: List[str] = []
    by_deployment: List[Dict[str, Any]] = []
    timeseries_rows: List[Dict[str, Any]] = []
    hist_rows: List[Dict[str, Any]] = []

    def _run(name: str, kql: str) -> List[Dict[str, Any]]:
        try:
            r = client.query_workspace(workspace_id=workspace_id, query=kql, timespan=timespan)
            status_ok = (LogsQueryStatus is None) or (getattr(r, "status", None) == LogsQueryStatus.SUCCESS)
            if not status_ok:
                notes.append(f"{name}: parcial ({getattr(r, 'partial_error', '')})")
            tables = getattr(r, "tables", None) or []
            if not tables:
                return []
            t = tables[0]
            return [_row_to_dict(t, row) for row in t.rows]
        except Exception as exc:
            log.warning("KQL %s falhou: %s", name, exc)
            notes.append(f"{name}: erro KQL — {type(exc).__name__}")
            return []

    by_deployment    = _run("by_deployment", _KQL_BY_DEPLOYMENT.format(h=h))
    timeseries_rows  = _run("timeseries",    _KQL_TIMESERIES.format(h=h))
    hist_rows        = _run("latency_hist",  _KQL_LATENCY_HIST.format(h=h))
    token_total_rows = _run("tokens_total",  _KQL_TOKENS_TOTAL.format(h=h))
    token_ts_rows    = _run("tokens_ts",     _KQL_TOKENS_TIMESERIES.format(h=h))

    total_calls = sum(int(r.get("Calls") or 0) for r in by_deployment)
    if total_calls == 0:
        log.info("LAW respondeu mas sem tráfego no APIM nas últimas %sh — fallback mock", h)
        notes.insert(0, "Log Analytics conectado, mas sem registros do APIM AI Gateway na janela. "
                       "Configure os Diagnostic Settings (Module 5) e gere tráfego para popular o dashboard.")
        return None

    # ---- Token totals from AzureMetrics (Foundry-emitted) ---------------------
    token_metrics: Dict[str, float] = {str(r.get("MetricName")): float(r.get("Value") or 0.0)
                                       for r in token_total_rows}
    total_input_tokens  = int(token_metrics.get("InputTokens") or token_metrics.get("ProcessedPromptTokens") or 0)
    total_output_tokens = int(token_metrics.get("OutputTokens") or token_metrics.get("GeneratedTokens") or 0)
    total_tokens_metric = int(token_metrics.get("TotalTokens") or (total_input_tokens + total_output_tokens))

    # ---- by_deployment → AgentRow / ModelRow ----------------------------------
    # Mapeia deployment para "agente" 1:1 (MVP — APIM ainda não emite agent_id por dimensão).
    # Tokens reais vêm de AzureMetrics (TotalTokens/InputTokens/OutputTokens) e são
    # alocados proporcionalmente à contagem de chamadas por deployment.
    by_agent: List[AgentRow] = []
    by_model_agg: Dict[str, Dict[str, float]] = {}
    if total_calls > 0 and total_tokens_metric > 0:
        notes.append(f"Tokens consolidados via AzureMetrics (Foundry): "
                     f"input={total_input_tokens:,}  output={total_output_tokens:,}  total={total_tokens_metric:,}.")
    for r in by_deployment:
        deployment = str(r.get("Deployment") or "unknown")
        calls = int(r.get("Calls") or 0)
        errors = int(r.get("Errors") or 0)
        share = (calls / total_calls) if total_calls else 0.0
        if total_tokens_metric > 0:
            ptok = int(total_input_tokens * share)
            ctok = int(total_output_tokens * share)
        else:
            # Fallback heurística: tokens ~ bytes / 4
            ptok = int(float(r.get("TotalRequestKB") or 0.0) * 256)
            ctok = int(float(r.get("TotalResponseKB") or 0.0) * 256)
        in_p, out_p = _price_for(deployment)
        cost = round(ptok / 1e6 * in_p + ctok / 1e6 * out_p, 4)
        by_agent.append(AgentRow(
            agent=deployment,
            model=deployment,
            requests=calls,
            prompt_tokens=ptok,
            completion_tokens=ctok,
            cost_usd=cost,
            p50_latency_ms=int(r.get("P50LatencyMs") or 0),
            p95_latency_ms=int(r.get("P95LatencyMs") or 0),
            error_rate=round((errors / calls) if calls else 0.0, 4),
            cache_hit_rate=0.0,  # APIM semantic caching não está no schema padrão
        ))
        agg = by_model_agg.setdefault(deployment, {"requests": 0, "tokens": 0, "cost_usd": 0.0})
        agg["requests"] += calls
        agg["tokens"] += ptok + ctok
        agg["cost_usd"] += cost
    by_agent.sort(key=lambda x: -x.cost_usd)

    total_cost = sum(v["cost_usd"] for v in by_model_agg.values()) or 1.0
    by_model = [
        ModelRow(model=k, requests=int(v["requests"]), tokens=int(v["tokens"]),
                 cost_usd=round(v["cost_usd"], 2), share=round(v["cost_usd"] / total_cost, 3))
        for k, v in by_model_agg.items()
    ]
    by_model.sort(key=lambda x: -x.cost_usd)

    # ---- timeseries -----------------------------------------------------------
    # Token series vem de AzureMetrics; demais métricas de ApiManagementGatewayLogs.
    # Junta as duas séries pelo bucket de hora e preenche buckets vazios para que
    # o chart sempre tenha ≥2 pontos (importante quando todo o tráfego foi gerado
    # numa janela curta de poucos minutos).
    from datetime import datetime, timezone

    def _hour_key(ts) -> str:
        try:
            return ts.strftime("%Y-%m-%dT%H") if hasattr(ts, "strftime") else str(ts)[:13]
        except Exception:
            return str(ts)[:13]

    tokens_by_hour: Dict[str, int] = {
        _hour_key(r.get("TimeGenerated")): int(r.get("Tokens") or 0) for r in token_ts_rows
    }
    by_hour: Dict[str, Dict[str, Any]] = {}
    for r in timeseries_rows:
        ts = r.get("TimeGenerated")
        by_hour[_hour_key(ts)] = {
            "ts": ts,
            "calls": int(r.get("Calls") or 0),
            "p95": int(r.get("P95LatencyMs") or 0),
        }

    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    timeseries: List[TimeBucket] = []
    for i in range(h - 1, -1, -1):
        ts = now - timedelta(hours=i)
        key = ts.strftime("%Y-%m-%dT%H")
        b = by_hour.get(key)
        timeseries.append(TimeBucket(
            t=ts.strftime("%H:00"),
            tokens=tokens_by_hour.get(key, 0),
            requests=int(b["calls"]) if b else 0,
            p95_latency_ms=int(b["p95"]) if b else 0,
            cache_hit_rate=0.0,
        ))

    # ---- latency histogram ----------------------------------------------------
    bucket_labels = ["<200", "200-500", "500-800", "800-1.2k", "1.2k-2k", "2k-3k", ">3k"]
    hist_map = {str(r.get("Bucket")): int(r.get("Count") or 0) for r in hist_rows}
    counts = [hist_map.get(b, 0) for b in bucket_labels]

    # ---- KPIs -----------------------------------------------------------------
    total_requests = sum(r.requests for r in by_agent)
    total_tokens = total_tokens_metric or sum(r.prompt_tokens + r.completion_tokens for r in by_agent)
    avg_p95 = int(sum(r.p95_latency_ms * r.requests for r in by_agent) / max(1, total_requests))
    err_rate = round(
        sum(r.error_rate * r.requests for r in by_agent) / max(1, total_requests), 4
    )

    total_throttled = sum(int(r.get("Throttled") or 0) for r in by_deployment)

    kpis = {
        "total_requests": total_requests,
        "total_tokens": total_tokens,
        "total_cost_usd": round(total_cost, 2),
        "p95_latency_ms": avg_p95,
        "error_rate": err_rate,
        "cache_hit_rate": 0.0,
        "throttled": total_throttled,
    }

    # Alerts derivados dos próprios dados reais
    alerts: List[dict] = []
    for r in by_agent[:3]:
        if r.p95_latency_ms > 2000:
            alerts.append({
                "severity": "warn", "title": "p95 latency acima de 2s", "agent": r.agent,
                "value": f"{r.p95_latency_ms}ms",
                "kql": "ApiManagementGatewayLogs | summarize percentile(TotalTime, 95) by Deployment=extract(@\"/openai/deployments/([^/?]+)\", 1, Url)",
            })
        if r.error_rate > 0.02:
            alerts.append({
                "severity": "crit", "title": "Erros HTTP >= 400", "agent": r.agent,
                "value": f"{r.error_rate * 100:.2f}%",
                "kql": "ApiManagementGatewayLogs | where ResponseCode >= 400 | summarize count() by bin(TimeGenerated, 5m)",
            })
    if not alerts:
        alerts.append({
            "severity": "info", "title": "Sem anomalias detectadas na janela",
            "agent": "—", "value": "OK",
            "kql": "AzureMetrics | where MetricName == 'TotalErrors' | summarize sum(Total)",
        })

    return MetricsResponse(
        window_hours=h,
        generated_at=time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
        source="real",
        workspace=os.getenv("LOG_ANALYTICS_WORKSPACE_NAME") or workspace_id,
        notes=notes,
        kpis=kpis,
        timeseries=timeseries or [TimeBucket(t="00:00", tokens=0, requests=0, p95_latency_ms=0, cache_hit_rate=0.0)],
        by_agent=by_agent,
        by_model=by_model,
        latency_hist=LatencyHistogram(buckets=bucket_labels, counts=counts),
        top_alerts=alerts,
    )


# ============================================================================
#  MOCK path — fallback for workshop demo when LAW empty
# ============================================================================
_MOCK_AGENTS = [
    {"name": "curador-conhecimento", "model": "gpt-4o"},
    {"name": "billing-agent", "model": "gpt-4o-mini"},
    {"name": "support-agent", "model": "gpt-4o-mini"},
    {"name": "sales-agent", "model": "gpt-4o"},
    {"name": "fraud-detector", "model": "o3-mini"},
]


def _build_mock(window_hours: int, notes: Optional[List[str]] = None) -> MetricsResponse:
    hours = max(1, min(72, window_hours))
    # Seed deterministically per-window so toggling 6h/24h/72h produces
    # visibly different KPIs (instead of every window scaling identically).
    random.seed(int(time.time()) // 600 * 100 + hours)

    # Scale base request volume continuously with the window so 6h, 24h and
    # 72h totals are clearly distinct (≈ ¼×, 1×, 3× respectively).
    vol_scale = hours / 24.0

    by_agent: List[AgentRow] = []
    for a in _MOCK_AGENTS:
        reqs = int(random.randint(1500, 9000) * vol_scale)
        reqs = max(reqs, 50)
        ptok = reqs * random.randint(180, 420)
        ctok = reqs * random.randint(80, 260)
        in_p, out_p = _price_for(a["model"])
        cost = round(ptok / 1e6 * in_p + ctok / 1e6 * out_p, 2)
        by_agent.append(AgentRow(
            agent=a["name"], model=a["model"], requests=reqs,
            prompt_tokens=ptok, completion_tokens=ctok, cost_usd=cost,
            p50_latency_ms=random.randint(280, 620),
            p95_latency_ms=random.randint(900, 2400),
            error_rate=round(random.uniform(0.001, 0.025), 4),
            cache_hit_rate=round(random.uniform(0.18, 0.62), 3),
        ))
    by_agent.sort(key=lambda r: -r.cost_usd)

    by_model_agg: Dict[str, Dict[str, float]] = {}
    for r in by_agent:
        agg = by_model_agg.setdefault(r.model, {"requests": 0, "tokens": 0, "cost_usd": 0.0})
        agg["requests"] += r.requests
        agg["tokens"] += r.prompt_tokens + r.completion_tokens
        agg["cost_usd"] += r.cost_usd
    total_cost = sum(v["cost_usd"] for v in by_model_agg.values()) or 1.0
    by_model = [
        ModelRow(model=k, requests=int(v["requests"]), tokens=int(v["tokens"]),
                 cost_usd=round(v["cost_usd"], 2), share=round(v["cost_usd"] / total_cost, 3))
        for k, v in by_model_agg.items()
    ]
    by_model.sort(key=lambda r: -r.cost_usd)

    timeseries: List[TimeBucket] = []
    base_req = sum(r.requests for r in by_agent) // hours
    for h in range(hours):
        wave = 1.4 - (0.65 + 0.45 * abs(((h % 24) - 12) / 12))
        req = max(1, int(base_req * wave * random.uniform(0.85, 1.15)))
        timeseries.append(TimeBucket(
            t=_hour_label(h),
            tokens=req * random.randint(280, 520),
            requests=req,
            p95_latency_ms=int(900 + 700 * (1 - wave) + random.randint(-120, 200)),
            cache_hit_rate=round(0.30 + 0.20 * wave + random.uniform(-0.05, 0.05), 3),
        ))

    bucket_labels = ["<200", "200-500", "500-800", "800-1.2k", "1.2k-2k", "2k-3k", ">3k"]
    weights = [3, 18, 32, 24, 14, 6, 3]
    total_reqs = sum(r.requests for r in by_agent)
    counts = [int(total_reqs * w / 100) for w in weights]

    total_tokens = sum(r.prompt_tokens + r.completion_tokens for r in by_agent)
    avg_p95 = int(sum(r.p95_latency_ms for r in by_agent) / len(by_agent))
    err_rate = round(sum(r.error_rate * r.requests for r in by_agent) / total_reqs, 4)
    cache_rate = round(sum(r.cache_hit_rate * r.requests for r in by_agent) / total_reqs, 3)

    kpis = {
        "total_requests": total_reqs,
        "total_tokens": total_tokens,
        "total_cost_usd": round(total_cost, 2),
        "p95_latency_ms": avg_p95,
        "error_rate": err_rate,
        "cache_hit_rate": cache_rate,
        "throttled": int(total_reqs * random.uniform(0.001, 0.006)),
    }

    alerts = [
        {"severity": "warn", "title": "p95 latency acima de 2s", "agent": by_agent[0].agent,
         "value": f"{by_agent[0].p95_latency_ms}ms",
         "kql": "AzureDiagnostics | summarize percentile(DurationMs, 95) by Deployment"},
        {"severity": "info", "title": "Cache hit rate baixo", "agent": "fraud-detector",
         "value": f"{int(by_agent[-1].cache_hit_rate * 100)}%",
         "kql": "AzureMetrics | where MetricName == 'CacheHitRate' | summarize avg(Total)"},
        {"severity": "crit", "title": "Erros 5xx aumentaram 40%", "agent": "billing-agent",
         "value": "0.024 → 0.034",
         "kql": "AzureDiagnostics | where responseCode_d >= 500 | summarize count() by bin(TimeGenerated, 5m)"},
    ]

    return MetricsResponse(
        window_hours=hours,
        generated_at=time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
        source="mock",
        workspace=os.getenv("LOG_ANALYTICS_WORKSPACE_NAME"),
        notes=notes or [],
        kpis=kpis,
        timeseries=timeseries,
        by_agent=by_agent,
        by_model=by_model,
        latency_hist=LatencyHistogram(buckets=bucket_labels, counts=counts),
        top_alerts=alerts,
    )


# ============================================================================
#  Endpoint
# ============================================================================
@router.post("/api/metrics", response_model=MetricsResponse)
async def metrics(payload: MetricsRequest, request: Request) -> MetricsResponse:
    use_real = is_real(request)
    if use_real:
        try:
            real = _query_real(payload.window_hours)
            if real is not None:
                return real
        except Exception:
            log.exception("Falha inesperada consultando Log Analytics — fallback mock")
        # Fallback path: explain why
        notes = []
        if not get_log_analytics_workspace_id():
            notes.append("LOG_ANALYTICS_WORKSPACE_ID não configurado no .env.")
        elif get_logs_query_client() is None:
            notes.append("SDK azure-monitor-query / credenciais indisponíveis no container.")
        else:
            notes.append("Workspace conectado, sem dados na janela — Diagnostic Settings + tráfego pendentes "
                         "(seguir Modules 4-5 do tutorial foundry-observability).")
        await asyncio.sleep(2.0 + random.uniform(0, 0.8))
        return _build_mock(payload.window_hours, notes=notes)
    await asyncio.sleep(2.0 + random.uniform(0, 0.8))
    return _build_mock(payload.window_hours)


__all__ = ["router", "MENU_TITLE", "MENU_ICON"]
