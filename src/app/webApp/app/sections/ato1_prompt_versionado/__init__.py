"""Prompt como Ativo Versionado — content + interactive prompt optimization demo (Foundry + LLMLingua-style)."""

import re
import asyncio
import difflib
import html as _html_esc
import random
from pathlib import Path
from typing import List, Literal, Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

MENU_TITLE = "Prompt como Ativo Versionado"
MENU_ICON = "fa-solid fa-code-branch"

_HERE = Path(__file__).parent
_GLOBAL_TEMPLATES = Path(__file__).resolve().parents[2] / "templates"
_templates = Jinja2Templates(directory=[str(_HERE / "templates"), str(_GLOBAL_TEMPLATES)])

SECTION = {
    "title": MENU_TITLE,
    "description": "Prompty + Git + CI/CD: prompt deixa de ser texto solto e vira artefato de engenharia.",
    "eyebrow": "Construir",
    "eyebrow_icon": "fa-solid fa-screwdriver-wrench",
}

# --- Code samples (Prism.js highlighting) -----------------------------------
PROMPTY_SAMPLE = '''---
name: contoso-knowledge-curator
description: Curador de base de conhecimento para atendimento Contoso
authors: [equipe-ia-contoso]
model:
  api: chat
  configuration:
    type: azure_openai
    azure_deployment: gpt-4o
  parameters:
    temperature: 0.2          # << baixo p/ respostas factuais
    max_tokens: 800
    response_format: { type: "json_object" }
sample:
  pergunta: "Qual o procedimento para portabilidade?"
  contexto: "..."
---
system:
Você é o curador de conhecimento Contoso. Responda APENAS com base
no {{contexto}} fornecido. Se não houver evidência, diga
"não encontrei na base" — nunca invente.

user:
Pergunta: {{pergunta}}
Contexto:
{{contexto}}'''

CI_SAMPLE = '''name: prompt-quality-gate
on:
  pull_request:
    paths: ["prompts/**/*.prompty"]    # << dispara só em mudanças de prompt

jobs:
  evaluate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: azure/login@v2
        with:
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}

      - name: Run Foundry evaluators
        run: |
          az foundry evaluation run \\
            --prompt prompts/contoso-knowledge-curator.prompty \\
            --dataset eval/regression-set.jsonl \\
            --evaluators groundedness relevance fluency \\
            --threshold 0.85         # << bloqueia merge se cair abaixo'''

PYTHON_SAMPLE = '''from prompty import load, execute

# 1. Carrega o prompt versionado (do Git)
prompt = load("prompts/contoso-knowledge-curator.prompty")

# 2. Executa com inputs dinâmicos — params do front-matter são aplicados
resposta = execute(
    prompt,
    inputs={
        "pergunta": "Como faço portabilidade?",
        "contexto": rag_chunks,    # << vem do Foundry IQ
    },
)

# 3. resposta é JSON estruturado por causa de response_format no .prompty
print(resposta["citacoes"], resposta["resposta"])'''


def _code_block(lang: str, code: str, caption: str = "") -> str:
    import html as _html
    safe = _html.escape(code)
    cap = f'<div class="code-caption">{caption}</div>' if caption else ""
    return (
        f'{cap}<pre class="code-block"><code class="language-{lang}">{safe}</code></pre>'
    )


BLOCK_CONCEITO = (
    "<p>Prompts são <strong>tão críticos quanto código</strong>: uma vírgula a mais na "
    "instrução pode degradar 20% da qualidade. A stack Microsoft trata prompt como "
    "artefato versionado via <strong>Prompty</strong> (formato aberto <code>.prompty</code>), "
    "integrado a <strong>Git</strong>, <strong>VS Code</strong>, "
    "<strong>GitHub Actions</strong> e ao <strong>Foundry Project</strong>.</p>"
    "<ul>"
    "<li><code>.prompty</code> = <strong>front-matter</strong> (modelo, params) + corpo "
    "(system/user/assistant) — totalmente diff-friendly.</li>"
    "<li>Templates corporativos publicados no Foundry Project podem ser reusados pelas BUs.</li>"
    "<li>Cada PR roda <em>evaluators</em> automaticamente antes do merge.</li>"
    "<li>Rollback é <code>git revert</code> + redeploy automático.</li>"
    "</ul>"
)

