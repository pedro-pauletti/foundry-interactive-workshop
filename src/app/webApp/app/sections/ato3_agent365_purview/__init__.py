"""Agent 365 e Purview — content from content/{lang}/sections/ato3_agent365_purview.yaml."""

from section_factory import make_content_router_from_files

MENU_TITLE = "Agent 365 e Purview"
MENU_ICON = "fa-solid fa-id-badge"

router = make_content_router_from_files("ato3_agent365_purview")

__all__ = ["router", "MENU_TITLE", "MENU_ICON"]
