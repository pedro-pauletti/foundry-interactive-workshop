# Framework AI Contoso · Microsoft Workshop

Local-first demo that maps the requirements of the **Contoso AI Framework** to Microsoft's AI stack
(centered on **Microsoft Foundry**), structured as a 3-act journey:
**Build → Validate → Operate & Govern**.

The sidebar and section pages are generated dynamically from [`agenda.md`](./agenda.md) — editing
that file updates the menu automatically.

---

## ⚠️ Important: public demo vs. local execution

This repository ships with two execution modes. **Read this carefully before deploying or sharing
the project.**

### 🔒 Public deployment (GitHub Pages) — mock data only

A static snapshot of the app is published automatically to GitHub Pages on every push to `main`
(workflow: [`.github/workflows/deploy-pages.yml`](./.github/workflows/deploy-pages.yml)).
The public build is intentionally restricted:

- The environment variable `DISABLE_REAL_MODE=1` is set during the build, which **forces mock mode
  server-side**. The "Real mode" toggle in the UI is locked and the `POST /api/demo-mode` endpoint
  rejects any attempt to switch to real mode with HTTP 403.
- **No Azure credentials, endpoints, agent IDs, search indexes, or Content Safety resources are
  used.** The public site is a static HTML/CSS/JS snapshot — there is no server to call Azure
  from. Interactive widgets that POST to per-section APIs will not work; they exist for the
  local experience only.
- A "Public demo" banner is displayed at the top of every page to make this explicit to visitors.

> **The public deployment is for browsing the workshop content with mocked data. It is *not* a
> hosted instance of the real product.**

### 🛠️ Local execution — full experience (Azure required)

To exercise the real flows (Foundry agents, Azure AI Search RAG, Content Safety, etc.) you must
clone this repository and run it on your own machine with your own Azure subscription. You are
responsible for:

- Provisioning the Azure resources (Foundry project, agents, AI Search indexes, Content Safety,
  storage, etc.). See [`infra/scripts/README.md`](./infra/scripts/README.md).
- Populating `.env` files with **your** endpoints and credentials.
- Any costs incurred by your own Azure usage.

Neither this repository nor its maintainers provide hosted Azure resources, secrets, or quota.

---

## What's inside

- 📋 **Contoso Requirements × Microsoft Stack mapping** — filterable table with 24 requirements.
- 🛠️ **Act 1 · Build** — agent creation, versioned prompts, LLM Arena, live RAG chat.
- 🧪 **Act 2 · Validate** — evaluators, red teaming, CI/CD with auditable evidence.
- 📡 **Act 3 · Operate & Govern** — observability, governance, Agent 365, Purview, cost.

---

## Quick start (local, full experience)

```bash
cd src/app/webApp
cp example.env .env
# edit .env with your Foundry endpoint and agent name
docker compose up --build
# open http://localhost:8080
```

### Requirements for the live RAG chat demo

The **Act 1 · RAG with Foundry IQ** section calls a real **Microsoft Foundry** agent. You need:

1. A **Foundry Project** with at least one published agent.
2. `az login` on the host (the cache is mounted at `/root/.azure` inside the container).
3. `.env` configured with:
   - `AZURE_AI_PROJECT_ENDPOINT=https://<resource>.services.ai.azure.com/api/projects/<project>`
   - `AZURE_AI_AGENT_NAME=<your-agent-name>`

If you run `az login` after `docker compose up`, re-authenticate the running container:

```bash
docker exec -it framework-ia-contoso-webapp az login
```

### Running without Docker

```bash
cd src/app/webApp
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
cd app
uvicorn app:app --reload --port 8080
```

---

## Quick start (mock mode only, no Azure)

If you just want to browse the demo with mocked data — equivalent to the public GitHub Pages
build — set `DISABLE_REAL_MODE=1` before starting the app:

```powershell
$env:DISABLE_REAL_MODE = "1"; $env:DEMO_MODE_DEFAULT = "mock"
docker compose up --build
```

Useful for previewing what visitors see on the public site.

---

## Building the static site locally

The same build that runs in GitHub Actions can be run locally:

