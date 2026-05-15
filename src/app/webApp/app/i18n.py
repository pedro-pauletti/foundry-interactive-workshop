"""i18n — cookie-driven language selector (en/pt/es, default en).

Mirrors the `demo_mode` / `industry` pattern:
  1. cookie ``lang``
  2. env ``LANG_DEFAULT``
  3. fallback ``"en"``

UI chrome + section menu titles are translated. Section body content
(demo blocks, mock data, long-form copy) currently stays in Portuguese
and is treated as a follow-up.
"""

from __future__ import annotations

import os
from typing import Dict, List

from fastapi import Request, Response

COOKIE_NAME = "lang"
COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 days
ENV_VAR = "LANG_DEFAULT"
DEFAULT_LANG = "pt"

LANGUAGES: List[Dict[str, str]] = [
    {"code": "en", "label": "English", "flag": "🇺🇸"},
    {"code": "pt", "label": "Português", "flag": "🇧🇷"},
    {"code": "es", "label": "Español", "flag": "🇪🇸"},
]

_VALID = {lng["code"] for lng in LANGUAGES}


# ----------------------------------------------------------------------------
# Translation dictionary.
# Keys are dotted paths. Missing keys fall back to English, then to the key
# itself, so partial coverage doesn't break the UI.
# ----------------------------------------------------------------------------
TRANSLATIONS: Dict[str, Dict[str, str]] = {
    # --- Sidebar / chrome -----------------------------------------------------
    "chrome.toggle_menu": {
        "en": "Toggle menu",
        "pt": "Alternar menu",
        "es": "Alternar menú",
    },
    "chrome.collapse_menu": {
        "en": "Collapse menu",
        "pt": "Recolher menu",
        "es": "Contraer menú",
    },
    "chrome.industry": {
        "en": "Industry",
        "pt": "Indústria",
        "es": "Industria",
    },
    "chrome.industry_tooltip": {
        "en": "Industry used in examples and demos",
        "pt": "Indústria dos exemplos e demos",
        "es": "Industria usada en ejemplos y demos",
    },
    "chrome.language": {
        "en": "Language",
        "pt": "Idioma",
        "es": "Idioma",
    },
    "chrome.language_tooltip": {
        "en": "Interface language",
        "pt": "Idioma da interface",
        "es": "Idioma de la interfaz",
    },
    "chrome.home": {
        "en": "Home",
        "pt": "Início",
        "es": "Inicio",
    },
    "chrome.workshop": {
        "en": "Workshop",
        "pt": "Workshop",
        "es": "Taller",
    },
    "chrome.azure_signin": {
        "en": "Sign in to Azure",
        "pt": "Entrar no Azure",
        "es": "Iniciar sesión en Azure",
    },
    "chrome.azure_signout": {
        "en": "Sign out of Azure",
        "pt": "Sair do Azure",
        "es": "Cerrar sesión de Azure",
    },
    "chrome.azure_device_open": {
        "en": "Open",
        "pt": "Abra",
        "es": "Abre",
    },
    "chrome.azure_device_then": {
        "en": "and enter:",
        "pt": "e digite:",
        "es": "e ingresa:",
    },
    "chrome.demo_toggle_aria": {
        "en": "Toggle demo mode",
        "pt": "Alternar modo de demo",
        "es": "Alternar modo demo",
    },
    "chrome.demo_real_tooltip": {
        "en": "Real mode — calls Foundry, Search, Content Safety. Falls back to local simulation if credentials are missing.",
        "pt": "Modo Real — chama Foundry, Search, Content Safety. Cai pra simulação local se faltar credencial.",
        "es": "Modo Real — llama a Foundry, Search, Content Safety. Cae a simulación local si faltan credenciales.",
    },
    "chrome.demo_mock_tooltip": {
        "en": "Offline mode — everything generated locally, no cost.",
        "pt": "Modo offline — tudo gerado localmente, sem custo.",
        "es": "Modo offline — todo generado localmente, sin costo.",
    },
    "chrome.demo_locked_tooltip": {
        "en": "Real mode is disabled in this public deployment. Clone and run locally with your own Azure credentials to enable it.",
        "pt": "Modo Real está desabilitado nesta versão pública. Clone e execute localmente com suas credenciais Azure para habilitá-lo.",
        "es": "Modo Real está deshabilitado en esta versión pública. Clona y ejecuta localmente con tus credenciales de Azure para habilitarlo.",
    },
    "chrome.public_demo_banner": {
        "en": "<strong>Public demo</strong> — running in <strong>mock mode only</strong>. To exercise real Foundry agents, Azure AI Search and Content Safety, clone the repo and run it locally with your own Azure subscription.",
        "pt": "<strong>Demo público</strong> — rodando apenas em <strong>modo mock</strong>. Para acionar agentes Foundry, Azure AI Search e Content Safety reais, clone o repositório e execute localmente com sua própria assinatura Azure.",
        "es": "<strong>Demo público</strong> — ejecutando solo en <strong>modo mock</strong>. Para invocar agentes Foundry, Azure AI Search y Content Safety reales, clona el repositorio y ejecútalo localmente con tu propia suscripción de Azure.",
    },

    # --- Menu groups ----------------------------------------------------------
    "groups.overview": {
        "en": "Overview",
        "pt": "Visão Geral",
        "es": "Visión General",
    },
    "groups.build": {
        "en": "Build",
        "pt": "Construir",
        "es": "Construir",
    },
    "groups.validate": {
        "en": "Validate",
        "pt": "Validar",
        "es": "Validar",
    },
    "groups.operate": {
        "en": "Operate & Govern",
        "pt": "Operar & Governar",
        "es": "Operar y Gobernar",
    },

    # --- Section menu titles --------------------------------------------------
    "sections.visao_geral": {
        "en": "Stack Overview & Integrated Architecture",
        "pt": "Visão Geral da Stack & Arquitetura Integrada",
        "es": "Visión General de la Stack y Arquitectura Integrada",
    },
    "sections.mapeamento": {
        "en": "Contoso Requirements × Microsoft Stack Mapping",
        "pt": "Mapeamento Requisitos Contoso × Stack Microsoft",
        "es": "Mapeo de Requisitos Contoso × Stack Microsoft",
    },
    "sections.estrutura_projetos": {
        "en": "Foundry Project Structure",
        "pt": "Estrutura de Projetos do Foundry",
        "es": "Estructura de Proyectos de Foundry",
    },
    "sections.ato1_criacao_agente": {
        "en": "Simplified Agent Creation",
        "pt": "Criação Simplificada de Agente",
        "es": "Creación Simplificada de Agente",
    },
    "sections.ato1_llm_arena": {
        "en": "LLM Arena & Model Comparison",
        "pt": "LLM Arena & Comparação de Modelos",
        "es": "LLM Arena y Comparación de Modelos",
    },
    "sections.ato1_modelagem": {
        "en": "Modeling & Fine-tuning",
        "pt": "Modelagem e Fine-tuning",
        "es": "Modelado y Fine-tuning",
    },
    "sections.ato1_prompt_versionado": {
        "en": "Prompt as Versioned Asset",
        "pt": "Prompt como Ativo Versionado",
        "es": "Prompt como Activo Versionado",
    },
    "sections.ato1_rag_chat": {
        "en": "RAG with Foundry IQ",
        "pt": "RAG com Foundry IQ",
        "es": "RAG con Foundry IQ",
    },
    "sections.ato1_hosted_agents": {
        "en": "Hosted Agents",
        "pt": "Hosted Agents",
        "es": "Hosted Agents",
    },
    "sections.ato1_multiagentes": {
        "en": "Multi-Agent with MAF & Foundry Workflows",
        "pt": "Multi-Agentes com MAF e Foundry Workflows",
        "es": "Multi-Agente con MAF y Foundry Workflows",
    },
    "sections.ato2_cicd": {
        "en": "Evaluation CI/CD with Auditable Evidence",
        "pt": "CI/CD de Avaliações com Evidência Auditável",
        "es": "CI/CD de Evaluaciones con Evidencia Auditable",
    },
    "sections.ato2_evaluators_scorecard": {
        "en": "Evaluations & Custom Evaluators",
        "pt": "Evaluations & Custom Evaluators",
        "es": "Evaluations y Custom Evaluators",
    },
    "sections.ato2_red_teaming": {
        "en": "AI Red Teaming",
        "pt": "AI Red Teaming",
        "es": "AI Red Teaming",
    },
    "sections.ato3_agent365_purview": {
        "en": "Agent 365 and Purview",
        "pt": "Agent 365 e Purview",
        "es": "Agent 365 y Purview",
    },
    "sections.ato3_classificacao_risco": {
        "en": "Risk Classification",
        "pt": "Classificação de Risco",
        "es": "Clasificación de Riesgo",
    },
    "sections.ato3_custo_integracao": {
        "en": "Integration with External Agents (A2A)",
        "pt": "Integração com Agentes Externos (A2A)",
        "es": "Integración con Agentes Externos (A2A)",
    },
    "sections.ato3_governanca": {
        "en": "Governance & Guardrails",
        "pt": "Governança & Guardrails",
        "es": "Gobernanza y Guardrails",
    },
    "sections.ato3_observabilidade": {
        "en": "Production Observability",
        "pt": "Observabilidade em Produção",
        "es": "Observabilidad en Producción",
    },

    # --- Home page ------------------------------------------------------------
    "home.title_suffix": {
        "en": "Home",
        "pt": "Início",
        "es": "Inicio",
    },
    "home.eyebrow": {
        "en": "Microsoft × Contoso Workshop",
        "pt": "Workshop Microsoft × Contoso",
        "es": "Taller Microsoft × Contoso",
    },
    "home.kpi_sections": {
        "en": "Sections",
        "pt": "Seções",
        "es": "Secciones",
    },
    "home.kpi_requirements": {
        "en": "Contoso requirements mapped",
        "pt": "Requisitos Contoso mapeados",
        "es": "Requisitos Contoso mapeados",
    },
    "home.kpi_stack": {
        "en": "Core stack",
        "pt": "Stack central",
        "es": "Stack central",
    },
    "home.narrative_eyebrow": {
        "en": "Narrative",
        "pt": "Narrativa",
        "es": "Narrativa",
    },
    "home.narrative_title": {
        "en": "An end-to-end journey through the AI agent lifecycle",
        "pt": "Uma jornada ponta a ponta de ciclo de vida de um agente de IA",
        "es": "Un recorrido punta a punta del ciclo de vida de un agente de IA",
    },
    "home.narrative_p1_html": {
        "en": "The demo walks through the same cycle Contoso must govern: <strong>create, test, evaluate, protect, publish, monitor, and govern</strong> AI agents at enterprise scale.",
        "pt": "A demo percorre o mesmo ciclo que a Contoso precisa governar: <strong>criar, testar, avaliar, proteger, publicar, monitorar e governar</strong> agentes de IA em escala corporativa.",
        "es": "La demo recorre el mismo ciclo que Contoso debe gobernar: <strong>crear, probar, evaluar, proteger, publicar, monitorear y gobernar</strong> agentes de IA a escala corporativa.",
    },
    "home.narrative_p2_html": {
        "en": "The first section is the <strong>consolidated table</strong> of requirements × stack. The rest follow three acts: <strong>Build → Validate → Operate &amp; Govern</strong>.",
        "pt": "A primeira seção é a <strong>tabela consolidada</strong> de requisitos × stack. As demais seguem em três atos: <strong>Construir → Validar → Operar e Governar</strong>.",
        "es": "La primera sección es la <strong>tabla consolidada</strong> de requisitos × stack. Las demás siguen tres actos: <strong>Construir → Validar → Operar y Gobernar</strong>.",
    },
    "home.synthesis_eyebrow": {
        "en": "Synthesis",
        "pt": "Síntese",
        "es": "Síntesis",
    },
    "home.synthesis_title": {
        "en": "How the Microsoft stack covers the Contoso AI Framework",
        "pt": "Como a stack Microsoft cobre o Framework IA Contoso",
        "es": "Cómo la stack de Microsoft cubre el Framework IA Contoso",
    },
    "home.table_pillar": {
        "en": "Contoso Pillar / Theme",
        "pt": "Pilar / Tema Contoso",
        "es": "Pilar / Tema Contoso",
    },
    "home.table_microsoft": {
        "en": "How Microsoft addresses it",
        "pt": "Como a Microsoft endereça",
        "es": "Cómo Microsoft lo aborda",
    },
    "home.row_prompt_eng": {
        "en": "Prompt Engineering",
        "pt": "Engenharia de Prompt",
        "es": "Ingeniería de Prompt",
    },
    "home.row_performance": {
        "en": "Performance / Curation",
        "pt": "Performance / Curadoria",
        "es": "Rendimiento / Curaduría",
    },
    "home.row_observability": {
        "en": "Observability",
        "pt": "Observabilidade",
        "es": "Observabilidad",
    },
    "home.row_governance": {
        "en": "AI Governance",
        "pt": "Governança de IA",
        "es": "Gobernanza de IA",
    },
    "home.row_inventory": {
        "en": "Inventory & Compliance",
        "pt": "Inventário & Compliance",
        "es": "Inventario y Cumplimiento",
    },
    "home.row_modeling": {
        "en": "Modeling",
        "pt": "Modelagem",
        "es": "Modelado",
    },
    "home.row_cost": {
        "en": "Cost & Traffic",
        "pt": "Custo & Tráfego",
        "es": "Costo y Tráfico",
    },
    "home.row_integration": {
        "en": "Integration with external agents",
        "pt": "Integração com agentes externos",
        "es": "Integración con agentes externos",
    },

    # --- Shared section-page chrome ------------------------------------------
    "section_page.pillars_label": {
        "en": "Contoso pillar(s) covered",
        "pt": "Pilar(es) Contoso atendido(s)",
        "es": "Pilar(es) Contoso cubierto(s)",
    },
    "section_page.requirements_label": {
        "en": "Requirements covered:",
        "pt": "Requisitos cobertos:",
        "es": "Requisitos cubiertos:",
    },
    "section_page.tutorial": {
        "en": "Tutorial",
        "pt": "Tutorial",
        "es": "Tutorial",
    },
    "section_page.howto_default": {
        "en": "How to use this feature",
        "pt": "Como usar esta funcionalidade",
        "es": "Cómo usar esta funcionalidad",
    },
    "section_page.key_message": {
        "en": "Key message",
        "pt": "Mensagem-chave",
        "es": "Mensaje clave",
    },
    "section_page.body_lang_notice": {
        "en": "<strong>Heads up:</strong> the in-depth content below is still in Portuguese while translation is in progress. UI navigation and section headers are localized.",
        "pt": "",
        "es": "<strong>Aviso:</strong> el contenido detallado a continuación aún está en portugués mientras se completa la traducción. La navegación y los encabezados de sección sí están localizados.",
    },

    # --- Per-section description & eyebrow -----------------------------------
    # PT falls back to the original SECTION dict via `t_section` -> None.
    # Only EN/ES are listed here.
    "sections.visao_geral.description": {
        "en": "Contoso pillars, the dev/operations cycle and components of the Microsoft stack.",
        "es": "Pilares Contoso, ciclo dev/operaciones y componentes de la pila Microsoft.",
    },
    "sections.visao_geral.eyebrow": {
        "en": "Overview · Microsoft × Contoso",
        "es": "Visión general · Microsoft × Contoso",
    },
    "sections.estrutura_projetos.description": {
        "en": "How to organize Foundry projects for dev/prod parity, traceability, granular RBAC and end-to-end auditing.",
        "es": "Cómo organizar proyectos Foundry para tener paridad dev/prod, trazabilidad, RBAC granular y auditoría completa.",
    },
    "sections.estrutura_projetos.eyebrow": {
        "en": "Overview · Microsoft × Contoso",
        "es": "Visión general · Microsoft × Contoso",
    },
    "sections.mapeamento.description": {
        "en": "The Contoso AI Framework requirements and how each Microsoft product or feature (Foundry, Agent 365, APIM, Entra, Purview) addresses them.",
        "es": "Los requisitos del Framework de IA Contoso y cómo cada producto o funcionalidad de la pila Microsoft (Foundry, Agent 365, APIM, Entra, Purview) los aborda.",
    },
    "sections.mapeamento.eyebrow": {
        "en": "Section 1 · Mapping overview",
        "es": "Sección 1 · Visión general del mapeo",
    },
    "sections.ato1_criacao_agente.description": {
        "en": "From the Foundry Playground to VS Code: build the Contoso Curator in minutes with low-code and declarative flows.",
        "es": "Del Foundry Playground a VS Code: crear el Curador Contoso en minutos con flujos low-code y declarativos.",
    },
    "sections.ato1_criacao_agente.eyebrow": {
        "en": "Build",
        "es": "Construir",
    },
    "sections.ato1_llm_arena.description": {
        "en": "Compare models side by side and choose by cost × quality × latency trade-off.",
        "es": "Comparar modelos lado a lado y elegir por el trade-off costo × calidad × latencia.",
    },
    "sections.ato1_llm_arena.eyebrow": {
        "en": "Build",
        "es": "Construir",
    },
    "sections.ato1_modelagem.description": {
        "en": "SLMs, distillation, fine-tuning, RLHF and DPO in Foundry Models — compare base and Contoso-specialized models side by side.",
        "es": "SLMs, destilación, fine-tuning, RLHF y DPO en Foundry Models — compara lado a lado el modelo base y el modelo especializado para Contoso.",
    },
    "sections.ato1_modelagem.eyebrow": {
        "en": "Build · LIVE DEMO",
        "es": "Construir · LIVE DEMO",
    },
    "sections.ato1_prompt_versionado.description": {
        "en": "Prompty + Git + CI/CD: the prompt stops being loose text and becomes an engineering artifact.",
        "es": "Prompty + Git + CI/CD: el prompt deja de ser texto suelto y se convierte en un artefacto de ingeniería.",
    },
    "sections.ato1_prompt_versionado.eyebrow": {
        "en": "Build",
        "es": "Construir",
    },
    "sections.ato1_rag_chat.description": {
        "en": "Contoso Knowledge Curator answering from internal documentation.",
        "es": "Curador de Conocimiento Contoso respondiendo con base en la documentación interna.",
    },
    "sections.ato1_rag_chat.eyebrow": {
        "en": "Build · LIVE DEMO",
        "es": "Construir · LIVE DEMO",
    },
    "sections.ato1_hosted_agents.description": {
        "en": "Publish the agent as a Foundry Hosted Agent: managed runtime, ready endpoint, Entra identity and zero infrastructure to operate.",
        "es": "Publicar el agente como Hosted Agent de Foundry: runtime gestionado, endpoint listo, identidad en Entra y cero infraestructura para operar.",
    },
    "sections.ato1_hosted_agents.eyebrow": {
        "en": "Build · LIVE DEMO",
        "es": "Construir · LIVE DEMO",
    },
    "sections.ato1_multiagentes.description": {
        "en": "Microsoft Agent Framework orchestration patterns + declarative Foundry Workflows — pick a pattern and see the topology in real time.",
        "es": "Patrones de orquestación del Microsoft Agent Framework + Foundry Workflows declarativos — elige el patrón y ve la topología en tiempo real.",
    },
    "sections.ato1_multiagentes.eyebrow": {
        "en": "Build · LIVE DEMO",
        "es": "Construir · LIVE DEMO",
    },
    "sections.ato2_cicd.description": {
        "en": "GitHub Actions + Foundry Evaluations + scorecard as the promote gate.",
        "es": "GitHub Actions + Foundry Evaluations + scorecard como gate de promoción.",
    },
    "sections.ato2_cicd.eyebrow": {
        "en": "Validate",
        "es": "Validar",
    },
    "sections.ato2_evaluators_scorecard.description": {
        "en": "Foundry built-in evaluators (Quality, Safety, Agent) plus how to build and run Custom Evaluators.",
        "es": "Evaluadores built-in de Foundry (Quality, Safety, Agent) + cómo construir y ejecutar Custom Evaluators.",
    },
    "sections.ato2_evaluators_scorecard.eyebrow": {
        "en": "Validate · LIVE DEMO",
        "es": "Validar · LIVE DEMO",
    },
    "sections.ato2_red_teaming.description": {
        "en": "Automated red teaming via PyRIT + Foundry: attacks the agent across multiple categories and strategies and produces an auditable scorecard.",
        "es": "Red teaming automatizado vía PyRIT + Foundry: ataca al agente en múltiples categorías y estrategias y genera un scorecard auditable.",
    },
    "sections.ato2_red_teaming.eyebrow": {
        "en": "Validate · LIVE DEMO",
        "es": "Validar · LIVE DEMO",
    },
    "sections.ato3_agent365_purview.description": {
        "en": "Corporate inventory of agents + DLP, classification and auditing via Purview — and how to surface your agent in Agent 365.",
        "es": "Inventario corporativo de agentes + DLP, clasificación y auditoría vía Purview — y cómo exponer tu agente en Agent 365.",
    },
    "sections.ato3_agent365_purview.eyebrow": {
        "en": "Operate & Govern",
        "es": "Operar y Gobernar",
    },
    "sections.ato3_classificacao_risco.description": {
        "en": "Parametrizable criteria, alignment with PL 2338 and Custom Azure Policy for Foundry for automated risk enforcement.",
        "es": "Criterios parametrizables, alineación al PL 2338 y Custom Azure Policy for Foundry para enforcement automatizado de riesgo.",
    },
    "sections.ato3_classificacao_risco.eyebrow": {
        "en": "Operate & Govern · DEMO",
        "es": "Operar y Gobernar · DEMO",
    },
    "sections.ato3_custo_integracao.description": {
        "en": "APIM AI Gateway, semantic caching and real A2A orchestration via Microsoft Agent Framework — local agents + Foundry Hosted Agents.",
        "es": "APIM AI Gateway, semantic caching y orquestación A2A real vía Microsoft Agent Framework — agentes locales + Foundry Hosted Agents.",
    },
    "sections.ato3_custo_integracao.eyebrow": {
        "en": "Operate & Govern · LIVE DEMO",
        "es": "Operar y Gobernar · LIVE DEMO",
    },
    "sections.ato3_governanca.description": {
        "en": "Foundry Control Plane + Guardrails (Content Safety, Prompt Shields, Groundedness).",
        "es": "Foundry Control Plane + Guardrails (Content Safety, Prompt Shields, Groundedness).",
    },
    "sections.ato3_governanca.eyebrow": {
        "en": "Operate & Govern · LIVE DEMO",
        "es": "Operar y Gobernar · LIVE DEMO",
    },
    "sections.ato3_observabilidade.description": {
        "en": "Custom dashboard of Foundry agent/model metrics, collected via APIM AI Gateway → Log Analytics.",
        "es": "Dashboard personalizado de métricas de agentes/modelos del Foundry, recolectadas vía APIM AI Gateway → Log Analytics.",
    },
    "sections.ato3_observabilidade.eyebrow": {
        "en": "Operate & Govern · LIVE DEMO",
        "es": "Operar y Gobernar · LIVE DEMO",
    },

    # --- Industry packs (top-level metadata only; deep mock data stays as-is) -
    # PT falls back to the JSON pack value when no entry is present.
    "industries.cpg.label": {
        "en": "Consumer Goods (CPG)",
        "es": "Bienes de Consumo (CPG)",
    },
    "industries.cpg.app_title": {
        "en": "Contoso Goods AI Framework",
        "es": "Framework de IA Contoso Goods",
    },
    "industries.cpg.app_tagline": {
        "en": "The 24 requirements of the Contoso Goods AI Framework and how each one is addressed by the Microsoft stack.",
        "es": "Los 24 requisitos del Framework de IA Contoso Goods y cómo cada uno es abordado por la pila Microsoft.",
    },
    "industries.energy.label": {
        "en": "Energy & Utilities",
        "es": "Energía y Utilities",
    },
    "industries.energy.app_title": {
        "en": "Contoso Energy AI Framework",
        "es": "Framework de IA Contoso Energy",
    },
    "industries.energy.app_tagline": {
        "en": "The 24 requirements of the Contoso Energy AI Framework and how each one is addressed by the Microsoft stack.",
        "es": "Los 24 requisitos del Framework de IA Contoso Energy y cómo cada uno es abordado por la pila Microsoft.",
    },
    "industries.financial.label": {
        "en": "Financial Services",
        "es": "Servicios Financieros",
    },
    "industries.financial.app_title": {
        "en": "Contoso Financial AI Framework",
        "es": "Framework de IA Contoso Financial",
    },
    "industries.financial.app_tagline": {
        "en": "The 24 requirements of the Contoso Financial AI Framework and how each one is addressed by the Microsoft stack.",
        "es": "Los 24 requisitos del Framework de IA Contoso Financial y cómo cada uno es abordado por la pila Microsoft.",
    },
    "industries.manufacturing.label": {
        "en": "Manufacturing",
        "es": "Manufactura",
    },
    "industries.manufacturing.app_title": {
        "en": "Contoso Industries AI Framework",
        "es": "Framework de IA Contoso Industries",
    },
    "industries.manufacturing.app_tagline": {
        "en": "The 24 requirements of the Contoso Industries AI Framework and how each one is addressed by the Microsoft stack.",
        "es": "Los 24 requisitos del Framework de IA Contoso Industries y cómo cada uno es abordado por la pila Microsoft.",
    },
    "industries.telecom.label": {
        "en": "Telecommunications",
        "es": "Telecomunicaciones",
    },
    "industries.telecom.app_title": {
        "en": "Contoso AI Framework",
        "es": "Framework de IA Contoso",
    },
    "industries.telecom.app_tagline": {
        "en": "The 24 requirements of the Contoso AI Framework and how each one is addressed by the Microsoft stack.",
        "es": "Los 24 requisitos del Framework de IA Contoso y cómo cada uno es abordado por la pila Microsoft.",
    },

    # --- Pillar labels (keyed by the original Portuguese string) ----------
    "label.pillar.Engenharia de Prompt": {
        "en": "Prompt Engineering",
        "es": "Ingeniería de Prompt",
    },
    "label.pillar.Performance": {
        "en": "Performance",
        "es": "Rendimiento",
    },
    "label.pillar.Performance / Curadoria": {
        "en": "Performance / Curation",
        "es": "Rendimiento / Curaduría",
    },
    "label.pillar.Governança": {
        "en": "Governance",
        "es": "Gobernanza",
    },
    "label.pillar.Governança de IA": {
        "en": "AI Governance",
        "es": "Gobernanza de IA",
    },
    "label.pillar.Modelagem": {
        "en": "Modeling",
        "es": "Modelado",
    },
    "label.pillar.Transversal": {
        "en": "Cross-cutting",
        "es": "Transversal",
    },
    "label.pillar.Transversal (Custo / Integração)": {
        "en": "Cross-cutting (Cost / Integration)",
        "es": "Transversal (Costo / Integración)",
    },
    "label.pillar.Operação": {
        "en": "Operations",
        "es": "Operación",
    },

    # --- Requirement titles (keyed by the original Portuguese string) -----
    "label.requisito.Fluxo de criação simplificado": {
        "en": "Simplified creation flow",
        "es": "Flujo de creación simplificado",
    },
    "label.requisito.Versionamento de prompt": {
        "en": "Prompt versioning",
        "es": "Versionado de prompts",
    },
    "label.requisito.LLM Arena": {
        "en": "LLM Arena",
        "es": "LLM Arena",
    },
    "label.requisito.Otimização de prompt (autoprompt + compressão)": {
        "en": "Prompt optimization (autoprompt + compression)",
        "es": "Optimización de prompts (autoprompt + compresión)",
    },
    "label.requisito.Ambiente de teste com paridade de produção": {
        "en": "Test environment with production parity",
        "es": "Entorno de prueba con paridad de producción",
    },
    "label.requisito.Criação e testes de multiagentes": {
        "en": "Multi-agent creation and testing",
        "es": "Creación y pruebas de multiagentes",
    },
    "label.requisito.Métricas RAG": {
        "en": "RAG metrics",
        "es": "Métricas RAG",
    },
    "label.requisito.Métricas RAG (qualidade da pergunta, assertividade, qualidade do documento)": {
        "en": "RAG metrics (question quality, assertiveness, document quality)",
        "es": "Métricas RAG (calidad de la pregunta, asertividad, calidad del documento)",
    },
    "label.requisito.Persona Sintética / Prompt Injection": {
        "en": "Synthetic Persona / Prompt Injection",
        "es": "Persona Sintética / Inyección de Prompt",
    },
    "label.requisito.Framework Avaliativo de Agentes": {
        "en": "Agent Evaluation Framework",
        "es": "Framework Evaluativo de Agentes",
    },
    "label.requisito.Framework Avaliativo de Agentes (Knowledge / Reasoning / Conversational)": {
        "en": "Agent Evaluation Framework (Knowledge / Reasoning / Conversational)",
        "es": "Framework Evaluativo de Agentes (Knowledge / Reasoning / Conversational)",
    },
    "label.requisito.Monitoramento por produto": {
        "en": "Per-product monitoring",
        "es": "Monitoreo por producto",
    },
    "label.requisito.Métricas multidimensionais customizadas": {
        "en": "Custom multidimensional metrics",
        "es": "Métricas multidimensionales personalizadas",
    },
    "label.requisito.Estudos pontuais (ad hoc)": {
        "en": "Ad hoc studies",
        "es": "Estudios puntuales (ad hoc)",
    },
    "label.requisito.Observabilidade": {
        "en": "Observability",
        "es": "Observabilidad",
    },
    "label.requisito.Observabilidade (drift, anomalias, dashboards)": {
        "en": "Observability (drift, anomalies, dashboards)",
        "es": "Observabilidad (drift, anomalías, dashboards)",
    },
    "label.requisito.Scorecards Modulares + Índice Único de Maturidade": {
        "en": "Modular Scorecards + Unified Maturity Index",
        "es": "Scorecards Modulares + Índice Único de Madurez",
    },
    "label.requisito.Inventário e rastreabilidade": {
        "en": "Inventory and traceability",
        "es": "Inventario y trazabilidad",
    },
    "label.requisito.Classificação de risco": {
        "en": "Risk classification",
        "es": "Clasificación de riesgo",
    },
    "label.requisito.Guardrail padrão (corporativo)": {
        "en": "Default (corporate) guardrail",
        "es": "Guardrail por defecto (corporativo)",
    },
    "label.requisito.Guardrail por sistema (configurável)": {
        "en": "Per-system guardrail (configurable)",
        "es": "Guardrail por sistema (configurable)",
    },
    "label.requisito.RBAC, auditoria e segregação de ambientes": {
        "en": "RBAC, audit and environment segregation",
        "es": "RBAC, auditoría y segregación de ambientes",
    },
    "label.requisito.Workflow de aprovação por nível de risco": {
        "en": "Approval workflow by risk level",
        "es": "Workflow de aprobación por nivel de riesgo",
    },
    "label.requisito.Testes com evidência (acurácia, vieses, privacidade)": {
        "en": "Evidence-based testing (accuracy, biases, privacy)",
        "es": "Pruebas con evidencia (precisión, sesgos, privacidad)",
    },
    "label.requisito.Transparência e explicabilidade": {
        "en": "Transparency and explainability",
        "es": "Transparencia y explicabilidad",
    },
    "label.requisito.Visão por requisito do PL/norma interna": {
        "en": "Per-requirement view of the bill / internal policy",
        "es": "Vista por requisito del PL / norma interna",
    },
    "label.requisito.Documentação de ciclo de vida + Dashboard de governança": {
        "en": "Lifecycle documentation + Governance dashboard",
        "es": "Documentación de ciclo de vida + Dashboard de gobernanza",
    },
    "label.requisito.Modelagem (catalog, fine-tune, DPO)": {
        "en": "Modeling (catalog, fine-tune, DPO)",
        "es": "Modelado (catálogo, fine-tune, DPO)",
    },
    "label.requisito.Modelagem (Leaderboard, SLMs, Destilação, Fine-tune, RLHF, DPO)": {
        "en": "Modeling (Leaderboard, SLMs, Distillation, Fine-tune, RLHF, DPO)",
        "es": "Modelado (Leaderboard, SLMs, Destilación, Fine-tune, RLHF, DPO)",
    },
    "label.requisito.Custo / consumo de tokens": {
        "en": "Cost / token consumption",
        "es": "Costo / consumo de tokens",
    },
    "label.requisito.Integração com agentes externos": {
        "en": "Integration with external agents",
        "es": "Integración con agentes externos",
    },
    "label.requisito.Integração com agentes externos (IBM, Salesforce, ServiceNow, Copilot)": {
        "en": "Integration with external agents (IBM, Salesforce, ServiceNow, Copilot)",
        "es": "Integración con agentes externos (IBM, Salesforce, ServiceNow, Copilot)",
    },

    # --- Status labels ----------------------------------------------------
    "label.status.Completo": {
        "en": "Complete",
        "es": "Completo",
    },
    "label.status.Parcial": {
        "en": "Partial",
        "es": "Parcial",
    },
    "label.status.Requer integração": {
        "en": "Requires integration",
        "es": "Requiere integración",
    },
}