BLOCK_PROMPTY = (
    "<p>O arquivo <code>.prompty</code> é a <strong>fonte única de verdade</strong> para um "
    "prompt: contém modelo, hyperparâmetros e o template do prompt em si. "
    "Pontos críticos destacados:</p>"
    + _code_block("yaml", PROMPTY_SAMPLE, "contoso-knowledge-curator.prompty")
    + "<ul>"
    "<li><strong>temperature: 0.2</strong> — para curadoria factual; nunca deixe default em "
    "RAG corporativo (default = 1.0 alucina).</li>"
    "<li><strong>response_format: json_object</strong> — força saída estruturada; o app "
    "consumidor não precisa parsear texto livre.</li>"
    "<li>O bloco <code>sample:</code> serve para o VS Code rodar inline (F5) sem precisar "
    "de pipeline — feedback loop em segundos.</li>"
    "<li>A regra <em>“nunca invente”</em> no system é o anti-alucinação básico — combinado "
    "com groundedness evaluator no CI.</li>"
    "</ul>"
)

BLOCK_PYTHON = (
    "<p>O consumo no código de aplicação é trivial — não há string concatenation, não há "
    "prompt injection acidental:</p>"
    + _code_block("python", PYTHON_SAMPLE, "app/curator.py")
    + "<p>Note que o <strong>versionamento do prompt está no Git</strong>, não no código. "
    "Trocar o modelo de gpt-4o para gpt-4o-mini é uma linha no <code>.prompty</code> + "
    "PR — sem deploy de aplicação.</p>"
)

BLOCK_CI = (
    "<p>O <strong>quality gate</strong> de prompts roda exatamente como teste de código. "
    "Exemplo de workflow no GitHub Actions:</p>"
    + _code_block("yaml", CI_SAMPLE, ".github/workflows/prompt-quality-gate.yml")
    + "<ul>"
    "<li><strong>paths filter</strong> evita rodar evaluators caros em PRs que não tocam prompts.</li>"
    "<li><strong>threshold 0.85</strong> é a métrica que bloqueia merge — auditável, mensurável.</li>"
    "<li>O dataset de regressão (<code>eval/regression-set.jsonl</code>) também é "
    "versionado no Git — todo dado de teste rastreável.</li>"
    "</ul>"
)


# ---- V1 vs V2 do mesmo .prompty (req 1.1.2 — versionamento) ---------------
PROMPTY_V1 = """---
name: contoso-knowledge-curator
description: Curador de base de conhecimento Contoso
authors: [equipe-ia-contoso]
model:
  api: chat
  configuration:
    type: azure_openai
    azure_deployment: gpt-4o
  parameters:
    temperature: 0.7
    max_tokens: 500
---
system:
Voce e um assistente da Contoso. Responda as perguntas do usuario
da melhor forma possivel usando o contexto.

user:
{{pergunta}}

Contexto: {{contexto}}
"""

PROMPTY_V2 = """---
name: contoso-knowledge-curator
description: Curador de base de conhecimento para atendimento Contoso
authors: [equipe-ia-contoso]
tags: [rag, atendimento, regulatorio]
model:
  api: chat
  configuration:
    type: azure_openai
    azure_deployment: gpt-4o
  parameters:
    temperature: 0.2
    max_tokens: 800
    response_format: { type: "json_object" }
sample:
  pergunta: "Qual o procedimento para portabilidade?"
  contexto: "POL-VEN-007 ..."
---
system:
Você é o curador de conhecimento Contoso. Responda APENAS com base
no {{contexto}} fornecido. Se não houver evidência, diga
"não encontrei na base" — nunca invente. Cite código da política
quando disponível (formato POL-XXX-NNN).

user:
Pergunta: {{pergunta}}
Contexto:
{{contexto}}
"""


