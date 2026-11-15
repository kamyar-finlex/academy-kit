# Remote LLM & Multi-Model Routing Research

*Research snapshot: November 2026*

When building a private learning academy from a repository's Markdown and source files, not every step needs the same intelligence level. Treating the entire pipeline as a single giant prompt to one model is either too slow locally or unnecessarily expensive remotely.

This document evaluates cost-effective remote LLMs and recommends a **multi-model routing architecture** tailored to `academy-kit`.

---

## 1. Why a Multi-Model Pipeline Beats a Single Model

Generating a high-quality academy involves three distinct cognitive workloads across [studio.py](../engine/studio.py) and [app.js](../engine/portal/assets/app.js):

1. **Triage, Grouping & Classification (`_plan_lessons`, term glosses):**
   Cluster dozens of source files into coherent lessons, filter relevant files, and produce brief glossary translations. This requires speed and low cost rather than deep synthesis.
2. **Human-Facing Lesson Authoring (`_generate_one_lesson`):**
   Transform dense technical Markdown into clear prose, plain-words notes (`explain`), worked examples, common pitfalls, and multi-choice quizzes without inventing facts not present in the source documents.
3. **Structured Visualization & Mind-Tree Graphs (`VIZ_SYSTEM`, `mindMap`, Mermaid specs):**
   Extract non-looping flow diagrams (`nodes` + `edges`), concept hierarchies, and two-sided mind-tree graphs directly from passages or cross-lesson mentions. Weak models often break JSON schemas, emit orphan edges, create invalid cycles, or drop hierarchy links when extracting diagrams.

Splitting these stages across specialized models lets you pay frontier/reasoning prices **only** where structural fidelity matters most.

---

## 2. Candidate Remote LLMs & Pricing Comparison

*Standard API rates per 1 million tokens (USD), verified November 2026:*

| Provider & Model | Input | Cached Input | Output | Context Window | Best Role in `academy-kit` |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **OpenAI `GPT-5 nano`** | `$0.05` | `$0.005` | `$0.40` | 400K | Bulk file classification, lesson grouping, JSON repair/normalization. |
| **Anthropic `Claude Haiku 5.5`** *(<=100K)* | `$0.10` | ~0.05x–0.1x | `$0.50` | >100K (`$0.50`/`$2.50` over 100K) | Primary **lesson writer**: clear pedagogical prose + top-tier JSON schema stability. |
| **DeepSeek `deepseek-flash`** *(V4.1-Flash)* | `$0.15` *(off-peak)* / `$0.30` *(peak)* | `$0.003` / `$0.006` | `$0.60` / `$1.20` | Long context | Ultra-low-cost remote batch runs (replaces retired `deepseek-chat`/`deepseek-reasoner`); check org data residency first. |
| **OpenAI `GPT-5 mini`** | `$0.25` | `$0.025–$0.03` | `$2.00` | 272K–400K | **Diagrams & mind-tree graphs** + strong single-vendor all-rounder for lesson writing. |
| **Google `Gemini 3.1 / 3.5 Flash-Lite`** | `~$0.25–$0.30` | — | `~$1.50–$2.50` | Long context | High-volume document summarization and chunk pre-processing. |
| **DeepSeek `deepseek-v4-pro`** | `$0.66` *(off-peak)* / `$1.32` *(peak)* | `$0.022` / `$0.044` | `$1.98` / `$3.96` | Long context | Low-cost reasoning for code-heavy architecture graphs when residency rules allow. |
| **Google `Gemini 3.8 Flash`** | `$0.75` *(2026 promo; `$1.50` in 2027)* | `~$0.075` | `$3.75` *(2026 promo; `$7.50` in 2027)* | Long context | Cross-file synthesis when a lesson spans many Markdown + code files simultaneously. |
| **OpenAI `o4-mini` / `o3-mini`** | `$1.10` | `$0.55` | `$4.40` | 200K | Dedicated reasoning fallback for complex dependency or workflow graphs. |
| **Anthropic `Claude Sonnet 5.5`** | `$2.00` | ~0.05x–0.1x | `$10.00` | Long context | Premium polish for flagship lessons, nuanced explanations, and complex mind-tree graphs. |
| **Google `Gemini 3.1 Pro Preview`** | `$2.00` *(<=200K)* | `$0.20` | `$12.00` *(<=200K)* | >200K (`$4`/`$18` over 200K) | Heavy multi-repo architecture synthesis (overkill for routine lessons). |