# --- Public API -------------------------------------------------------------


def default_lang() -> str:
    val = (os.getenv(ENV_VAR) or DEFAULT_LANG).strip().lower()
    return val if val in _VALID else DEFAULT_LANG


def get_lang(request: Request) -> str:
    raw = (request.cookies.get(COOKIE_NAME) or "").strip().lower()
    if raw in _VALID:
        return raw
    return default_lang()


def set_lang_cookie(response: Response, code: str) -> str:
    norm = (code or "").strip().lower()
    if norm not in _VALID:
        raise ValueError(f"unknown language: {code}")
    response.set_cookie(
        COOKIE_NAME,
        norm,
        max_age=COOKIE_MAX_AGE,
        path="/",
        samesite="lax",
        httponly=False,
    )
    return norm


def list_languages() -> List[Dict[str, str]]:
    return list(LANGUAGES)


def _workshop_lookup(key: str, lang: str) -> str | None:
    """Look up a dotted key in the file-based content/<lang>/workshop.yaml.

    Imported lazily to avoid a hard dependency at module import time
    (lets ``i18n`` keep working in tooling contexts where pyyaml is absent).
    Returns ``None`` when the key is missing or the loader fails to import.
    """
    try:
        from content_loader import workshop_t  # local import — optional
    except Exception:
        return None
    try:
        return workshop_t(lang, key)
    except Exception:
        return None