def _render_unified_diff_html(old: str, new: str, old_label: str, new_label: str) -> str:
    """Renderiza um unified diff em HTML colorido (verde/vermelho)."""
    diff = difflib.unified_diff(
        old.splitlines(keepends=False),
        new.splitlines(keepends=False),
        fromfile=old_label, tofile=new_label, lineterm="", n=3,
    )
    lines_html: List[str] = []
    for line in diff:
        escaped = _html_esc.escape(line)
        if line.startswith("+++") or line.startswith("---"):
            cls = "diff-meta"
        elif line.startswith("@@"):
            cls = "diff-hunk"
        elif line.startswith("+"):
            cls = "diff-add"
        elif line.startswith("-"):
            cls = "diff-del"
        else:
            cls = "diff-ctx"
        lines_html.append(f'<span class="{cls}">{escaped}</span>')
    body = "\n".join(lines_html)
    return (
        '<div class="prompty-diff">'
        f'<div class="prompty-diff__head"><span class="diff-v1">{old_label}</span>'
        f'<span class="diff-arrow">→</span><span class="diff-v2">{new_label}</span></div>'
        f'<pre class="prompty-diff__body"><code>{body}</code></pre>'
        '</div>'
    )


_PROMPTY_DIFF_HTML = _render_unified_diff_html(
    PROMPTY_V1, PROMPTY_V2,
    "contoso-knowledge-curator.prompty @ v1.0.0",
    "contoso-knowledge-curator.prompty @ v2.0.0",
)

BLOCK_VERSIONAMENTO_DIFF = (
    "<p>O <code>.prompty</code> é texto puro — então o <strong>diff entre versões</strong> "
    "é tão legível quanto um diff de código. Abaixo: o mesmo prompt antes e depois de "
    "uma iteração baseada em feedback de evaluators (groundedness subiu de 0.68 → 0.94).</p>"
    "<div class=\"prompty-diff-grid\">"
    "<div class=\"prompty-diff-col\">"
    "<header class=\"prompty-diff-col__head\"><i class=\"fa-solid fa-tag\"></i> v1.0.0 <span class=\"muted\">(baseline)</span></header>"
    + _code_block("yaml", PROMPTY_V1, "")
    + "</div>"
    "<div class=\"prompty-diff-col\">"
    "<header class=\"prompty-diff-col__head prompty-diff-col__head--new\"><i class=\"fa-solid fa-tag\"></i> v2.0.0 <span class=\"muted\">(promovido)</span></header>"
    + _code_block("yaml", PROMPTY_V2, "")
    + "</div>"
    "</div>"
    "<h4 style=\"margin:18px 0 6px 0;\">Diff unified — exatamente o que aparece no PR</h4>"
    + _PROMPTY_DIFF_HTML
    + "<ul>"
    "<li><strong>temperature 0.7 → 0.2</strong>: corrige alucinação detectada pelos evaluators.</li>"
    "<li><strong>response_format json_object</strong>: força saída estruturada — quebra zero no consumidor.</li>"
    "<li><strong>tags + sample</strong>: descobribilidade no Foundry Project + smoke-test local (F5 no VS Code).</li>"
    "<li><strong>System reforçado</strong>: regra anti-alucinação + obrigatoriedade de citar POL-XXX-NNN.</li>"
    "</ul>"
    "<style>"
    ".prompty-diff-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin: 12px 0; }"
    "@media (max-width: 900px) { .prompty-diff-grid { grid-template-columns: 1fr; } }"
    ".prompty-diff-col__head { font-family: 'JetBrains Mono', monospace; font-size: 12px; padding: 6px 10px; background: var(--background-light); border: 1px solid var(--border-color); border-bottom: none; border-radius: 6px 6px 0 0; color: var(--text-secondary); }"
    ".prompty-diff-col__head--new { border-color: var(--accent-color); color: var(--accent-color); }"
    ".prompty-diff-col .code-block { margin: 0; border-radius: 0 0 6px 6px; }"
    ".prompty-diff { margin-top: 8px; }"
    ".prompty-diff__head { display: flex; gap: 8px; align-items: center; font-family: 'JetBrains Mono', monospace; font-size: 12px; padding: 8px 12px; background: var(--background-light); border: 1px solid var(--border-color); border-bottom: none; border-radius: 6px 6px 0 0; }"
    ".prompty-diff__head .diff-v1 { color: #ff8b8b; }"
    ".prompty-diff__head .diff-v2 { color: #4ade80; }"
    ".prompty-diff__head .diff-arrow { color: var(--text-muted); }"
    ".prompty-diff__body { margin: 0; padding: 12px; background: var(--background-dark); border: 1px solid var(--border-color); border-radius: 0 0 6px 6px; overflow-x: auto; font-size: 12.5px; line-height: 1.55; }"
    ".prompty-diff__body code { display: block; font-family: 'JetBrains Mono', monospace; white-space: pre; }"
    ".prompty-diff__body .diff-meta { display: block; color: var(--text-muted); }"
    ".prompty-diff__body .diff-hunk { display: block; color: #8aa1ff; }"
    ".prompty-diff__body .diff-add  { display: block; color: #4ade80; background: rgba(74,222,128,.08); }"
    ".prompty-diff__body .diff-del  { display: block; color: #ff8b8b; background: rgba(255,107,107,.08); }"
    ".prompty-diff__body .diff-ctx  { display: block; color: var(--text-secondary); }"
    "</style>"
)



