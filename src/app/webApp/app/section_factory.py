"""Helper para sub-apps de conteúdo (sem live demo): monta APIRouter com template compartilhado."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

_ROOT_TEMPLATES = Path(__file__).parent / "templates"

_templates = Jinja2Templates(directory=str(_ROOT_TEMPLATES))


def _merge_body(base: dict, overlay: dict | None) -> dict:
    """Shallow-merge `overlay` over `base` returning a new dict.

    Lists (blocks, requisitos, passos, …) are taken from `overlay` when present; otherwise
    from `base`. Inside list-of-dicts the overlay entry replaces the base entry positionally
    so callers can re-translate individual items by providing the full list.
    """
    if not overlay:
        return base
    merged = dict(base)
    for key, val in overlay.items():
        merged[key] = val
    return merged


def make_content_router_from_files(slug: str) -> APIRouter:
    """Cria um APIRouter que lê o conteúdo de ``content/<lang>/sections/<slug>.yaml``.

    Cada idioma tem seu próprio arquivo YAML com chaves ``section`` e ``body``.
    Falta de chave em um idioma cai automaticamente para PT (deep-merge no loader).
    """
    from content_loader import load_section_dict  # local import to avoid cycles

    router = APIRouter(prefix=f"/sections/{slug}", tags=[slug])

    @router.get("", response_class=HTMLResponse)
    async def index(request: Request):
        lang = getattr(request.state, "lang", "pt")
        payload = load_section_dict(lang, slug)
        if payload is None:
            # Defensive: surface a 500 rather than silently rendering blanks.
            raise RuntimeError(
                f"content/{lang}/sections/{slug}.yaml not found (and PT fallback missing)"
            )
        return _templates.TemplateResponse(
            "_section_page.html",
            {"request": request, "section": payload["section"], "section_body": payload["body"]},
        )

    return router


def make_content_router(
    slug: str,
    section: dict,
    body: dict,
    section_i18n: dict | None = None,
    body_i18n: dict | None = None,
) -> APIRouter:
    """Cria um APIRouter com uma rota GET / que renderiza _section_page.html.

    `section_i18n` e `body_i18n` são dicts opcionais no formato
    `{"en": {...}, "es": {...}}` com overrides por idioma. O idioma de fallback é o
    português (conteúdo nativo de `section` e `body`).
    """
    router = APIRouter(prefix=f"/sections/{slug}", tags=[slug])

    @router.get("", response_class=HTMLResponse)
    async def index(request: Request):
        lang = getattr(request.state, "lang", "pt")
        _section = _merge_body(section, (section_i18n or {}).get(lang))
        _body = _merge_body(body, (body_i18n or {}).get(lang))
        return _templates.TemplateResponse(
            "_section_page.html",
            {"request": request, "section": _section, "section_body": _body},
        )

    return router