def t(key: str, lang: str = DEFAULT_LANG) -> str:
    """Return translation for `key` in `lang`, falling back to English then the key itself.

    File-based ``content/<lang>/workshop.yaml`` takes precedence over the
    legacy in-code ``TRANSLATIONS`` dict so editorial copy can be edited
    without touching Python.
    """
    val = _workshop_lookup(key, lang)
    if val is not None:
        return val
    entry = TRANSLATIONS.get(key)
    if not entry:
        return key
    return entry.get(lang) or entry.get(DEFAULT_LANG) or key


def t_optional(key: str, lang: str) -> str | None:
    """Return translation for `key` in `lang`, or None when there is no entry for that language.

    File-based workshop.yaml is consulted first; legacy TRANSLATIONS dict
    is the fallback. Never falls back to another language or the key itself.
    """
    val = _workshop_lookup(key, lang)
    if val is not None:
        return val
    entry = TRANSLATIONS.get(key)
    if not entry:
        return None
    val = entry.get(lang)
    return val if val else None


def make_translator(lang: str):
    """Build a `t(key)` callable bound to a specific language. Jinja-friendly."""
    def _t(key: str) -> str:
        return t(key, lang)
    return _t


def make_section_translator(lang: str, slug: str | None):
    """Build a callable `t_section(key, fallback='')` for the section identified by `slug`.

    Looks up `sections.<slug>.<key>` in the translation dict. Returns the fallback (which is
    typically the original Portuguese SECTION dict value) when no translation exists for `lang`
    or when `slug` is None. Templates use:

        {{ request.state.t_section('description', section.description) }}
    """
    def _t_section(key: str, fallback: str = "") -> str:
        if not slug:
            return fallback
        translated = t_optional(f"sections.{slug}.{key}", lang)
        if translated is None and key == "title":
            # Fall back to the menu title key, which is already translated for the sidebar.
            translated = t_optional(f"sections.{slug}", lang)
        return translated if translated is not None else fallback
    return _t_section


def make_label_translator(lang: str):
    """Build a callable `t_label(namespace, pt_text)` that translates short PT labels.

    Looks up `label.<namespace>.<pt_text>` in the translation dict. Returns `pt_text`
    unchanged when there is no entry for `lang`. Designed for short structural labels
    (pillars, requirement titles, status tags, etc.) where the original Portuguese
    string is the natural fallback. Templates use:

        {{ request.state.t_label('pillar', p) }}
    """
    def _t_label(namespace: str, pt_text: str) -> str:
        if not pt_text:
            return pt_text
        translated = t_optional(f"label.{namespace}.{pt_text}", lang)
        return translated if translated is not None else pt_text
    return _t_label


__all__ = [
    "COOKIE_NAME",
    "DEFAULT_LANG",
    "LANGUAGES",
    "default_lang",
    "get_lang",
    "set_lang_cookie",
    "list_languages",
    "t",
    "t_optional",
    "make_translator",
    "make_section_translator",
    "make_label_translator",
]
