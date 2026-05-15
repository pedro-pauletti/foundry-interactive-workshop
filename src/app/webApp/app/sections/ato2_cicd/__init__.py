"""CI/CD de Avaliações — content from content/{lang}/sections/ato2_cicd.yaml."""

from section_factory import make_content_router_from_files

MENU_TITLE = "CI/CD de Avaliações com Evidência Auditável"
MENU_ICON = "fa-solid fa-code-pull-request"

router = make_content_router_from_files("ato2_cicd")

__all__ = ["router", "MENU_TITLE", "MENU_ICON"]