> **Cost multipliers & discounts:** OpenAI, Anthropic, and Google all offer **~50% Batch API discounts** for asynchronous rebuilds and **50–90% prompt-caching discounts** on shared system instructions.

---

## 3. Recommended Multi-Model Stacks & Reasons

Assuming a typical **25-document repository** (~120K input tokens + ~30K output tokens across 10–14 lessons plus diagrams):

### Option A — Recommended Best Balance (Hybrid Local + Dual Remote, ~$0.03–$0.05 / build)
- **Stage 1 (Grouping & Triage):** Local Ollama (`gemma4:26b` with `think=false`, **$0**) or **`GPT-5 nano`**
- **Stage 2 (Lesson Writing):** **`Claude Haiku 5.5`**
- **Stage 3 (Diagrams & Mind-Tree Graphs):** **`GPT-5 mini`** (or **`Claude Sonnet 5.5`** for flagship docs)

**Why this wins:**
- Keeps file scanning, planning, and classification completely free (local) or near-zero (`$0.05/1M` input).
- `Claude Haiku 5.5` writes clean, human-readable prose and adheres strictly to nested lesson schemas at `$0.10 / $0.50` per 1M tokens (as long as individual prompts stay under 100K tokens).
- `GPT-5 mini` brings strong native JSON mode and spatial/topological reasoning for node/edge flow graphs and two-sided mind trees without paying full Pro/Sonnet rates on every paragraph.

### Option B — Simplest Single-Provider Budget Stack (OpenAI-only, ~$0.04–$0.09 / build)
- **Stage 1 (Grouping & Triage):** **`GPT-5 nano`** (`$0.05 / $0.40`)
- **Stage 2 & 3 (Lessons + Diagrams/Mind Trees):** **`GPT-5 mini`** (`$0.25 / $2.00`)

**Why choose this:** One API key, one billing dashboard, 272K–400K context headroom, and strong structured outputs.

### Option C — Maximum Quality for Complex Repositories (~$0.12–$0.25 / build)
- **Stage 1 (Grouping & Triage):** Local Ollama or **`GPT-5 nano`**
- **Stage 2 (Lesson Writing):** **`Claude Haiku 5.5`** (or **`Gemini 3.8 Flash`** for huge multi-file context)
- **Stage 3 (Diagrams & Mind-Tree Graphs):** **`Claude Sonnet 5.5`**

**Why choose this:** Still costs less than a quarter per full academy rebuild while giving flagship lessons and architectural mind-tree graphs the clearest human pedagogy.

---

## 4. Implementation Design Guidelines & Caveats

1. **Always Separate Planning, Prose, and Graph Extraction:**
   Avoid generating prose lessons and diagram graphs in a single monolithic prompt. Running diagram/mind-tree extraction as focused post-passes over small passages keeps prompts short (`<10K` tokens) and prevents reasoning bloat.
2. **Enforce Two-Step JSON -> Mermaid Rendering (Never Raw Mermaid):**
   Consistent with `StructEval` findings and `academy-kit`'s existing `VIZ_SYSTEM` -> `toMermaid` pipeline in [app.js](../engine/portal/assets/app.js), require the remote model to output constrained JSON (`nodes`, `edges`, `type`) and render Mermaid/SVG deterministically in client code. This eliminates bracket/arrow syntax errors on budget models.
3. **Control Thinking Tokens Explicitly:**
   On reasoning-capable models (`Gemini 3.8 Flash`, `o4-mini`, DeepSeek V4), internal thinking tokens are billed at **output rates**. Explicitly disable thinking for grouping, classification, and plain-JSON formatting; enable it only for complex diagram and mind-tree synthesis.
4. **Respect Organization Privacy & Data Residency:**
   When generating academies from private company or organization repositories, use enterprise/zero-data-retention API endpoints (Anthropic API, OpenAI API, Google Vertex/Gemini API) or keep sensitive pre-filtering strictly local in Ollama before sending excerpts remotely.
