"""Export an existing section module's SECTION/BODY/BODY_I18N to ``content/{lang}/sections/{slug}.yaml``.

Usage:
    python scripts/export_section_to_content.py <slug> [<slug> ...]

The script imports ``app.sections.<slug>`` from the webApp app/ folder, reads
its ``SECTION``, ``BODY``, optional ``SECTION_I18N`` and ``BODY_I18N`` dicts,
and writes three YAML files: ``content/{pt,en,es}/sections/<slug>.yaml``.

For PT the section/body are taken as-is from SECTION/BODY.
For EN/ES, the PT base is merged with the matching ``*_I18N[lang]`` overrides.

This is a one-shot migration helper. After running it, the section's
``__init__.py`` can be slimmed to just menu metadata + a call to
``make_content_router_from_files(<slug>)``.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any, Dict

import yaml


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
WEBAPP_APP = ROOT / "src" / "app" / "webApp" / "app"
CONTENT_ROOT = ROOT / "content"
LANGUAGES = ("pt", "en", "es")


def _deep_merge(base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = dict(base)
    for k, v in (overlay or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _import_section(slug: str):
    if str(WEBAPP_APP) not in sys.path:
        sys.path.insert(0, str(WEBAPP_APP))
    # Monkey-patch make_content_router to capture inline section_i18n / body_i18n kwargs
    # (some sections pass them inline rather than via module-level *_I18N attributes).
    import section_factory  # type: ignore

    captured: Dict[str, Any] = {}
    original = section_factory.make_content_router

    def _spy(slug_arg, section, body, section_i18n=None, body_i18n=None):
        captured["slug"] = slug_arg
        captured["section"] = section
        captured["body"] = body
        captured["section_i18n"] = section_i18n or {}
        captured["body_i18n"] = body_i18n or {}
        return original(slug_arg, section, body, section_i18n=section_i18n, body_i18n=body_i18n)

    section_factory.make_content_router = _spy
    try:
        # Force fresh import so the spy is in effect.
        mod_name = f"sections.{slug}"
        if mod_name in sys.modules:
            del sys.modules[mod_name]
        mod = importlib.import_module(mod_name)
    finally:
        section_factory.make_content_router = original
    # Attach captured kwargs onto the module so _build_lang_payload sees them.
    if captured:
        if not getattr(mod, "SECTION_I18N", None):
            mod.SECTION_I18N = captured.get("section_i18n") or {}
        if not getattr(mod, "BODY_I18N", None):
            mod.BODY_I18N = captured.get("body_i18n") or {}
    return mod


def _build_lang_payload(mod, lang: str) -> Dict[str, Any]:
    section_base = dict(getattr(mod, "SECTION", {}) or {})
    body_base = dict(getattr(mod, "BODY", {}) or {})
    section_i18n = getattr(mod, "SECTION_I18N", {}) or {}
    body_i18n = getattr(mod, "BODY_I18N", {}) or {}

    if lang == "pt":
        section = section_base
        body = body_base
    else:
        section = _deep_merge(section_base, section_i18n.get(lang, {}) or {})
        body = _deep_merge(body_base, body_i18n.get(lang, {}) or {})

    # File-sourced sections are explicit per-lang — mark accordingly.
    body.setdefault("body_localized", True)
    return {"section": section, "body": body}


def export_one(slug: str) -> None:
    mod = _import_section(slug)
    for lang in LANGUAGES:
        out_dir = CONTENT_ROOT / lang / "sections"
        out_dir.mkdir(parents=True, exist_ok=True)
        payload = _build_lang_payload(mod, lang)
        out_path = out_dir / f"{slug}.yaml"
        with out_path.open("w", encoding="utf-8") as fh:
            yaml.safe_dump(
                payload,
                fh,
                allow_unicode=True,
                sort_keys=False,
                width=120,
                default_flow_style=False,
            )
        print(f"wrote {out_path.relative_to(ROOT)}")


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    for slug in argv:
        export_one(slug)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
