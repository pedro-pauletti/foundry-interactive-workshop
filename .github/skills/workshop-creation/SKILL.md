---
name: workshop-creation
description: "Scaffold a local-first, Docker-based multi-microservice + web UI demo project for AI workshops. The web app's left-nav menu and per-section sub-apps are driven dynamically by the sibling `agenda.md` file (read at scaffold time — never hard-coded). Generates FastAPI Python microservices (one per concern: agent, database, search, etc.), a Jinja2 + static-CSS web app that proxies to them, per-service Dockerfile + docker-compose.yml + example.env, and applies a consistent design system with predefined color schemes. Optimized for short workshops where attendees run everything locally with `docker compose up` and connect to remote Azure AI Foundry agents. WHEN: \"workshop demo\", \"new microservices project\", \"AI agent demo app\", \"local FastAPI microservices\", \"docker-compose demo\", \"scaffold AI workshop project\", \"agent + web UI sample\", \"multi-service Python demo\", \"reuse grocery4u structure\", \"capstone-style microservices\", \"agenda-driven workshop app\"."
license: MIT
metadata:
  author: jbrantolivei
  version: "1.0.0"
  basedOn: "amap-capstone (Grocery4U)"
---

# Workshop AI Microservices

> Reusable scaffold for **local-first, container-based, multi-microservice demo apps** that showcase Azure AI Foundry agents during workshops. Each service is an independent FastAPI app with its own `Dockerfile`, `docker-compose.yml`, and `example.env`. A single `webApp` service hosts the demo UI and proxies user actions to the AI microservices.

## When to use

Use this skill when the user asks to:
- Scaffold a new workshop / hackathon / demo project that mixes a web UI with one or more AI-powered microservices.
- Add a new microservice that follows the same Docker + FastAPI + API-key pattern as the existing `app/agentOperations`, `app/cosmosOperations`, `app/searchOperations` services.
- Add a new front-end (chat-style, kiosk-style, dashboard-style) that consumes those microservices.
- Stand up a fully local demo (`docker compose up` per service, or one combined compose file) that talks to remote Azure AI Foundry / Cosmos DB / AI Search backends.

Do **not** use this skill for:
- Production deployments to Azure Container Apps / AKS — hand off to `azure-prepare` once the local demo is validated.
- Single-process notebooks or pure CLI samples.

---

## Rules

