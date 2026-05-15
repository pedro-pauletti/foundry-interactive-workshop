"""LLM Arena — content from content/{lang}/sections/ato1_llm_arena.yaml."""

from section_factory import make_content_router_from_files

MENU_TITLE = "LLM Arena & Comparação de Modelos"
MENU_ICON = "fa-solid fa-trophy"

router = make_content_router_from_files("ato1_llm_arena")

__all__ = ["router", "MENU_TITLE", "MENU_ICON"]