BODY = {
    "pillars": ["Engenharia de Prompt"],
    "requisitos": [
        {"id": "1.1.2", "titulo": "Engenharia + versionamento de prompts"},
        {"id": "1.1.3", "titulo": "Reutilização de templates aprovados"},
        {"id": "1.1.4", "titulo": "Múltiplas versões + rollback"},
    ],
    "blocks": [
        {"titulo": "Conceito", "html": BLOCK_CONCEITO},
        {"titulo": "Anatomia de um arquivo .prompty", "html": BLOCK_PROMPTY},
        {"titulo": "Versionamento na prática — diff v1 → v2", "html": BLOCK_VERSIONAMENTO_DIFF},
        {"titulo": "Consumo em aplicação Python", "html": BLOCK_PYTHON},
        {"titulo": "Quality gate no CI/CD", "html": BLOCK_CI},
    ],
    "tutorial_titulo": "Versionar e revisar um prompt em produção",
    "tutorial_passos": [
        {
            "titulo": "Editar o .prompty no VS Code",
            "html": "Abrir <code>contoso-knowledge-curator.prompty</code>, ajustar a instrução, "
                    "rodar inline (F5) usando o bloco <code>sample:</code>. Iteração em segundos.",
        },
        {
            "titulo": "Abrir PR no GitHub",
            "html": "Push gera PR; o workflow <em>prompt-quality-gate</em> dispara, executa "
                    "evaluators contra o dataset de regressão e posta o scorecard como "
                    "comentário no PR. Merge bloqueado se score cair.",
        },
        {
            "titulo": "Comparar versões A/B no Foundry",
            "html": "Em <em>Foundry → Prompts → Compare</em>, executar prompt antigo vs novo "
                    "no mesmo input set. Tabela lado-a-lado mostra deltas de qualidade, "
                    "tokens e latência — base auditável para decisão de promote.",
        },
        {
            "titulo": "Rollback se necessário",
            "html": "Problema em produção? <code>git revert &lt;sha&gt;</code> + push. "
                    "O CD pega a versão anterior do <code>.prompty</code> e republica. "
                    "Sem hotfix manual, sem caminho fora do Git.",
        },
    ],
    "mensagem_chave": (
        "Prompt = código. <strong>Versionamento, revisão automatizada e rollback</strong> "
        "deixam de ser opcionais e passam a ser a forma natural de trabalhar."
    ),
}


