"""Criação Simplificada de Agente — content from content/{lang}/sections/ato1_criacao_agente.yaml."""

from section_factory import make_content_router_from_files

MENU_TITLE = "Criação Simplificada de Agente"
MENU_ICON = "fa-solid fa-wand-magic-sparkles"

router = make_content_router_from_files("ato1_criacao_agente")

__all__ = ["router", "MENU_TITLE", "MENU_ICON"]
