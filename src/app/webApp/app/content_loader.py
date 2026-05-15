"""Content loader — file-based i18n source of truth.

Reads localized YAML/Markdown from the sibling ``content/`` directory:

    content/
      pt/                 # Portuguese — source of truth, fallback language
        agenda.yaml       # 18 workshop items (id, slug, title, description, icon)
        workshop.yaml     # UI chrome strings, nested by category (chrome, groups, ...)
        sections/         # Per-section .yaml + .md (Phase 2)
      en/
      es/

Public API:
    resolve_lang(code)                    -> normalized language code
    load_workshop(lang)                   -> nested dict, lazily cached
    load_agenda(lang)                     -> List[ContentAgendaItem], lazily cached
    workshop_t(lang, dotted_key)          -> str (with PT fallback then key itself)
    load_section(lang, slug)              -> SectionContent | None (Phase 2)
    available_languages()                 -> List[str]

The loader purposefully has zero dependencies on the legacy ``i18n.py`` module
so it can be exercised standalone by ``scripts/validate_i18n.py``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LANGUAGES: Tuple[str, ...] = ("pt", "en", "es")
FALLBACK_LANG = "pt"
DEFAULT_LANG_ENV = "LANG_DEFAULT"
DEFAULT_LANG_FALLBACK = "pt"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ContentAgendaItem:
    """One workshop navigation item, sourced from content/<lang>/agenda.yaml."""

    id: str
    slug: str
    title: str
    description: str
    icon: str = "fa-solid fa-cube"


@dataclass(frozen=True)
class SectionContent:
    """Phase 2 section payload: YAML front-matter + Markdown body."""

    slug: str
    front_matter: Dict[str, Any] = field(default_factory=dict)
    body_html: str = ""


# ---------------------------------------------------------------------------
# Content root discovery (mirrors agenda_loader._find_agenda_file)
# ---------------------------------------------------------------------------

def _find_content_root() -> Optional[Path]:
    """Locate the ``content/`` directory.

    1. Sibling of this module (Docker image: ``/app/content``).
    2. Walk up the parent chain (local dev: project root).
    """
    here = Path(__file__).resolve().parent
    candidates: List[Path] = [here / "content"]
    for parent in here.parents:
        candidates.append(parent / "content")
    for p in candidates:
        if p.is_dir():
            return p
    return None


@lru_cache(maxsize=1)
def content_root() -> Optional[Path]:
    return _find_content_root()


# ---------------------------------------------------------------------------
# Language resolution
# ---------------------------------------------------------------------------

def available_languages() -> List[str]:
    return list(LANGUAGES)


def default_lang() -> str:
    env_val = (os.getenv(DEFAULT_LANG_ENV) or "").strip().lower()
    if env_val in LANGUAGES:
        return env_val
    return DEFAULT_LANG_FALLBACK


def resolve_lang(code: Optional[str]) -> str:
    """Normalize an input language code to one of LANGUAGES, with defaulting."""
    if code:
        c = code.strip().lower()
        if c in LANGUAGES:
            return c
    return default_lang()


# ---------------------------------------------------------------------------
# YAML loading (cached)
# ---------------------------------------------------------------------------

def _read_yaml(path: Path) -> Dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except FileNotFoundError:
        return {}
    except yaml.YAMLError as exc:  # pragma: no cover — surfaced at startup
        raise RuntimeError(f"Invalid YAML in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"Expected mapping at top of {path}, got {type(data).__name__}")
    return data


@lru_cache(maxsize=8)
def _load_workshop_raw(lang: str) -> Dict[str, Any]:
    root = content_root()
    if root is None:
        return {}
    return _read_yaml(root / lang / "workshop.yaml")


@lru_cache(maxsize=8)
def _load_agenda_raw(lang: str) -> List[Dict[str, Any]]:
    root = content_root()
    if root is None:
        return []
    data = _read_yaml(root / lang / "agenda.yaml")
    items = data.get("items") or []
    if not isinstance(items, list):
        raise RuntimeError(f"agenda.yaml ({lang}): 'items' must be a list")
    return items


# ---------------------------------------------------------------------------
# Public API — workshop strings
# ---------------------------------------------------------------------------

def load_workshop(lang: str) -> Dict[str, Any]:
    """Return the requested-language workshop dict with PT fallback merged in.

    PT values fill any gap in the requested language so partial coverage
    doesn't break the UI.
    """
    lang = resolve_lang(lang)
    base = _load_workshop_raw(FALLBACK_LANG)
    if lang == FALLBACK_LANG:
        return base
    overlay = _load_workshop_raw(lang)
    return _deep_merge(base, overlay)


def _deep_merge(base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
    """Return a new dict where overlay values win, recursing into nested dicts."""
    out: Dict[str, Any] = dict(base)
    for k, v in overlay.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def workshop_t(lang: str, dotted_key: str) -> Optional[str]:
    """Resolve a dotted key against the workshop dict.

    Returns ``None`` when the key is absent in BOTH the requested language
    and the PT fallback — caller decides whether to fall back further
    (e.g. to the legacy in-code TRANSLATIONS dict).
    """
    data: Any = load_workshop(lang)
    for part in dotted_key.split("."):
        if not isinstance(data, dict) or part not in data:
            return None
        data = data[part]
    return data if isinstance(data, str) else None


# ---------------------------------------------------------------------------
# Public API — agenda
# ---------------------------------------------------------------------------

def load_agenda(lang: str) -> List[ContentAgendaItem]:
    """Return localized agenda items, falling back to PT field-by-field."""
    lang = resolve_lang(lang)
    pt_items = {item.get("id"): item for item in _load_agenda_raw(FALLBACK_LANG) if item.get("id")}
    if lang == FALLBACK_LANG:
        raw_items = list(_load_agenda_raw(FALLBACK_LANG))
    else:
        loc_items = {item.get("id"): item for item in _load_agenda_raw(lang) if item.get("id")}
        # Preserve PT order; overlay loc fields when present.
        raw_items = []
        for item_id, pt_item in pt_items.items():
            merged = dict(pt_item)
            if item_id in loc_items:
                for k, v in loc_items[item_id].items():
                    if v not in (None, ""):
                        merged[k] = v
            raw_items.append(merged)

    out: List[ContentAgendaItem] = []
    for raw in raw_items:
        item_id = str(raw.get("id") or "").strip()
        if not item_id:
            continue
        out.append(
            ContentAgendaItem(
                id=item_id,
                slug=str(raw.get("slug") or item_id),
                title=str(raw.get("title") or item_id),
                description=str(raw.get("description") or ""),
                icon=str(raw.get("icon") or "fa-solid fa-cube"),
            )
        )
    return out


# ---------------------------------------------------------------------------
# Public API — per-section content (Phase 2 scaffold)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=128)
def _load_section_raw(lang: str, slug: str) -> Optional[Dict[str, Any]]:
    root = content_root()
    if root is None:
        return None
    path = root / lang / "sections" / f"{slug}.yaml"
    if not path.exists():
        return None
    return _read_yaml(path)


def load_section_texts(lang: str, slug: str) -> Dict[str, Any]:
    """Return the ``texts:`` mapping from ``content/<lang>/sections/<slug>.yaml``.

    Used by custom-routed sections (Phase 3) that keep their own template but
    want to source per-string translations from the content folder. Falls back
    to PT keys for missing entries via deep-merge.

    Returns an empty dict when neither the requested language nor the PT file
    exists, so templates can use ``texts.get(...)`` patterns safely.
    """
    lang = resolve_lang(lang)
    pt_raw = _load_section_raw(FALLBACK_LANG, slug) or {}
    if lang == FALLBACK_LANG:
        merged: Dict[str, Any] = dict(pt_raw)
    else:
        loc_raw = _load_section_raw(lang, slug) or {}
        merged = _deep_merge(pt_raw, loc_raw)
    texts = merged.get("texts") or {}
    return texts if isinstance(texts, dict) else {}


def load_section_dict(lang: str, slug: str) -> Optional[Dict[str, Any]]:
    """Load ``content/<lang>/sections/<slug>.yaml`` with PT fallback per top-level key.

    Expected YAML shape::

        section:
          title: ...
          description: ...
          eyebrow: ...
          eyebrow_icon: ...
        body:
          pillars: [...]
          requisitos: [...]
          resumo: ...
          ...

    Returns ``{"section": {...}, "body": {...}}`` with PT values filling any
    missing keys in the requested language. Returns ``None`` when neither the
    requested language nor the PT fallback file exists.
    """
    lang = resolve_lang(lang)
    pt_raw = _load_section_raw(FALLBACK_LANG, slug)
    if lang == FALLBACK_LANG or lang not in LANGUAGES:
        raw = pt_raw
    else:
        loc_raw = _load_section_raw(lang, slug)
        if pt_raw is None and loc_raw is None:
            raw = None
        else:
            raw = _deep_merge(pt_raw or {}, loc_raw or {})
    if not raw:
        return None
    section = raw.get("section") or {}
    body = raw.get("body") or {}
    if not isinstance(section, dict) or not isinstance(body, dict):
        return None
    # Default body_localized=True for file-sourced sections (they're explicit per-lang).
    if "body_localized" not in body:
        body = {**body, "body_localized": True}
    return {"section": section, "body": body}


def load_section(lang: str, slug: str) -> Optional[SectionContent]:
    """Load ``content/<lang>/sections/<slug>.yaml`` + ``<slug>.md``.

    Phase 2 — returns ``None`` when files are absent so callers can fall
    back to legacy Python ``BODY`` / ``BODY_I18N`` dicts.
    """
    root = content_root()
    if root is None:
        return None
    lang = resolve_lang(lang)
    fallback_root = root / FALLBACK_LANG / "sections"
    lang_root = root / lang / "sections"

    yaml_path = lang_root / f"{slug}.yaml"
    md_path = lang_root / f"{slug}.md"

    if not yaml_path.exists():
        yaml_path = fallback_root / f"{slug}.yaml"
    if not md_path.exists():
        md_path = fallback_root / f"{slug}.md"

    if not yaml_path.exists() and not md_path.exists():
        return None

    fm = _read_yaml(yaml_path) if yaml_path.exists() else {}

    body_html = ""
    if md_path.exists():
        try:
            from markdown_it import MarkdownIt  # local import — optional dep
            md = MarkdownIt("commonmark", {"html": True}).enable("table")
            body_html = md.render(md_path.read_text(encoding="utf-8"))
        except ImportError:  # pragma: no cover
            body_html = md_path.read_text(encoding="utf-8")

    return SectionContent(slug=slug, front_matter=fm, body_html=body_html)
