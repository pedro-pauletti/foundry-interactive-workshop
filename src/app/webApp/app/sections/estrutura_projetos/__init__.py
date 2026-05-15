"""Estrutura de Projetos do Foundry — content from content/{lang}/sections/estrutura_projetos.yaml."""

from section_factory import make_content_router_from_files

MENU_TITLE = "Estrutura de Projetos do Foundry"
MENU_ICON = "fa-solid fa-sitemap"

router = make_content_router_from_files("estrutura_projetos")

__all__ = ["router", "MENU_TITLE", "MENU_ICON"]