```bash
pip install -r src/app/webApp/requirements.txt
python infra/scripts/build_static_site.py --out dist --base-url ""
python -m http.server --directory dist 8000
# open http://localhost:8000
```

For deployment under a subpath (e.g. `https://<user>.github.io/<repo>`), pass
`--base-url "/<repo>"`.

---

## Project layout

```
agenda.md                        # sidebar items (heading "### Workshop App")
data/vivo/requirements.json      # 24 mapped requirements
infra/scripts/
  build_static_site.py           # GitHub Pages static export
  provision_*.ipynb              # Azure provisioning notebooks
.github/workflows/deploy-pages.yml  # public demo CI
src/app/webApp/
  Dockerfile, docker-compose.yml, requirements.txt, example.env
  app/
    app.py                       # FastAPI + menu middleware
    agenda_loader.py             # parser for agenda.md
    section_factory.py           # helper for content sub-apps
    demo_mode.py                 # real/mock toggle + DISABLE_REAL_MODE kill switch
    i18n.py                      # EN/PT/ES translation layer
    industry.py                  # industry pack selector
    sections/
      mapeamento/                # filterable requirements table
      visao_geral/
      ato1_*/                    # Act 1 sub-apps (one with live chat)
      ato2_*/                    # Act 2 sub-apps
      ato3_*/                    # Act 3 sub-apps
    templates/
      base.html, home.html, _section_page.html
    static/
      css/styles.css             # Contoso theme
      microsoft-logo.png, contoso-logo.svg
```

---

## Customizing the sidebar

Edit [`agenda.md`](./agenda.md) under the `### Workshop App` heading. Each item:

```markdown
- <title>: <short description without colons>
```

The title must match (case-insensitive substring) the `MENU_TITLE` of a sub-app in
`src/app/webApp/app/sections/`.

---

## Languages

The web app is multilingual: **English (default), Portuguese, Spanish**. Language is controlled by
the `lang` cookie (set via the language switcher in the sidebar) and falls back to `LANG_DEFAULT`
env var, then to `en`. Translation strings live in
[`src/app/webApp/app/i18n.py`](./src/app/webApp/app/i18n.py).

> **Note:** UI chrome, menu, and the home page are fully translated. Per-section body content is
> still mostly in pt-BR and is being translated incrementally.

---

## Environment variables (summary)

| Variable | Purpose | Where |
|---|---|---|
| `DISABLE_REAL_MODE` | When truthy (`1`/`true`/`yes`), forces mock mode and rejects real-mode requests. Used by the public GitHub Pages build. | webApp |
| `DEMO_MODE_DEFAULT` | Initial mode (`real` or `mock`) when no cookie is set. | webApp |
| `LANG_DEFAULT` | Initial language (`en`/`pt`/`es`) when no cookie is set. | webApp |
| `INDUSTRY_DEFAULT` | Initial industry pack. | webApp |
| `AZURE_AI_PROJECT_ENDPOINT` | Foundry project endpoint. | webApp (real mode) |
| `AZURE_AI_AGENT_NAME` | Foundry agent name for the RAG chat. | webApp (real mode) |

See [`src/app/webApp/example.env`](./src/app/webApp/example.env) for the full list.

---

## Pushing this project to your own GitHub repo

This repository is not yet initialized as a git repo locally. To publish it:

```bash
git init
git add .
git commit -m "Initial commit: Framework AI Contoso workshop"
git branch -M main
git remote add origin https://github.com/<your-user>/<your-repo>.git
git push -u origin main
```

After the first push:

1. In your repo on GitHub, open **Settings → Pages** and set **Source = GitHub Actions**.
2. The workflow `.github/workflows/deploy-pages.yml` will run on every push to `main` and publish
   the static demo to `https://<your-user>.github.io/<your-repo>/`.

> **Reminder:** never commit `.env` files. The `.gitignore` already excludes them.

---

## License & disclaimer

This is a workshop demonstration project. It is provided as-is, with no warranty. The maintainers
do not host any Azure resources for users of this repository — to use the real experience, run it
locally on your own Azure subscription as documented above.
