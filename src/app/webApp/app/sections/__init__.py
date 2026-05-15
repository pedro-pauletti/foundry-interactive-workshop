"""Auto-discover every section sub-app and expose its router + menu metadata."""

from __future__ import annotations

import importlib
import pkgutil
from typing import List, Tuple

from fastapi import APIRouter


def collect_routers() -> List[Tuple[str, APIRouter, str, str]]:
    """Return (slug, router, menu_title, menu_icon) for every section package."""
    found: List[Tuple[str, APIRouter, str, str]] = []
    for mod in pkgutil.iter_modules(__path__):
        if mod.name.startswith("_"):
            continue
        pkg = importlib.import_module(f"{__name__}.{mod.name}")
        router = getattr(pkg, "router", None)
        if router is None:
            continue
        found.append(
            (
                mod.name,
                router,
                getattr(pkg, "MENU_TITLE", mod.name.replace("_", " ").title()),
                getattr(pkg, "MENU_ICON", "fa-solid fa-cube"),
            )
        )
    return found
