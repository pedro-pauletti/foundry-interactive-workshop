"""Mapeamento dos requisitos Contoso × stack Microsoft (tabela filtrável)."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

_HERE = Path(__file__).parent
_ROOT_TEMPLATES = _HERE.parents[1] / "templates"

router = APIRouter(prefix="/sections/mapeamento", tags=["Mapeamento"])
templates = Jinja2Templates(directory=[str(_HERE / "templates"), str(_ROOT_TEMPLATES)])

SECTION = {
    "title": "Mapeamento Requisitos Contoso × Stack Microsoft",
    "description": (
        "Os requisitos do Framework IA Contoso e como cada produto ou funcionalidade "
        "da stack Microsoft (Foundry, Agent 365, APIM, Entra, Purview) endereça cada um."
    ),
    "eyebrow": "Seção 1 · Visão Geral do Mapeamento",
}


def _load_data() -> dict:
    """Tenta carregar requirements.json de múltiplos locais (container e dev)."""
    candidates = [_HERE / "requirements.json"]
    for parent in _HERE.parents:
        candidates.append(parent / "data" / "contoso" / "requirements.json")
    for p in candidates:
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    return {"pilares": [], "status": [], "requisitos": []}


DATA = _load_data()


@router.get("", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "section": SECTION,
            "data": DATA,
        },
    )


@router.get("/api/requirements")
async def api_requirements():
    return JSONResponse(DATA)
