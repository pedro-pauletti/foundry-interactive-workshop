"""Visão Geral da Stack — content sourced from content/{lang}/sections/visao_geral.yaml."""

from section_factory import make_content_router_from_files

MENU_TITLE = "Visão Geral da Stack & Arquitetura Integrada"
MENU_ICON = "fa-solid fa-diagram-project"

router = make_content_router_from_files("visao_geral")

__all__ = ["router", "MENU_TITLE", "MENU_ICON"]