# ============================================================================
#  Router (uses custom template that extends _section_page.html)
# ============================================================================
router = APIRouter(prefix="/sections/ato1_prompt_versionado", tags=["ato1_prompt_versionado"])


@router.get("", response_class=HTMLResponse)
async def index(request: Request):
    return _templates.TemplateResponse(
        "index.html",
        {"request": request, "section": SECTION, "section_body": BODY},
    )


# ============================================================================
#  Prompt Optimization API — Foundry built-in + LLMLingua-style
# ============================================================================
# LLMLingua-style heuristics implemented in pure Python (mock/local). Real
# integration would call:  from llmlingua import PromptCompressor
# and Foundry would use the prompt-optimizer endpoint.

_STOPWORDS_PT = {
    "a", "o", "as", "os", "um", "uma", "uns", "umas", "de", "do", "da", "dos", "das",
    "no", "na", "nos", "nas", "em", "para", "por", "com", "sem", "se", "que", "qual",
    "como", "quando", "onde", "porque", "muito", "muita", "mais", "menos", "também",
    "ainda", "já", "ou", "e", "mas", "porém", "então", "assim", "isso", "esse", "essa",
    "este", "esta", "isto", "aquele", "aquela", "aquilo", "ser", "estar", "ter", "haver",
    "favor", "por favor", "gostaria", "poderia", "talvez",
}
_STOPWORDS_EN = {
    "a", "an", "the", "of", "to", "in", "on", "at", "for", "with", "and", "or", "but",
    "is", "are", "was", "were", "be", "been", "being", "do", "does", "did", "have",
    "has", "had", "will", "would", "could", "should", "may", "might", "can",
    "please", "kindly", "really", "very", "just", "actually", "basically",
}
_STOPWORDS = _STOPWORDS_PT | _STOPWORDS_EN

# Filler / verbose phrases → concise replacements
_FILLER_REPLACEMENTS = [
    (r"\bpor\s+favor\b", ""),
    (r"\bvocê\s+poderia\b", ""),
    (r"\bgostaria\s+que\s+você\b", ""),
    (r"\bse\s+possível\b", ""),
    (r"\bmuito\s+importante\s+que\b", ""),
    (r"\bé\s+fundamental\s+que\b", ""),
    (r"\bobservação\s*:\s*", ""),
    (r"\b(very|really|just|actually|basically)\b", ""),
    (r"\b(please|kindly)\b", ""),
    (r"\bI would like you to\b", ""),
    (r"\bcould you please\b", ""),
    (r"\s{2,}", " "),
]


class OptimizeRequest(BaseModel):
    prompt: str
    technique: Literal[
        "llmlingua_compress",
        "llmlingua_question_aware",
        "llmlingua_coarse_to_fine",
        "foundry_optimize",
        "foundry_clarity",
    ]
    question: Optional[str] = None  # for question_aware
    target_ratio: float = 0.5       # 0..1 (lower = more aggressive)


class OptimizeResponse(BaseModel):
    technique: str
    original_prompt: str
    optimized_prompt: str
    original_tokens: int
    optimized_tokens: int
    compression_ratio: float
    saved_tokens: int
    cost_saved_usd: float
    notes: List[str]


