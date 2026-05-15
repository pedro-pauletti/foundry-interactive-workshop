"""Industry selector — cookie-driven multi-vertical content packs.

Mirrors `demo_mode.py`: a cookie + env-fallback chooses which industry pack
(JSON in `data/industries/<slug>.json`) feeds mocked demo content across the
workshop sections. Packs are cached after first load.
"""

from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import Request, Response

log = logging.getLogger("industry")

COOKIE_NAME = "industry"
COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 days
ENV_VAR = "INDUSTRY_DEFAULT"
DEFAULT_SLUG = "telecom"

# Resolve packs directory: /workspace/data/industries (mounted into webApp via
# absolute path, or fallback to the repo layout when running locally).
_HERE = Path(__file__).resolve().parent
_parents = _HERE.parents
_CANDIDATES = [
    Path(os.getenv("INDUSTRIES_DIR", "")) if os.getenv("INDUSTRIES_DIR") else None,
    Path("/app/data/industries"),                       # in-container mount
    _parents[3] / "data" / "industries" if len(_parents) > 3 else None,
    _parents[4] / "data" / "industries" if len(_parents) > 4 else None,
]
PACKS_DIR: Path = next(
    (p for p in _CANDIDATES if p and p.exists()),
    Path("/app/data/industries"),
)


def default_industry() -> str:
    slug = (os.getenv(ENV_VAR) or DEFAULT_SLUG).strip().lower()
    if slug not in _available_slugs():
        return DEFAULT_SLUG
    return slug


def _available_slugs() -> List[str]:
    try:
        return sorted(p.stem for p in PACKS_DIR.glob("*.json"))
    except Exception as exc:
        log.warning("[industry] cannot list packs at %s: %s", PACKS_DIR, exc)
        return [DEFAULT_SLUG]


def get_industry(request: Request) -> str:
    raw = (request.cookies.get(COOKIE_NAME) or "").strip().lower()
    if raw and raw in _available_slugs():
        return raw
    return default_industry()


def set_industry_cookie(response: Response, slug: str) -> None:
    if slug not in _available_slugs():
        raise ValueError(f"unknown industry: {slug}")
    response.set_cookie(
        COOKIE_NAME,
        slug,
        max_age=COOKIE_MAX_AGE,
        path="/",
        samesite="lax",
        httponly=False,
    )


@lru_cache(maxsize=16)
def load_pack(slug: str) -> Dict:
    path = PACKS_DIR / f"{slug}.json"
    if not path.exists():
        log.warning("[industry] pack not found: %s — falling back to %s", path, DEFAULT_SLUG)
        path = PACKS_DIR / f"{DEFAULT_SLUG}.json"
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def get_pack(request: Request) -> Dict:
    return load_pack(get_industry(request))


def list_industries() -> List[Dict]:
    """Return [{slug,label,company_name}] for the dropdown."""
    out = []
    for slug in _available_slugs():
        try:
            pack = load_pack(slug)
            out.append(
                {
                    "slug": slug,
                    "label": pack.get("label", slug.title()),
                    "company_name": pack.get("company_name", slug.title()),
                }
            )
        except Exception as exc:
            log.warning("[industry] skip pack %s: %s", slug, exc)
    return out
