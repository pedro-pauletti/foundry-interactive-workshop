# Workshop infrastructure setup

Provisioning of the two Azure AI Search indexes and the five Microsoft Foundry agents, plus the two
local agents (LangGraph and Microsoft Agent Framework) that run alongside the `webApp` in their own
containers.

## Pre-provisioned Azure resources

| Type                 | Name                           |
|----------------------|--------------------------------|
| Foundry account      | `foundry-ai-framework`         |
| Foundry project      | `proj-ai-framework`            |
| Azure AI Search      | `ai-search-ai-framework`       |
| Application Insights | `ai-framework-app-insights`    |
| APIM (AI Gateway)    | `ai-framework-gateway`         |
| Log Analytics WS     | `law-framework-ai`             |

> **Required RBAC** — see the header of [`infra/scripts/example.env`](./example.env).

## 1. Configure `.env`

```powershell
# infra/scripts/.env (used by the notebooks)
Copy-Item infra\scripts\example.env infra\scripts\.env
# Edit infra\scripts\.env with:
#   AZURE_SUBSCRIPTION_ID, AZURE_RESOURCE_GROUP,
#   APPLICATIONINSIGHTS_CONNECTION_STRING,
#   LOG_ANALYTICS_WORKSPACE_ID, APIM_SUBSCRIPTION_KEY
```

And the `.env` for each microservice (dev host only):

```powershell
Copy-Item src\app\webApp\example.env         src\app\webApp\.env
Copy-Item src\app\langgraphAgent\example.env src\app\langgraphAgent\.env
Copy-Item src\app\mafwAgent\example.env      src\app\mafwAgent\.env
```

## 2. Sign in to Azure (host)

```powershell
az login --use-device-code
az account set --subscription <id>
```

The containers reuse this cache via a `~/.azure` volume mount. After `docker compose up`, run
`az login` *once per container*:

```powershell
docker exec -it framework-ia-contoso-webapp           az login --use-device-code
docker exec -it framework-ia-contoso-langgraph-agent  az login --use-device-code
docker exec -it framework-ia-contoso-mafw-agent       az login --use-device-code
```

## 3. Provision the AI Search indexes

Open and run all cells in [`provision_indexes.ipynb`](./provision_indexes.ipynb). It creates or
recreates:

- `telecom-products` (30 docs: mobile plans, fiber/TV, devices)
- `internal-regulations` (21 docs: HR, Information Security, LGPD)

Both with the built-in AOAI vectorizer (no key) and semantic ranking enabled.

## 4. Provision the Foundry agents

Run [`provision_agents.ipynb`](./provision_agents.ipynb). It idempotently creates 5 agents:

| Agent                           | Knowledge                | Role                                        |
|---------------------------------|--------------------------|---------------------------------------------|
| `especialista-produtos`         | `telecom-products`       | Product catalog                             |
| `especialista-regulamentos`     | `internal-regulations`   | HR / InfoSec / LGPD                         |
| `especialista-suporte-tecnico`  | `telecom-products`       | Connectivity & troubleshooting              |
| `especialista-vendas`           | `telecom-products`       | Sales recommendations                       |
| `orquestrador-atendimento`      | (Connected Agents)       | Routes to the right specialist              |

## 5. Start the local stack

```powershell
docker compose up -d --build
```

| Service          | URL                       |
|------------------|---------------------------|
| Web App          | <http://localhost:8080>   |
| LangGraph agent  | <http://localhost:8090>   |
| MAFW agent       | <http://localhost:8091>   |

Smoke test the local agents:

```powershell
$body = '{"message":"I want a 5G family plan"}'
Invoke-WebRequest -Uri http://localhost:8090/chat -Method POST -ContentType 'application/json' -Body $body -UseBasicParsing | Select-Object -ExpandProperty Content

$body = '{"message":"Can I use personal ChatGPT to review a customer contract?"}'
Invoke-WebRequest -Uri http://localhost:8091/chat -Method POST -ContentType 'application/json' -Body $body -UseBasicParsing | Select-Object -ExpandProperty Content
```

## 6. Optional telemetry

To send traces from the local agents to Application Insights, fill
`APPLICATIONINSIGHTS_CONNECTION_STRING` in each microservice's `.env`. OpenTelemetry wiring can be
added later in `app.py` via `azure-monitor-opentelemetry`.