def _approx_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars/token for mixed PT-BR/EN."""
    return max(1, len(text) // 4)


def _split_keep_punct(text: str) -> List[str]:
    return re.findall(r"\S+", text)


def _llmlingua_compress(prompt: str, ratio: float) -> tuple[str, List[str]]:
    """Coarse compression: drop stopwords + filler + redundant whitespace, keep important spans."""
    notes = ["Removidos stopwords e filler phrases (pt-BR / en)."]
    text = prompt
    for pat, repl in _FILLER_REPLACEMENTS:
        text = re.sub(pat, repl, text, flags=re.IGNORECASE)
    tokens = _split_keep_punct(text)
    keep_n = max(1, int(len(tokens) * (1 - (1 - ratio) * 0.6)))
    # token-importance heuristic: keep upper-case, numbers, longer tokens; drop stopwords
    scored = []
    for i, t in enumerate(tokens):
        bare = re.sub(r"[^\wÀ-ÿ]", "", t).lower()
        if not bare:
            scored.append((i, 0.0, t))
            continue
        score = 1.0
        if bare in _STOPWORDS:
            score = 0.05
        if bare.isdigit():
            score += 0.5
        if t[:1].isupper():
            score += 0.3
        if len(bare) > 7:
            score += 0.3
        scored.append((i, score, t))
    scored_sorted = sorted(scored, key=lambda x: -x[1])[:keep_n]
    kept = sorted(scored_sorted, key=lambda x: x[0])
    out = " ".join(t for _, _, t in kept)
    notes.append(f"Mantidos {len(kept)} de {len(tokens)} tokens via importance scoring.")
    return out, notes


def _llmlingua_question_aware(prompt: str, question: str, ratio: float) -> tuple[str, List[str]]:
    """Bias keep-decision toward tokens that overlap with the question."""
    notes = [f"Question-aware: viés para tokens relacionados a “{question[:60]}”."]
    q_tokens = {re.sub(r"[^\wÀ-ÿ]", "", w).lower() for w in question.split() if len(w) > 2}
    tokens = _split_keep_punct(prompt)
    keep_n = max(1, int(len(tokens) * (1 - (1 - ratio) * 0.7)))
    scored = []
    for i, t in enumerate(tokens):
        bare = re.sub(r"[^\wÀ-ÿ]", "", t).lower()
        score = 0.4
        if bare in _STOPWORDS:
            score = 0.05
        if bare in q_tokens:
            score += 1.5
        if any(qt in bare or bare in qt for qt in q_tokens if qt):
            score += 0.6
        if bare.isdigit() or len(bare) > 7:
            score += 0.3
        scored.append((i, score, t))
    scored_sorted = sorted(scored, key=lambda x: -x[1])[:keep_n]
    kept = sorted(scored_sorted, key=lambda x: x[0])
    out = " ".join(t for _, _, t in kept)
    notes.append(f"Tokens relevantes à pergunta priorizados; final {len(kept)}/{len(tokens)}.")
    return out, notes


def _llmlingua_coarse_to_fine(prompt: str, ratio: float) -> tuple[str, List[str]]:
    """Two-stage: first drop redundant sentences, then compress remaining."""
    notes = ["Coarse: removeu sentenças com baixa densidade informacional."]
    sentences = re.split(r"(?<=[.!?])\s+", prompt.strip())
    if len(sentences) > 1:
        scored = []
        for s in sentences:
            tokens = _split_keep_punct(s)
            unique = len({t.lower() for t in tokens})
            density = unique / max(1, len(tokens))
            scored.append((density * len(tokens), s))
        scored.sort(key=lambda x: -x[0])
        keep_sentences = max(1, int(len(sentences) * 0.7))
        kept_sentences = [s for _, s in scored[:keep_sentences]]
        # restore order
        order = {s: i for i, s in enumerate(sentences)}
        kept_sentences.sort(key=lambda s: order.get(s, 0))
        first_pass = " ".join(kept_sentences)
        notes.append(f"Sentenças: {len(kept_sentences)}/{len(sentences)} preservadas.")
    else:
        first_pass = prompt
    second, second_notes = _llmlingua_compress(first_pass, ratio)
    notes.append("Fine: aplicou compressão por token.")
    notes.extend(second_notes)
    return second, notes


def _foundry_optimize(prompt: str) -> tuple[str, List[str]]:
    """Simulates Foundry prompt-optimizer: rewrites for clarity + structure."""
    notes = [
        "Foundry prompt-optimizer: estrutura system/user, define formato de saída.",
        "Adiciona âncora anti-alucinação e exemplos few-shot quando ausentes.",
    ]
    cleaned = prompt.strip()
    for pat, repl in _FILLER_REPLACEMENTS:
        cleaned = re.sub(pat, repl, cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    optimized = (
        "# Role\n"
        "Você é um assistente especializado.\n\n"
        "# Task\n"
        f"{cleaned}\n\n"
        "# Output format\n"
        "Responda em JSON com chaves: resposta, citacoes, confianca (0-1).\n\n"
        "# Constraints\n"
        "- Use APENAS o contexto fornecido. Nunca invente.\n"
        "- Se não souber, retorne resposta=\"não encontrei na base\"."
    )
    notes.append("Saída em formato estruturado (JSON) e role/task/format/constraints separados.")
    return optimized, notes


def _foundry_clarity(prompt: str) -> tuple[str, List[str]]:
    """Lighter Foundry optimization: clarity-only rewrite, preserve length."""
    notes = ["Foundry clarity: reescreve para imperativos curtos sem mudar tamanho."]
    cleaned = prompt
    for pat, repl in _FILLER_REPLACEMENTS:
        cleaned = re.sub(pat, repl, cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = re.sub(r"^(você|tu|vc)\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(é importante que|gostaria que)\b\s*", "", cleaned, flags=re.IGNORECASE)
    return cleaned, notes


@router.post("/api/optimize", response_model=OptimizeResponse)
async def optimize(payload: OptimizeRequest) -> OptimizeResponse:
    src = payload.prompt.strip()
    if not src:
        return OptimizeResponse(
            technique=payload.technique, original_prompt="", optimized_prompt="",
            original_tokens=0, optimized_tokens=0, compression_ratio=1.0,
            saved_tokens=0, cost_saved_usd=0.0, notes=["Prompt vazio."],
        )

    # Simulated processing latency for the demo — the heuristic itself is
    # near-instantaneous, but the UI should feel like a real optimizer call.
    await asyncio.sleep(2.0 + random.uniform(0, 0.8))

    if payload.technique == "llmlingua_compress":
        opt, notes = _llmlingua_compress(src, payload.target_ratio)
    elif payload.technique == "llmlingua_question_aware":
        q = (payload.question or "").strip() or "pergunta principal"
        opt, notes = _llmlingua_question_aware(src, q, payload.target_ratio)
    elif payload.technique == "llmlingua_coarse_to_fine":
        opt, notes = _llmlingua_coarse_to_fine(src, payload.target_ratio)
    elif payload.technique == "foundry_optimize":
        opt, notes = _foundry_optimize(src)
    elif payload.technique == "foundry_clarity":
        opt, notes = _foundry_clarity(src)
    else:
        opt, notes = src, ["Técnica desconhecida."]

    orig_t = _approx_tokens(src)
    opt_t = _approx_tokens(opt)
    ratio = round(opt_t / orig_t, 3) if orig_t else 1.0
    saved = max(0, orig_t - opt_t)
    # gpt-4o input price ~$2.50 / 1M tokens
    cost_saved = round(saved * 2.5e-6, 6)

    return OptimizeResponse(
        technique=payload.technique,
        original_prompt=src,
        optimized_prompt=opt,
        original_tokens=orig_t,
        optimized_tokens=opt_t,
        compression_ratio=ratio,
        saved_tokens=saved,
        cost_saved_usd=cost_saved,
        notes=notes,
    )


__all__ = ["router", "MENU_TITLE", "MENU_ICON"]
