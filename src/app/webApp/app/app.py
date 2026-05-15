"""Workshop web app — agenda-driven sidebar + auto-discovered section sub-apps."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from agenda_loader import load_agenda, normalize_for_match
from content_loader import (
    available_languages as content_languages,
    load_agenda as load_content_agenda,
)
from demo_mode import default_mode, get_mode, real_mode_disabled, set_mode_cookie
import re as _re
from i18n import (  # noqa: E501
    make_label_translator,
    default_lang,
    get_lang,
    list_languages,
    make_translator,
    make_section_translator,
    t_optional,
    set_lang_cookie,
    t as translate,
)
from industry import (
    default_industry,
    get_industry,
    get_pack,
    list_industries,
    set_industry_cookie,
)
from sections import collect_routers

BASE = Path(__file__).resolve().parent
STATIC_VERSION = str(int(__import__("time").time()))

app = FastAPI(title=os.getenv("APP_TITLE", "Framework IA"))

templates = Jinja2Templates(directory=str(BASE / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")

AGENDA = load_agenda()
SECTIONS = collect_routers()


def _count_requirements() -> int:
    """Count Contoso requirements from data/contoso/requirements.json (best-effort)."""
    import json
    candidates = []
    for parent in BASE.parents:
        candidates.append(parent / "data" / "contoso" / "requirements.json")
    for p in candidates:
        if p.exists():
            try:
                payload = json.loads(p.read_text(encoding="utf-8"))
                return len(payload.get("requisitos", []))
            except Exception:
                return 0
    return 0


REQUIREMENTS_COUNT = _count_requirements()


import re as _re


_GENERIC_TOKENS = {
    "como", "para", "sobre", "stack", "contoso", "foundry", "agentes", "agente",
    "prompt", "prompts", "ativo", "ativos",
}


def _tokens(text: str) -> set[str]:
    """Significant lowercase tokens (length >= 3) used for fuzzy matching.
    Generic words shared across many sections are excluded so the token-overlap
    fallback in ``_match_section`` doesn't accidentally match the wrong section
    (e.g. an agenda item containing 'Prompt' matching ``ato1_prompt_versionado``).
    """
    raw = {t for t in _re.split(r"[^a-z0-9]+", text.lower()) if len(t) >= 3}
    return raw - _GENERIC_TOKENS


def _match_section(agenda_title: str):
    """Return the (slug, title, icon) of the section whose MENU_TITLE best matches
    the given agenda title. Uses normalized-substring comparison so that hand-picked
    short folder titles ("Design the target search experience") still match agenda
    items with extra prefixes ("Hands-on working session: ...").

    Falls back to a token-overlap heuristic so multi-clause agenda titles
    (e.g. "Persona Sintética, Prompt Injection & Red Teaming") still map to a
    section whose MENU_TITLE only covers part of the topic ("AI Red Teaming").
    """
    norm_a = normalize_for_match(agenda_title)
    if not norm_a:
        return None
    # Prefer exact normalized match, then containment in either direction.
    exact = []
    contains = []
    for slug, _router, title, icon in SECTIONS:
        norm_s = normalize_for_match(title)
        if not norm_s:
            continue
        if norm_a == norm_s:
            exact.append((slug, title, icon))
        elif norm_s in norm_a or norm_a in norm_s:
            contains.append((slug, title, icon))
    if exact:
        return exact[0]
    if contains:
        # Pick the longest match — most specific
        contains.sort(key=lambda t: len(normalize_for_match(t[1])), reverse=True)
        return contains[0]

    # Token-overlap fallback: pick the section sharing the most significant
    # tokens with the agenda title (and at least one).
    a_tokens = _tokens(agenda_title)
    if not a_tokens:
        return None
    best = None
    best_score = 0
    for slug, _router, title, icon in SECTIONS:
        s_tokens = _tokens(title)
        score = len(a_tokens & s_tokens)
        if score > best_score:
            best_score = score
            best = (slug, title, icon)
    # Require at least 2 token overlap to avoid coincidental single-word matches
    # (e.g. an agenda item containing "Prompt" silently matching prompt_versionado).
    if best_score < 2:
        return None
    return best


MENU = []
matched_slugs: set[str] = set()
for item in AGENDA:
    match = _match_section(item.title)
    if match:
        slug, title, icon = match
        matched_slugs.add(slug)
        MENU.append(
            {
                "slug": slug,
                "title": title,                 # short, clean label from MENU_TITLE
                "agenda_title": item.title,     # exact agenda title (tooltip / debug)
                "description": item.description,
                "icon": icon,
                "url": f"/sections/{slug}",
            }
        )
    else:
        # Agenda item without a matching sub-app — link to a 404-ish placeholder
        MENU.append(
            {
                "slug": item.slug,
                "title": item.title,
                "agenda_title": item.title,
                "description": item.description,
                "icon": "fa-solid fa-circle-question",
                "url": "#",
            }
        )

# Append any sub-apps not referenced by the agenda (defensive)
for slug, _router, title, icon in SECTIONS:
    if slug not in matched_slugs:
        MENU.append(
            {
                "slug": slug,
                "title": title,
                "agenda_title": title,
                "description": "",
                "icon": icon,
                "url": f"/sections/{slug}",
            }
        )


def _build_groups(menu: list[dict], lang: str) -> list[dict]:
    """Group menu items by section folder slug prefix (ato1_/ato2_/ato3_).
    Items without that prefix go into an 'Overview' group at the top."""
    groups: dict[str, dict] = {}
    order: list[str] = []
    for item in menu:
        slug = item.get("slug", "") or ""
        key = translate("groups.overview", lang)
        icon = "fa-solid fa-compass"
        if slug.startswith("ato1_"):
            key, icon = translate("groups.build", lang), "fa-solid fa-hammer"
        elif slug.startswith("ato2_"):
            key, icon = translate("groups.validate", lang), "fa-solid fa-shield-halved"
        elif slug.startswith("ato3_"):
            key, icon = translate("groups.operate", lang), "fa-solid fa-tower-broadcast"
        if key not in groups:
            groups[key] = {"label": key, "icon": icon, "items": []}
            order.append(key)
        groups[key]["items"].append(item)
    return [groups[k] for k in order]


def _localize_menu(menu: list[dict], lang: str) -> list[dict]:
    """Return a copy of MENU with section titles translated when a key exists."""
    out = []
    for item in menu:
        slug = item.get("slug", "")
        key = f"sections.{slug}"
        title = translate(key, lang) if slug else item.get("title", "")
        # translate() returns the key unchanged when missing — keep original then.
        if title == key:
            title = item.get("title", "")
        new_item = dict(item)
        new_item["title"] = title
        out.append(new_item)
    return out


# Slug → section package metadata (icon + URL), used when overlaying the
# file-based agenda over the auto-discovered section packages.
_SECTION_BY_SLUG: dict[str, dict] = {
    slug: {"icon": icon, "url": f"/sections/{slug}", "menu_title": title}
    for slug, _router, title, icon in SECTIONS
}


def _build_menu_from_content(lang: str) -> list[dict]:
    """Build the sidebar menu from content/<lang>/agenda.yaml.

    Each agenda item's ``id`` maps directly to a section package folder
    name. Items without a matching package render with a question-mark
    icon pointing nowhere (placeholder). Returns the legacy MENU shape
    so the rest of the app (sidebar template, groups) is untouched.
    """
    items = load_content_agenda(lang)
    if not items:
        # Content folder missing — fall back to the legacy menu so the
        # app still boots in environments without content/ on disk.
        return _localize_menu(MENU, lang)

    out: list[dict] = []
    seen: set[str] = set()
    for it in items:
        meta = _SECTION_BY_SLUG.get(it.slug)
        seen.add(it.slug)
        out.append(
            {
                "slug": it.slug,
                "title": it.title,
                "agenda_title": it.title,
                "description": it.description,
                "icon": (meta or {}).get("icon") or it.icon,
                "url": (meta or {}).get("url") or "#",
            }
        )
    # Append any section packages not referenced by the agenda (defensive).
    for slug, _router, title, icon in SECTIONS:
        if slug in seen:
            continue
        key = f"sections.{slug}"
        loc_title = translate(key, lang)
        if loc_title == key:
            loc_title = title
        out.append(
            {
                "slug": slug,
                "title": loc_title,
                "agenda_title": title,
                "description": "",
                "icon": icon,
                "url": f"/sections/{slug}",
            }
        )
    return out


@app.middleware("http")
async def lang_query_handler(request: Request, call_next):
    """Handle ``?lang=xx`` query — set cookie and redirect to clean URL.

    Lets users share localized links. The cookie remains the durable
    source of truth; the query is consumed and stripped on first visit.
    """
    code = (request.query_params.get("lang") or "").strip().lower()
    if code and code in {l["code"] for l in list_languages()}:
        # Drop ?lang= from the URL while keeping any other query params.
        remaining = [(k, v) for k, v in request.query_params.multi_items() if k != "lang"]
        from urllib.parse import urlencode
        qs = urlencode(remaining)
        target = request.url.path + (f"?{qs}" if qs else "")
        resp = RedirectResponse(url=target, status_code=303)
        set_lang_cookie(resp, code)
        return resp
    return await call_next(request)


@app.middleware("http")
async def inject_menu(request: Request, call_next):
    pack = get_pack(request)
    lang = get_lang(request)
    localized_menu = _build_menu_from_content(lang)
    request.state.menu = localized_menu
    request.state.industry = get_industry(request)
    request.state.industry_pack = pack
    _industries = list_industries()
    for _ind in _industries:
        _localized_label = t_optional(f"industries.{_ind.get('slug')}.label", lang)
        if _localized_label:
            _ind["label"] = _localized_label
    request.state.industries = _industries
    request.state.lang = lang
    request.state.languages = list_languages()
    request.state.t = make_translator(lang)
    # Detect section slug from URL so templates can look up `sections.<slug>.<key>`
    _m = _re.match(r"^/sections/([a-z0-9_]+)", request.url.path)
    _slug = _m.group(1) if _m else None
    request.state.section_slug = _slug
    request.state.t_section = make_section_translator(lang, _slug)
    request.state.t_label = make_label_translator(lang)
    # Per-section UI strings sourced from content/<lang>/sections/<slug>.yaml (texts: {...}).
    # Always a dict — empty when the section has no `texts:` block — so templates can
    # safely call request.state.texts.get('key', 'fallback').
    if _slug:
        try:
            from content_loader import load_section_texts
            request.state.texts = load_section_texts(lang, _slug)
        except Exception:
            request.state.texts = {}
    else:
        request.state.texts = {}
    # App title/tagline: translation for the active language wins so the UI is consistent;
    # otherwise honor an explicit env override, then fall back to the industry pack's own value.
    _active_slug = request.state.industry
    _i18n_title = t_optional(f"industries.{_active_slug}.app_title", lang)
    _i18n_tagline = t_optional(f"industries.{_active_slug}.app_tagline", lang)
    request.state.app_title = (
        _i18n_title or os.getenv("APP_TITLE") or pack.get("app_title", "Framework IA")
    )
    request.state.app_tagline = _i18n_tagline or os.getenv("APP_TAGLINE") or pack.get(
        "app_tagline",
        "Os 24 requisitos do Framework IA Contoso e como cada um é endereçado pela stack Microsoft",
    )
    request.state.menu_groups = _build_groups(localized_menu, lang)
    request.state.demo_mode = get_mode(request)
    request.state.real_mode_disabled = real_mode_disabled()
    request.state.static_version = STATIC_VERSION
    request.state.static_demo = os.getenv("STATIC_BUILD", "0").lower() in ("1", "true", "yes")
    request.state.pages_base_url = os.getenv("PAGES_BASE_URL", "").rstrip("/")
    request.state.default_lang = default_lang()
    request.state.default_industry = default_industry()
    return await call_next(request)


# Mount every section router
for _slug, router, _title, _icon in SECTIONS:
    app.include_router(router)


class _DemoModePayload(BaseModel):
    mode: str


@app.get("/api/demo-mode")
async def get_demo_mode(request: Request):
    return {
        "mode": get_mode(request),
        "default": default_mode(),
        "real_disabled": real_mode_disabled(),
    }


@app.post("/api/demo-mode")
async def post_demo_mode(payload: _DemoModePayload):
    if real_mode_disabled() and str(payload.mode).strip().lower() == "real":
        return JSONResponse(
            {
                "mode": "mock",
                "real_disabled": True,
                "error": "Real mode is disabled in this deployment. Run the project locally with your own Azure credentials to enable real mode.",
            },
            status_code=403,
        )
    resp = JSONResponse({"mode": payload.mode})
    norm = set_mode_cookie(resp, payload.mode)
    resp = JSONResponse({"mode": norm, "real_disabled": real_mode_disabled()})
    set_mode_cookie(resp, norm)
    return resp


class _IndustryPayload(BaseModel):
    industry: str


@app.get("/api/industry")
async def get_industry_endpoint(request: Request):
    return {
        "industry": get_industry(request),
        "default": default_industry(),
        "available": list_industries(),
    }


@app.post("/api/industry")
async def post_industry(payload: _IndustryPayload):
    slug = (payload.industry or "").strip().lower()
    try:
        resp = JSONResponse({"industry": slug})
        set_industry_cookie(resp, slug)
        return resp
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


class _LanguagePayload(BaseModel):
    language: str


@app.get("/api/language")
async def get_language_endpoint(request: Request):
    return {
        "language": get_lang(request),
        "default": default_lang(),
        "available": list_languages(),
    }


@app.post("/api/language")
async def post_language(payload: _LanguagePayload):
    code = (payload.language or "").strip().lower()
    try:
        resp = JSONResponse({"language": code})
        set_lang_cookie(resp, code)
        return resp
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


# --- Azure connection status + device-code login ----------------------------

import asyncio as _asyncio
import re as _re_login
import shutil as _shutil
import subprocess as _subprocess
from typing import Optional as _Optional

from azure_clients import get_credential, get_project_client

_AZ_LOGIN_STATE: dict = {"running": False, "code": None, "url": None, "error": None}


@app.get("/api/azure-status")
async def azure_status():
    """Probe Azure auth + Foundry project connectivity (best-effort, fast)."""
    cred = get_credential()
    azure_ok = False
    azure_user: _Optional[str] = None
    azure_err: _Optional[str] = None

    # First: ask the az CLI directly — it's the most reliable signal of "logged in".
    if _shutil.which("az"):
        try:
            res = await _asyncio.to_thread(
                _subprocess.run,
                ["az", "account", "show", "--query", "user.name", "-o", "tsv"],
                capture_output=True, text=True, timeout=4,
            )
            if res.returncode == 0:
                azure_user = (res.stdout or "").strip() or None
                if azure_user:
                    azure_ok = True
        except Exception:
            pass

    # If az CLI didn't confirm, fall back to attempting a token (covers SP / MI scenarios).
    if not azure_ok and cred is not None:
        try:
            tok = await _asyncio.to_thread(
                cred.get_token, "https://cognitiveservices.azure.com/.default"
            )
            azure_ok = bool(tok and tok.token)
        except Exception as exc:
            azure_err = str(exc)[:140]

    foundry_ok = False
    foundry_endpoint = os.getenv("AZURE_AI_PROJECT_ENDPOINT")
    foundry_name: _Optional[str] = None
    foundry_err: _Optional[str] = None
    if foundry_endpoint:
        # Extract /api/projects/<name>
        m = _re_login.search(r"/api/projects/([^/?#]+)", foundry_endpoint)
        if m:
            foundry_name = m.group(1)
        if azure_ok:
            try:
                pc = get_project_client()
                if pc is not None:
                    # Touch a cheap method to validate endpoint reachable
                    await _asyncio.to_thread(lambda: list(pc.connections.list())[:1])
                    foundry_ok = True
            except Exception as exc:
                foundry_err = str(exc)[:140]

    if azure_ok and foundry_ok:
        state = "ok"
    elif azure_ok:
        state = "degraded"
    else:
        state = "error"

    return {
        "state": state,
        "azure": {"ok": azure_ok, "user": azure_user, "error": azure_err},
        "foundry": {
            "ok": foundry_ok,
            "project": foundry_name,
            "endpoint": foundry_endpoint,
            "error": foundry_err,
        },
    }


@app.post("/api/azure-login")
async def azure_login_start():
    """Start `az login --use-device-code` in background; capture device code."""
    if _AZ_LOGIN_STATE.get("running"):
        return {
            "running": True,
            "code": _AZ_LOGIN_STATE.get("code"),
            "url": _AZ_LOGIN_STATE.get("url"),
        }
    if not _shutil.which("az"):
        return JSONResponse(
            {"error": "az CLI não disponível no container."}, status_code=500
        )

    _AZ_LOGIN_STATE.update({"running": True, "code": None, "url": None, "error": None})

    async def _runner():
        try:
            proc = await _asyncio.create_subprocess_exec(
                "az", "login", "--use-device-code",
                stdout=_asyncio.subprocess.PIPE,
                stderr=_asyncio.subprocess.STDOUT,
            )
            assert proc.stdout is not None
            buf: list[str] = []
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                txt = line.decode(errors="replace")
                buf.append(txt)
                m = _re_login.search(
                    r"open the page\s+(\S+)\s+and enter the code\s+(\S+)", txt
                )
                if m:
                    _AZ_LOGIN_STATE["url"] = m.group(1)
                    _AZ_LOGIN_STATE["code"] = m.group(2)
            await proc.wait()
            if proc.returncode != 0:
                _AZ_LOGIN_STATE["error"] = ("".join(buf))[-500:]
            # Reset cached credential so new token is picked up
            try:
                get_credential.cache_clear()  # type: ignore[attr-defined]
                get_project_client.cache_clear()  # type: ignore[attr-defined]
            except Exception:
                pass
        except Exception as exc:
            _AZ_LOGIN_STATE["error"] = str(exc)
        finally:
            _AZ_LOGIN_STATE["running"] = False

    _asyncio.create_task(_runner())
    # Wait briefly so the device code is usually populated before responding
    for _ in range(20):
        if _AZ_LOGIN_STATE.get("code") or not _AZ_LOGIN_STATE.get("running"):
            break
        await _asyncio.sleep(0.25)

    return {
        "running": _AZ_LOGIN_STATE.get("running"),
        "code": _AZ_LOGIN_STATE.get("code"),
        "url": _AZ_LOGIN_STATE.get("url"),
        "error": _AZ_LOGIN_STATE.get("error"),
    }


@app.get("/api/azure-login")
async def azure_login_status():
    return {
        "running": _AZ_LOGIN_STATE.get("running"),
        "code": _AZ_LOGIN_STATE.get("code"),
        "url": _AZ_LOGIN_STATE.get("url"),
        "error": _AZ_LOGIN_STATE.get("error"),
    }


@app.post("/api/azure-logout")
async def azure_logout():
    """Run `az logout` inside the container and clear cached credentials."""
    if not _shutil.which("az"):
        return JSONResponse(
            {"error": "az CLI não disponível no container."}, status_code=500
        )
    try:
        proc = await _asyncio.create_subprocess_exec(
            "az", "logout",
            stdout=_asyncio.subprocess.PIPE,
            stderr=_asyncio.subprocess.STDOUT,
        )
        out_b, _ = await proc.communicate()
        out = (out_b or b"").decode(errors="replace")[-500:]
        try:
            get_credential.cache_clear()  # type: ignore[attr-defined]
            get_project_client.cache_clear()  # type: ignore[attr-defined]
        except Exception:
            pass
        _AZ_LOGIN_STATE.update({"running": False, "code": None, "url": None, "error": None})
        return {"ok": proc.returncode == 0, "output": out}
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        "home.html",
        {
            "request": request,
            "menu": MENU,
            "agenda": AGENDA,
            "requirements_count": REQUIREMENTS_COUNT,
        },
    )


@app.get("/healthz")
async def healthz():
    return {
        "status": "ok",
        "agenda_items": len(AGENDA),
        "sections_loaded": len(SECTIONS),
    }
