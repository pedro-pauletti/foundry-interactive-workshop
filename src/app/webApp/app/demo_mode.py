"""Demo mode toggle — alterna entre execução real (Azure) e mock local.

Resolução do modo (prioridade):
  1. variável ``DISABLE_REAL_MODE`` (.env) — se truthy, força ``mock`` sempre
  2. cookie ``demo_mode`` (set por /api/demo-mode via UI)
  3. variável ``DEMO_MODE_DEFAULT`` (.env)
  4. fallback ``"real"``

Sub-apps consultam ``is_real(request)``. Se ``False`` ou se a chamada real
falhar, devolvem o mock — sempre incluindo no payload um campo ``source`` =
``"real" | "mock"`` para a UI exibir o badge correto.

When ``DISABLE_REAL_MODE`` is set (e.g. on the public GitHub Pages build),
``real_mode_disabled()`` returns ``True`` so the UI can hide the toggle and
the API endpoints reject attempts to switch to real mode.
"""

from __future__ import annotations

import os
from typing import Literal

from fastapi import Request, Response

DemoMode = Literal["real", "mock"]
COOKIE_NAME = "demo_mode"
_VALID = {"real", "mock"}
_TRUTHY = {"1", "true", "yes", "on"}


def real_mode_disabled() -> bool:
    """Public-build kill switch — force mock mode regardless of cookie/env."""
    return (os.getenv("DISABLE_REAL_MODE") or "").strip().lower() in _TRUTHY


def default_mode() -> DemoMode:
    if real_mode_disabled():
        return "mock"
    val = (os.getenv("DEMO_MODE_DEFAULT") or "real").strip().lower()
    return "mock" if val == "mock" else "real"


def get_mode(request: Request) -> DemoMode:
    if real_mode_disabled():
        return "mock"
    cookie = (request.cookies.get(COOKIE_NAME) or "").strip().lower()
    if cookie in _VALID:
        return cookie  # type: ignore[return-value]
    return default_mode()


def is_real(request: Request) -> bool:
    return get_mode(request) == "real"


def set_mode_cookie(response: Response, mode: str) -> DemoMode:
    """Persist the user's choice for ~30 days. Returns the normalized mode.
    If real mode is disabled by env, the choice is forced to ``mock``."""
    if real_mode_disabled():
        norm: DemoMode = "mock"
    else:
        norm = "mock" if str(mode).strip().lower() == "mock" else "real"
    response.set_cookie(
        key=COOKIE_NAME,
        value=norm,
        max_age=60 * 60 * 24 * 30,
        path="/",
        samesite="lax",
    )
    return norm


__all__ = [
    "DemoMode",
    "COOKIE_NAME",
    "default_mode",
    "get_mode",
    "is_real",
    "set_mode_cookie",
    "real_mode_disabled",
]