1. **Local-first**. Every service MUST run with `docker compose up` from its own folder, with no Azure resources created automatically. Cloud resources (Foundry, Cosmos DB, AI Search, App Insights) are *consumed* via env vars only.
2. **One folder per service** under `src/app/<serviceName>/` with the exact structure defined below. No shared `Dockerfile`.
3. **FastAPI + uvicorn + API-key header**. Every microservice authenticates via `X-API-Key` and falls back to "no auth" only when `API_KEY` is unset (dev-only behavior).
4. **`host.docker.internal` for inter-service URLs** in `example.env`. Never hard-code container names; the services are intended to run as separate compose stacks during workshops so attendees can stop/start them independently.
5. **Each service exposes a unique port** in the 8080–8089 range. Reserve 8080 for `webApp`; assign agent / data / search / etc. to 8081+.
6. **Consistent design system**. Every front-end MUST import the shared CSS variables block (see [Design System](#design-system--color-schemes)) and use Inter + Font Awesome 6 + Jinja2 templates.
7. **No secrets in repo**. Always ship `example.env`; the real `.env` is in `.gitignore`.
8. **Telemetry optional but wired**. If `APPINSIGHTS_CONNECTION_STRING` is set, configure `azure-monitor-opentelemetry`. If unset, services must still start cleanly.
9. **Stateless services**. In-memory dicts are acceptable for workshop demos (e.g., conversation thread cache) but document them as "replace with Redis for production".
10. **Agenda-driven menus**. The web app's primary navigation is **always** generated from the sibling [`agenda.md`](./agenda.md). At scaffold time, parse that file and create one menu entry + one **section sub-app** per agenda item. **Never hard-code** the agenda items inside templates or Python code — they must be re-read from `agenda.md` so the workshop content stays editable without re-scaffolding.

---

## Standard Project Layout

```
<project-root>/
├── README.md
├── requirements.txt              # top-level dev deps for scripts/notebooks
├── example.env                   # master example for shared infra values
├── data/                         # sample JSON data + images
├── infra/                        # Bicep / azd (out of scope for this skill)
├── scripts/                      # data generators, loaders
├── agenda.md                      # SOURCE OF TRUTH for the web-app menu
└── src/
    ├── app/
    │   ├── webApp/               # Front-end (port 8080) — Jinja2 + static
    │   │   └── app/sections/     # one sub-app per agenda.md item (see below)
    │   ├── agentOperations/      # AI agent service (port 8081)
    │   ├── cosmosOperations/     # Database service (port 8082)
    │   ├── searchOperations/     # Search service  (port 8083)
    │   └── <newService>/         # add more services following same pattern
    └── foundry/ search/ fabric/  # optional notebooks for setup
```

### Web app section sub-apps (driven by `agenda.md`)

The `webApp` is split into **content-focused section sub-apps** — one per item parsed from the project's [`agenda.md`](./agenda.md). Each sub-app is a self-contained Python module with its own router, templates, and (optionally) static assets, mounted under a slug derived from its title.

```
src/app/webApp/app/
├── app.py                         # FastAPI root: parses agenda.md + mounts every section
├── agenda_loader.py               # reads ../../../../agenda.md → list[AgendaItem]
├── templates/
│   ├── base.html                  # shared shell: sidebar (menu) + main area
│   └── home.html                  # landing page listing every agenda item
├── static/                        # global css + js
└── sections/
    ├── __init__.py                # auto-discovery: import every section package
    ├── architecture_sketch/       # slug = slugify(agenda title)
    │   ├── __init__.py            # exposes `router: APIRouter`, `MENU_TITLE`, `MENU_ICON`
    │   ├── router.py              # endpoints scoped to /sections/architecture-sketch
    │   ├── templates/             # section-specific Jinja templates (optional)
    │   └── static/                # section-specific assets (optional)
    ├── index_retrieval_plan/
    ├── search_experience/
    ├── ai_agent_integration/
    ├── relevance_optimization/
    ├── validation_evaluation/
    └── roadmap_next_steps/
```

> The folder names above are **examples** generated from the current `agenda.md`. Re-running the skill with a different `agenda.md` MUST produce a different set of section folders — the agenda is the contract, not the code.
```

### Per-service folder (mandatory contents)

```
src/app/<serviceName>/
├── app/
│   ├── app.py                    # FastAPI entry point (var name MUST be `app`)
│   └── (templates/, static/)     # only for webApp-style services
├── Dockerfile
├── docker-compose.yml
├── example.env
├── requirements.txt
└── deploy.ps1                    # optional: per-service Azure push script
```

---

## Microservice Template

### `Dockerfile` (identical for every Python microservice — only the port changes)

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ./app .

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "<PORT>"]
```

### `docker-compose.yml`

```yaml
version: '3.8'
services:
  <service-name>:
    build: .
    ports:
      - "<PORT>:<PORT>"
    env_file: .env
```

### `app/app.py` skeleton (AI microservice variant)

```python
from fastapi import FastAPI, HTTPException, Depends, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from typing import Optional
import os, secrets, logging

# Azure AI Foundry imports — keep only what the service needs
from azure.ai.agents import AgentsClient
from azure.identity import ClientSecretCredential
from azure.monitor.opentelemetry import configure_azure_monitor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------- API key auth ----------
API_KEY = os.getenv("API_KEY")
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def verify_api_key(api_key: str = Security(api_key_header)):
    if not API_KEY:
        return None  # dev fallback
    if not api_key:
        raise HTTPException(status_code=401, detail="API key is missing")
    if not secrets.compare_digest(api_key, API_KEY):
        raise HTTPException(status_code=403, detail="Invalid API key")
    return api_key

app = FastAPI(
    title="<Service> API",
    description="Workshop AI microservice",
    dependencies=[Depends(verify_api_key)],
)

# ---------- Optional telemetry ----------
conn = os.getenv("APPINSIGHTS_CONNECTION_STRING")
if conn:
    configure_azure_monitor(connection_string=conn)

# ---------- Azure AI Foundry ----------
PROJECT_ENDPOINT = os.getenv("AZURE_AI_FOUNDRY_ENDPOINT")

def get_credential():
    return ClientSecretCredential(
        tenant_id=os.environ["AGENT_APP_TENANT_ID"],
        client_id=os.environ["AGENT_APP_CLIENT_ID"],
        client_secret=os.environ["AGENT_APP_SECRET"],
    )

class ChatRequest(BaseModel):
    message: str
    thread_id: Optional[str] = None
    customer_id: Optional[str] = None

@app.post("/chat", tags=["Chat"])
async def chat(req: ChatRequest):
    client = AgentsClient(credential=get_credential(), endpoint=PROJECT_ENDPOINT)
    # ... agent run logic ...
    return {"thread_id": "...", "response": "..."}
```

### `app/app.py` skeleton (web UI variant)

```python
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path
import httpx, os, logging

logging.basicConfig(level=logging.INFO)
app = FastAPI(title="<Demo> Web")

AGENT_API_URL    = os.getenv("AGENT_API_URL",    "http://localhost:8081")
AGENT_API_KEY    = os.getenv("AGENT_API_KEY", "")
DATABASE_API_URL = os.getenv("DATABASE_API_URL", "http://localhost:8082")
DATABASE_API_KEY = os.getenv("DATABASE_API_KEY", "")
SEARCH_API_URL   = os.getenv("SEARCH_API_URL",   "http://localhost:8083")
SEARCH_API_KEY   = os.getenv("SEARCH_API_KEY", "")

base = Path(__file__).parent
templates = Jinja2Templates(directory=str(base / "templates"))
app.mount("/static", StaticFiles(directory=str(base / "static")), name="static")

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("chat.html", {"request": request})
```

### Inter-service env conventions

The web app proxies to each microservice using `<NAME>_API_URL` + `<NAME>_API_KEY` pairs. Inside Docker on Windows/macOS use `host.docker.internal`:

```env
AGENT_API_URL=http://host.docker.internal:8081
AGENT_API_KEY=<your-agent-api-key>
DATABASE_API_URL=http://host.docker.internal:8082
DATABASE_API_KEY=<your-database-api-key>
SEARCH_API_URL=http://host.docker.internal:8083
SEARCH_API_KEY=<your-search-api-key>
```

Each microservice's own `example.env` should expose only the upstream cloud resources it talks to (Foundry, Cosmos, Search, etc.) plus `API_KEY` and `APPINSIGHTS_CONNECTION_STRING`.

### Standard Azure AI Foundry env block (drop into agent service `example.env`)

```env
API_KEY=<your-api-key>

AZURE_AI_FOUNDRY_ENDPOINT=<your-azure-ai-foundry-endpoint>
AZURE_AI_MODEL_DEPLOYMENT=gpt-4o
AZURE_OPEN_AI_ENDPOINT=<your-azure-open-ai-endpoint>
AZURE_AI_FOUNDRY_EMBEDDING_DEPLOYMENT=text-embedding-3-small
AZURE_AI_FOUNDRY_API_KEY=<your-azure-ai-foundry-api-key>

AGENT_NAME=<workshop-agent-name>
AGENT_APP_TENANT_ID=<your-tenant-id>
AGENT_APP_CLIENT_ID=<your-client-id>
AGENT_APP_SECRET=<your-client-secret>

APPINSIGHTS_CONNECTION_STRING=<optional-app-insights-conn-string>
```

### Standard `requirements.txt` blocks

| Service type | requirements.txt |
|---|---|
| Web UI | `fastapi`, `uvicorn`, `httpx`, `jinja2`, `python-dotenv`, `pytest`, `pytest-asyncio` |
| Agent service | `fastapi`, `uvicorn`, `python-dotenv`, `azure-ai-agents`, `azure-ai-projects`, `azure-ai-inference`, `azure-identity`, `azure-monitor-opentelemetry`, `opentelemetry-sdk` |
| Cosmos service | `fastapi`, `uvicorn`, `python-dotenv`, `azure-cosmos` |
| Search service | `fastapi`, `uvicorn`, `python-dotenv`, `azure-search-documents` |

---

## Section Sub-App Template

Each item parsed from [`agenda.md`](./agenda.md) becomes a self-contained Python sub-app inside `webApp/app/sections/<slug>/`. The sub-app is responsible only for **its own content** (templates, partials, JS, optional API calls) and is wired into the root FastAPI app via a router.

### Slug rule

`slug = lowercase(title)` with non-alphanumeric runs collapsed to `_` and trimmed. Example:

| Agenda title | Folder slug |
|---|---|
| Architecture sketch + decision points | `architecture_sketch` |
| Hands on: Index & Retrieval Implementation Plan | `index_retrieval_plan` |
| Hands-on working session: "Design the target search experience" | `search_experience` |
| AI Agent Integration | `ai_agent_integration` |
| Relevance & Performance Optimization | `relevance_optimization` |
| Validation & Evaluation | `validation_evaluation` |
| Roadmap & Next Steps | `roadmap_next_steps` |

### `agenda_loader.py`

```python
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List

AGENDA_FILE = Path(__file__).resolve().parents[3] / "agenda.md"
BULLET_RE = re.compile(r"^\s*[-*]\s*(?P<title>[^:]+?)\s*:\s*(?P<desc>.+?)\s*$")

@dataclass(frozen=True)
class AgendaItem:
    title: str
    description: str
    slug: str

def _slugify(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", text.lower()).strip("_")
    return s or "section"

def load_agenda(path: Path = AGENDA_FILE) -> List[AgendaItem]:
    items: List[AgendaItem] = []
    if not path.exists():
        return items
    in_block = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("###") and "Workshop App" in line:
            in_block = True
            continue
        if in_block and line.strip().startswith("###"):
            break
        m = BULLET_RE.match(line)
        if in_block and m:
            title = m.group("title").strip().strip('"').strip("“”")
            desc  = m.group("desc").strip()
            items.append(AgendaItem(title=title, description=desc, slug=_slugify(title)))
    return items
```

### `sections/__init__.py` (auto-discovery)

```python
import importlib
import pkgutil
from fastapi import APIRouter

def collect_routers() -> list[tuple[str, APIRouter, str, str]]:
    """Returns (slug, router, menu_title, menu_icon) for every section package."""
    found = []
    for mod in pkgutil.iter_modules(__path__):
        pkg = importlib.import_module(f"{__name__}.{mod.name}")
        router = getattr(pkg, "router", None)
        if router is None:
            continue
        found.append((
            mod.name,
            router,
            getattr(pkg, "MENU_TITLE", mod.name.replace("_", " ").title()),
            getattr(pkg, "MENU_ICON", "fa-solid fa-cube"),
        ))
    return found
```

### `sections/<slug>/__init__.py`

```python
from .router import router

MENU_TITLE = "<exact agenda title>"
MENU_ICON  = "fa-solid fa-diagram-project"   # pick from Font Awesome 6
__all__ = ["router", "MENU_TITLE", "MENU_ICON"]
```

### `sections/<slug>/router.py`

```python
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

router = APIRouter(prefix="/sections/<slug>", tags=["<menu title>"])
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

SECTION = {
    "title": "<agenda title>",
    "description": "<agenda description>",
}

@router.get("", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "section": SECTION},
    )
```

### `sections/<slug>/templates/index.html`

```jinja
{% extends "base.html" %}
{% block content %}
<section class="section-page">
  <header class="section-header">
    <h1 class="section-title">{{ section.title }}</h1>
    <p class="section-subtitle">{{ section.description }}</p>
  </header>
  <div class="section-body card--active">
    {# Replace with the hands-on content for this agenda item. #}
    <p>Hands-on content for <strong>{{ section.title }}</strong> goes here.</p>
  </div>
</section>
{% endblock %}
```

### `webApp/app/app.py` (root) wiring

```python
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path

from .agenda_loader import load_agenda
from .sections import collect_routers

base = Path(__file__).parent
app = FastAPI(title="Workshop")
templates = Jinja2Templates(directory=str(base / "templates"))
app.mount("/static", StaticFiles(directory=str(base / "static")), name="static")

AGENDA = load_agenda()
SECTIONS = collect_routers()

# Make the menu available to every template
@app.middleware("http")
async def inject_menu(request: Request, call_next):
    request.state.menu = [
        {"slug": slug, "title": title, "icon": icon, "url": f"/sections/{slug}"}
        for slug, _, title, icon in SECTIONS
    ]
    return await call_next(request)

for slug, router, _, _ in SECTIONS:
    app.include_router(router)

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        "home.html",
        {"request": request, "agenda": AGENDA, "menu": request.state.menu},
    )
```

### `webApp/app/templates/base.html` (sidebar uses the live menu)

```jinja
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{% block title %}Workshop{% endblock %}</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
  <link rel="stylesheet" href="/static/css/styles.css">
</head>
<body>
  <aside class="sidebar">
    <div class="sidebar-header"><i class="fa-solid fa-bolt"></i> Workshop</div>
    <nav class="sidebar-menu">
      {% for item in request.state.menu %}
        <a class="menu-item" href="{{ item.url }}">
          <i class="{{ item.icon }}"></i>
          <span>{{ item.title }}</span>
        </a>
      {% endfor %}
    </nav>
  </aside>
  <main class="main-area">
    {% block content %}{% endblock %}
  </main>
</body>
</html>
```

> **Important:** Do not bake the agenda items into `base.html`, `home.html`, or any Python constant. The menu MUST come from `agenda_loader.load_agenda()` at runtime so editing `agenda.md` updates the app without code changes.

---

## Workflow

When invoked, follow these steps in order. Do not skip ahead.

1. **Confirm scope** with the user:
   - Project name and target folder.
   - List of microservices required (default: `webApp`, `agentOperations`).
   - Color theme (see [palettes](#predefined-color-palettes)) — default `foundry-violet` (dark neon-purple glow).
   - Whether to include sample data + scripts (default: yes).
2. **Read `agenda.md`** from the project root (or from `.github/skills/workshop-creation/agenda.md` if the project copy doesn't yet exist). Parse every bullet under `### Data to be used by SKILL.md to create the Workshop App` into an ordered list of `(title, description)` pairs. This list drives the web-app menu and section sub-apps. **Do not** invent items; if the file is missing, ask the user before continuing.
3. **Scaffold the layout** described in [Standard Project Layout](#standard-project-layout). Create `src/app/<serviceName>/` for every microservice, **plus** `src/app/webApp/app/sections/<slug>/` for every parsed agenda item.
4. **Generate per-service files** using the templates above. Substitute `<PORT>` and `<service-name>` consistently. Reserve port 8080 for `webApp`.
5. **Generate the front-end**:
   - Shared shell: `webApp/app/templates/base.html` + `static/css/styles.css` + `static/js/app.js` using the [Design System](#design-system--color-schemes) variables.
   - `agenda_loader.py` that re-reads `agenda.md` at startup and exposes the menu to every template via a Jinja context processor.
   - One section sub-app per agenda item (see [Section sub-app template](#section-sub-app-template)). The sub-app's content (page heading, intro copy, hands-on hints) is seeded from the agenda item's title + description.
   - Mandatory pages:
     - `/` — landing page listing every agenda section as a card grid.
     - `/sections/<slug>` — one route per agenda item, served by its sub-app router.
     - `/kiosk` — read-only display variant (optional, recommend for retail/IoT scenarios).
6. **Generate `example.env`** for every service. Cross-link inter-service URLs with `host.docker.internal:<port>`.
7. **Generate a top-level `README.md`** with a **Quick Start** section that boots the stack:
   ```bash
   cd src/app/agentOperations  && cp example.env .env && docker compose up --build -d
   cd ../cosmosOperations      && cp example.env .env && docker compose up --build -d
   cd ../searchOperations      && cp example.env .env && docker compose up --build -d
   cd ../webApp                && cp example.env .env && docker compose up --build
   # open http://localhost:8080
   ```
8. **Validate**:
   - Each `Dockerfile` references its own port.
   - Every `app.py` exposes `app = FastAPI(...)` (uvicorn target).
   - The number of folders under `webApp/app/sections/` equals the number of bullets parsed from `agenda.md`.
   - Every parsed agenda title appears in the rendered sidebar of `/`.
   - No real secrets committed; only `example.env` files exist.
9. **Hand-off note**: tell the user to run `azure-prepare` when they want to push the same containers to Azure Container Apps.

---

## Design System & Color Schemes

All front-ends share a single CSS-variable contract so themes are swappable per workshop. Drop the chosen palette block at the top of `static/css/styles.css`, then keep all downstream rules referencing `var(--*)`.

### Required typography & icon stack

```html
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
```

```css
body {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}
```

### Shared variable contract (always present)

```css
:root {
  /* brand */
  --primary-color:    <hex>;
  --primary-hover:    <hex>;
  --primary-light:    <rgba>;
  --primary-gradient: linear-gradient(135deg, <hex> 0%, <hex> 100%);
  --secondary-color:  <hex>;
  --accent-color:     <hex>;

  /* surfaces */
  --background-dark:    <hex>;
  --background-main:    #ffffff;
  --background-light:   <hex>;
  --background-lighter: <hex>;

  /* text */
  --text-primary:   #2d3436;
  --text-secondary: #636e72;
  --text-muted:     #b2bec3;
  --border-color:   <hex>;

  /* chat */
  --user-message-bg:      <gradient>;
  --assistant-message-bg: #ffffff;

  /* glass */
  --glass-bg:        rgba(255,255,255,0.62);
  --glass-bg-strong: rgba(255,255,255,0.78);
  --glass-border:    <rgba>;
  --glass-shadow:    0 18px 60px <rgba>;
  --glass-blur:      18px;

  /* page bg (radial spotlights + gradient) */
  --page-bg: radial-gradient(1200px 800px at 15% 5%,  <rgba>, transparent 60%),
             radial-gradient(1000px 700px at 90% 25%, <rgba>, transparent 55%),
             linear-gradient(180deg, #ffffff 0%, var(--background-dark) 60%, #ffffff 115%);

  /* shape & motion */
  --shadow-sm: 0 2px 4px  <rgba>;
  --shadow-md: 0 4px 12px <rgba>;
  --shadow-lg: 0 10px 30px <rgba>;
  --radius-sm: 12px;
  --radius-md: 16px;
  --radius-lg: 20px;
  --radius-xl: 28px;
  --transition-fast:   0.15s ease;
  --transition-normal: 0.30s ease;
  --transition-smooth: 0.45s cubic-bezier(0.2, 0.8, 0.2, 1);
}
```

### Predefined color palettes

Pick one based on the workshop vertical. Each is production-tested to keep contrast ≥ AA on light surfaces.

#### 1. Citrus Orange — *retail, marketplace, food (matches Grocery4U)*

```css
:root {
  --primary-color:    #ff6b35;
  --primary-hover:    #e55a2b;
  --primary-light:    rgba(255, 107, 53, 0.10);
  --primary-gradient: linear-gradient(135deg, #ff6b35 0%, #f7931e 100%);
  --secondary-color:  #ff9f1c;
  --accent-color:     #ffbf69;
  --background-dark:    #fff5f0;
  --background-light:   #fef7f3;
  --background-lighter: #fff0e8;
  --border-color:       #ffe4d6;
  --user-message-bg:    linear-gradient(135deg, #ff6b35 0%, #ff9f1c 100%);
  --shadow-sm: 0 2px 4px  rgba(255,107,53,0.10);
  --shadow-md: 0 4px 12px rgba(255,107,53,0.15);
  --shadow-lg: 0 10px 30px rgba(255,107,53,0.20);
  --glass-border: rgba(255,107,53,0.12);
  --glass-shadow: 0 18px 60px rgba(255,107,53,0.14);
}
```

#### 2. Azure Blue — *enterprise, Microsoft / Azure-themed sessions*

```css
:root {
  --primary-color:    #0078d4;
  --primary-hover:    #106ebe;
  --primary-light:    rgba(0, 120, 212, 0.10);
  --primary-gradient: linear-gradient(135deg, #0078d4 0%, #50b0ff 100%);
  --secondary-color:  #2b88d8;
  --accent-color:     #50b0ff;
  --background-dark:    #f0f6fc;
  --background-light:   #f5f9fd;
  --background-lighter: #e6f1fb;
  --border-color:       #d0e3f5;
  --user-message-bg:    linear-gradient(135deg, #0078d4 0%, #2b88d8 100%);
  --shadow-md: 0 4px 12px rgba(0,120,212,0.15);
  --glass-border: rgba(0,120,212,0.12);
}
```

#### 3. Foundry Violet — *AI / agent / Foundry-centric workshops (default — dark neon glow)*

Dark, near-black surfaces with a luminous violet → magenta border glow. Inspired by the Microsoft Foundry "widest selection of models" panel: deep space background, soft purple haze in the corners, and a glowing 1px border on the active card.

```css
:root {
  /* brand — neon violet → magenta */
  --primary-color:    #a855f7;   /* violet-500 */
  --primary-hover:    #c084fc;   /* violet-400 */
  --primary-light:    rgba(168, 85, 247, 0.18);
  --primary-gradient: linear-gradient(135deg, #a855f7 0%, #ec4899 100%);
  --secondary-color:  #8b5cf6;
  --accent-color:     #ec4899;

  /* surfaces — deep space */
  --background-dark:    #0a0613;   /* page base, almost-black with purple cast */
  --background-main:    #110a1f;   /* card / chat surface */
  --background-light:   #1a1030;   /* hover, raised elements */
  --background-lighter: #241640;   /* selected row */
  --border-color:       rgba(168, 85, 247, 0.22);

  /* text — high-contrast on dark */
  --text-primary:   #f5f3ff;
  --text-secondary: #c4b5fd;
  --text-muted:     #7c6aa8;

  /* chat bubbles */
  --user-message-bg:      linear-gradient(135deg, #a855f7 0%, #ec4899 100%);
  --assistant-message-bg: #1a1030;

  /* glass — frosted dark with violet rim light */
  --glass-bg:        rgba(26, 16, 48, 0.55);
  --glass-bg-strong: rgba(26, 16, 48, 0.78);
  --glass-border:    rgba(168, 85, 247, 0.35);
  --glass-shadow:    0 0 0 1px rgba(168,85,247,0.45),
                     0 18px 60px rgba(168,85,247,0.28),
                     0 0 80px rgba(236, 72, 153, 0.18);
  --glass-blur:      18px;

  /* page bg — radial purple spotlights on near-black */
  --page-bg: radial-gradient(1200px 800px at 15% 5%,  rgba(168, 85, 247, 0.28), transparent 60%),
             radial-gradient(1000px 700px at 90% 25%, rgba(236,  72, 153, 0.18), transparent 55%),
             radial-gradient(900px  900px at 50% 110%, rgba(124, 58, 237, 0.22), transparent 60%),
             linear-gradient(180deg, #0a0613 0%, #100826 60%, #0a0613 115%);

  /* shadows — neon */
  --shadow-sm: 0 2px 4px  rgba(0,0,0,0.40);
  --shadow-md: 0 4px 14px rgba(168, 85, 247, 0.30);
  --shadow-lg: 0 10px 40px rgba(168, 85, 247, 0.40);
}

/* Optional: glowing border treatment for the "active" card,
   matching the lit-up Models row in the reference image. */
.card--active,
.quick-action:hover,
.menu-item--selected {
  position: relative;
  background: var(--background-light);
  border: 1px solid var(--glass-border);
  box-shadow:
    0 0 0 1px rgba(168, 85, 247, 0.55),
    0 0 24px rgba(168, 85, 247, 0.35),
    0 0 60px rgba(236,  72, 153, 0.20);
}
```

#### 4. Forest Green — *sustainability, healthcare, education*

```css
:root {
  --primary-color:    #16a34a;
  --primary-hover:    #15803d;
  --primary-light:    rgba(22, 163, 74, 0.10);
  --primary-gradient: linear-gradient(135deg, #16a34a 0%, #65a30d 100%);
  --secondary-color:  #22c55e;
  --accent-color:     #84cc16;
  --background-dark:    #f0fdf4;
  --background-light:   #f7fef9;
  --background-lighter: #dcfce7;
  --border-color:       #bbf7d0;
  --user-message-bg:    linear-gradient(135deg, #16a34a 0%, #22c55e 100%);
  --shadow-md: 0 4px 12px rgba(22,163,74,0.18);
}
```

#### 5. Slate Dark — *developer / IoT / dashboards (dark mode)*

```css
:root {
  --primary-color:    #38bdf8;
  --primary-hover:    #0ea5e9;
  --primary-light:    rgba(56, 189, 248, 0.10);
  --primary-gradient: linear-gradient(135deg, #38bdf8 0%, #818cf8 100%);
  --secondary-color:  #818cf8;
  --accent-color:     #f472b6;
  --background-dark:    #0f172a;
  --background-main:    #1e293b;
  --background-light:   #334155;
  --background-lighter: #475569;
  --text-primary:       #f1f5f9;
  --text-secondary:     #cbd5e1;
  --text-muted:         #94a3b8;
  --border-color:       #334155;
  --user-message-bg:    linear-gradient(135deg, #38bdf8 0%, #818cf8 100%);
  --glass-bg:           rgba(30, 41, 59, 0.6);
  --glass-bg-strong:    rgba(30, 41, 59, 0.85);
  --glass-border:       rgba(56, 189, 248, 0.18);
}
```

### Component conventions (apply across all front-ends)

- **Layout**: left **sidebar** (logo, "New chat / search", history, footer status pill) + main **chat area** (header → messages → input). Mirror the structure of `webApp/app/templates/chat.html`.
- **Header**: gradient text title using `background: linear-gradient(135deg, var(--text-primary), var(--primary-color))` + `-webkit-background-clip: text`.
- **Welcome screen**: hero icon, headline, sub-copy, then 3–4 **quick-action buttons** that trigger `sendQuickMessage(...)`. Use Font Awesome icons (`fa-utensils`, `fa-lightbulb`, `fa-coffee`, etc.).
- **Messages**: user bubble uses `var(--user-message-bg)` gradient, assistant bubble uses `var(--assistant-message-bg)` with `var(--shadow-sm)`. Border radius `var(--radius-lg)`.
- **Status indicator**: 8px dot with `pulse` keyframes (1s opacity 1 ↔ 0.5).
- **Modals** (e.g., personalization tags, settings): full-screen overlay `rgba(0,0,0,0.7)`, content panel uses `var(--background-main)` + `var(--radius-lg)` + entrance transform `scale(0.9) translateY(20px) → scale(1) translateY(0)`.
- **Glassmorphism** for cards/panels on top of the radial-gradient page bg:
  ```css
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur));
  border: 1px solid var(--glass-border);
  box-shadow: var(--glass-shadow);
  border-radius: var(--radius-xl);
  ```
- **Buttons**: primary uses solid `var(--primary-color)` + hover `translateY(-1px)` + `var(--shadow-md)`. Secondary uses `var(--background-light)` and primary text color.
- **Quick-action buttons**: 2×2 grid, icon circle on the left (gradient bg), title + helper text on the right.
- **Kiosk variant** (`/kiosk`): same palette, no input box, larger product/recommendation cards, rotates auto-content. Useful for "set it on a screen at the booth" workshops.

### Accessibility & motion

- Maintain **WCAG AA** contrast on text vs. surface — every palette above is pre-checked on `--background-main`.
- Respect reduced motion: wrap non-essential transitions with `@media (prefers-reduced-motion: reduce) { * { transition: none !important; animation: none !important; } }`.
- All interactive controls need a visible `:focus-visible` ring using `var(--primary-color)` + `0 0 0 3px var(--primary-light)`.

---

## Adding a new microservice (recipe)

1. `mkdir src/app/<newService>` and copy the `Dockerfile` + `docker-compose.yml` + `requirements.txt` + `example.env` from a sibling.
2. Pick a free port in 8080–8089. Update `Dockerfile` `CMD` and `docker-compose.yml` `ports`.
3. Drop the [AI microservice `app.py` skeleton](#appapppy-skeleton-ai-microservice-variant) and trim the Azure SDKs you don't need.
4. Add a new env-pair to `webApp/example.env`:
   ```env
   <NAME>_API_URL=http://host.docker.internal:<port>
   <NAME>_API_KEY=<your-key>
   ```
5. In `webApp/app/app.py`, add a proxy route that forwards to `<NAME>_API_URL` with `X-API-Key` header.
6. Add a quick-action button on the welcome screen that exercises the new service.
7. Update the top-level `README.md` Quick Start with the new compose command.

---

## Adding a new section sub-app (recipe)

Use this when the user edits `agenda.md` and wants a new menu entry without re-scaffolding.

1. Add the new bullet to `agenda.md` under `### Data to be used by SKILL.md to create the Workshop App` in the form `- <Title>: <Description>`.
2. Compute the slug with the rule in [Slug rule](#slug-rule).
3. `mkdir src/app/webApp/app/sections/<slug>` and copy `__init__.py`, `router.py`, and `templates/index.html` from a sibling section.
4. Update the new `__init__.py` so `MENU_TITLE` matches the agenda title exactly and pick a Font Awesome icon for `MENU_ICON`.
5. Update `router.py`: change the `prefix` to `/sections/<slug>`, set `SECTION["title"]` and `SECTION["description"]` to match `agenda.md`.
6. Restart the `webApp` container. Auto-discovery (`sections/__init__.py`) and `agenda_loader.load_agenda()` will pick up the new entry — **no edits to `app.py` or `base.html` are required**.
7. Verify the new entry appears in the sidebar and `/sections/<slug>` renders.

---

## Hand-offs

| Goal | Skill to invoke next |
|---|---|
| Push these containers to Azure Container Apps | `azure-prepare` |
| Wire up Application Insights properly | `appinsights-instrumentation` |
| Add or configure the Foundry agent itself | `microsoft-foundry` |
| Stand up Cosmos DB / AI Search infra | `azure-prepare` (Bicep recipes) |
| Validate before deploying | `azure-validate` |
