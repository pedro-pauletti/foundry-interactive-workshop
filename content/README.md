# Localized workshop content

This directory holds the editorial source-of-truth for the workshop, separated from code.

## Structure

```
content/
├── pt/                  # Portuguese — original source of truth
│   ├── agenda.yaml      # 18 workshop items: id, slug, title, description, icon
│   ├── workshop.yaml    # UI chrome strings (sidebar, groups, section_page)
│   └── sections/        # Per-section .yaml (front-matter) + .md (body) — Phase 2
├── en/                  # English
│   ├── agenda.yaml
│   ├── workshop.yaml
│   └── sections/
└── es/                  # Español
    ├── agenda.yaml
    ├── workshop.yaml
    └── sections/
```

## Rules

1. **`id` and `slug` are identifiers**, never translated. They must match exactly
   across all three languages and must match a section package folder under
   `src/app/webApp/app/sections/<slug>/`.
2. **`pt` is the fallback.** If a key is missing in `en` or `es`, the loader
   falls back to the `pt` value (then to the key path itself).
3. **HTML is allowed** in `description` and `workshop.yaml` strings — content
   is trusted (authored by maintainers, never user input). Templates render
   with `|safe`.
4. Body content (Phase 2) lives in `sections/<slug>.yaml` with two top-level
   keys: `section` (title, description, eyebrow, eyebrow_icon) and `body`
   (pillars, requisitos, blocks/resumo/bullets, passos, tutorial_passos,
   extra_html, mensagem_chave, etc.). HTML is allowed throughout.
5. **`body_localized: true`** is set automatically when a section's body is
   sourced from its own per-language YAML — this suppresses the "Heads up,
   this body is still in Portuguese" notice in the UI.

## Migrated sections (Phase 2)

These sections render entirely from `content/<lang>/sections/<slug>.yaml`:

- `visao_geral`
- `estrutura_projetos`
- `ato1_criacao_agente`
- `ato1_llm_arena`
- `ato2_cicd`
- `ato3_agent365_purview`

Their `app/sections/<slug>/__init__.py` is a 10-line stub that calls
`make_content_router_from_files("<slug>")`. To edit the text/HTML of these
sections, edit the YAML files directly — no Python changes needed.

The legacy Python source has been preserved alongside as
`__init__.py.legacy.bak` (one-time migration reference; safe to delete).

To migrate another factory-based section, run:

```bash
python scripts/export_section_to_content.py <slug> [<slug> ...]
```

…then replace its `__init__.py` with the slim stub pattern above.

## Custom-routed sections (Phase 3)

The 12 sections under `app/sections/` that have their own `router.py` +
`templates/index.html` (e.g. `mapeamento`, `ato1_modelagem`, `ato2_red_teaming`,
etc.) keep their Python orchestration but can source per-string UI text from
content YAML via an optional top-level `texts:` block:

```yaml
section:
  title: ...
  description: ...
  eyebrow: ...

texts:
  intro_eyebrow: My eyebrow
  intro_title: My title
  some_html_block: "Has <strong>HTML</strong> &mdash; render with | safe"
  count_template: "{visible} of {total} items"   # for inline JS via data-*
```

In templates:

```jinja
<h2>{{ request.state.texts.get('intro_title', 'PT fallback') }}</h2>
<p>{{ request.state.texts.get('some_html_block', '') | safe }}</p>
```

For strings consumed by inline JavaScript, pass them through a `data-*`
attribute on a host element and read it from JS — see
`app/sections/mapeamento/templates/index.html` (`data-count-template`) for the
canonical example.

Migrated so far: `mapeamento`. Remaining 11 follow the same pattern (no
Python changes required; only add `texts:` to the 3 YAML files and replace
hardcoded strings in the template).

## Validating

```bash
python scripts/validate_i18n.py
```

This checks parity: every key/id in `pt/` must exist in `en/` and `es/`.
