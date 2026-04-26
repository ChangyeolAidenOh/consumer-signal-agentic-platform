# Consumer Signal Agentic Platform

A **LangGraph multi-agent platform** that transforms the [H&S 3-Layer Consumer Signal Detection Pipeline](https://github.com/ChangyeolAidenOh/pg-hns-consumer-signal-pipeline) from a one-time analysis into an **always-queryable system**. Users ask natural-language questions about consumer switching signals, and the agent routes queries across PostgreSQL (structured data) and ChromaDB (VoC embeddings) to generate data-grounded answers.

> **"Can we turn a static consumer analysis into a living system where any stakeholder — brand manager, data analyst, or strategist — can ask questions and get answers backed by the underlying 3-layer data?"**

**Live API**: [https://hns-agent-887686014711.asia-northeast3.run.app/docs](https://hns-agent-887686014711.asia-northeast3.run.app/docs)

---

## Table of Contents

- [Motivation](#motivation)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Agent Design](#agent-design)
  - [Router](#router)
  - [Retriever](#retriever)
  - [Reporter](#reporter)
- [Data Layer](#data-layer)
- [Evaluation](#evaluation)
  - [Router Accuracy](#router-accuracy)
  - [Evaluation Set Design](#evaluation-set-design)
  - [Evaluation Strategy Highlights](#evaluation-strategy-highlights)
  - [Category-Level Results](#category-level-results)
- [Design Decisions and Iteration Log](#design-decisions-and-iteration-log)
- [API Reference](#api-reference)
- [Deployment](#deployment)
- [Local Development](#local-development)
- [Project Structure](#project-structure)
- [Known Limitations and Future Work](#known-limitations-and-future-work)

---

## Motivation

The upstream [H&S pipeline](https://github.com/ChangyeolAidenOh/pg-hns-consumer-signal-pipeline) produces 10 output CSV files across 3 analytical layers (VoC NLP, search trends, switching probability). These files contain actionable insights — but accessing them requires opening CSVs, writing pandas queries, and mentally connecting findings across layers.

This platform solves that by:

1. **Loading all pipeline outputs into a dual data store** — PostgreSQL for structured queries, ChromaDB for semantic VoC search
2. **Wrapping a LangGraph agent** around both stores so users can ask questions in natural language
3. **Serving the agent as a REST API** deployable to any cloud environment

The result: a stakeholder can type "안티트로가 헤드앤숄더를 역전한 시점은 언제야?" and get back "2025년 6월 기준으로 역전, ratio 1.027" — sourced directly from the data, not hallucinated.

A cross-layer SQL query immediately confirms the data: competitor-mentioned VoC documents show an 82.2% churn rate vs 20.4% for non-competitor documents — a 4:1 signal gap that the agent surfaces through both SQL aggregation and VoC semantic search.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                      User Query                         │
│            "What are the At-risk segment features?"     |
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│                  LangGraph Agent                        │
│                                                         │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐             │
│  │  Router   │──▶│ Retriever│──▶│ Reporter │            │
│  │ (Hybrid) │   │          │   │  (LLM)   │             │
│  └──────────┘   └────┬─────┘   └──────────┘             │
│                      │                                  │
│         ┌────────────┼────────────┐                     │
│         ▼            ▼            ▼                     │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐                 │
│  │PostgreSQL│ │ ChromaDB │ │ Canned   │                 │
│  │  (SQL)   │ │  (VoC)   │ │ Queries  │                 │
│  └──────────┘ └──────────┘ └──────────┘                 │
└─────────────────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│                  FastAPI + Cloud Run                    │
│          POST /api/v1/analyze → JSON response           │
└─────────────────────────────────────────────────────────┘
```

---

## Tech Stack

| Layer | Technology | Role |
|-------|-----------|------|
| Data (structured) | PostgreSQL 15 | 10 tables, 3,694 rows — trends, segments, topic models |
| Data (unstructured) | ChromaDB + ko-sroberta-multitask | 1,744 VoC documents as semantic embeddings |
| Agent | LangGraph | 3-node graph: Router → Retriever → Reporter |
| LLM (local dev) | Ollama (Llama 3.1 8B) | Local development and initial evaluation |
| LLM (local alt) | Gemini 2.0 Flash (Google AI Studio) | Local testing via `langchain-google-genai` |
| LLM (deployed) | Claude Haiku 4.5 (Anthropic) | Production API via `langchain-anthropic` |
| API | FastAPI + Pydantic | REST endpoints with schema validation |
| Deployment | Google Cloud Run | Serverless, asia-northeast3, pay-per-request |
| Database (cloud) | Supabase PostgreSQL | Free tier, Session Pooler (IPv4), Seoul region |
| CI/CD | GitHub Actions | Lint (ruff) + schema check + API tests on every push |
| Containerization | Docker + Docker Compose | Local: PostgreSQL + FastAPI in single compose |

**Multi-LLM switching**: The same agent code supports three LLM backends via `LLM_PROVIDER` environment variable (`ollama`, `gemini`, `anthropic`). Local development uses Ollama (free) or Gemini (free tier), production uses Claude Haiku (~$0.004/query).

---

## Agent Design

### Router

**Hybrid routing: keyword fast-path + LLM fallback.**

The router classifies incoming queries into 5 categories: `voc`, `trend`, `switching`, `mixed`, `methodology`.

Initial approach used LLM-only routing (Llama 3.1 8B), which achieved only 44% classification accuracy due to default-value bias in Korean query understanding. Through three iterations, the router evolved:

| Version | Approach | Accuracy |
|---------|----------|----------|
| v1 | LLM-only (Llama 8B) | 44% |
| v2 | LLM + keyword hints in prompt | 62% |
| v3 | Hybrid (keyword fast-path + LLM fallback) | 78% → 83.1% after eval set refinement |

The hybrid approach routes unambiguous queries instantly via keyword matching (zero latency, deterministic) and delegates ambiguous queries to the LLM. This decision reflects a production principle: **use LLM where it adds value (generation), not where rules suffice (classification).**

### Retriever

The retriever selects data sources based on query type and content keywords:

- **voc** → ChromaDB semantic search (top 5 documents with metadata). Additionally triggers SQL churn aggregation if query contains churn-related keywords.
- **trend** → Pre-built SQL queries against `trend_monthly`, `chronos_forecast`. Includes `ANTITRO_LEADS` / `HNS_LEADS` pre-computed labels for ratio interpretation.
- **switching** → Pre-built SQL with JOIN across `segment_summary` + `switching_implications`, returning both segment characteristics and intervention strategies in a single context.
- **mixed** → Both ChromaDB + SQL, with keyword-based SQL selection: churn reasons (`unnest` signal breakdown), antitro timeline, segment summary, or monthly churn depending on query keywords. Default: churn reasons + antitro timeline combined.
- **methodology** → SQL queries against `lda_topics` (coherence scores), `bertopic_documents` (topic distribution), `lda_bertopic_consensus` (12 consensus signals).

Key design: SQL queries include **pre-computed interpretation labels** (e.g., `ANTITRO_LEADS` / `HNS_LEADS` for ratio ≥ 1.0) so the LLM doesn't need to perform numerical comparison — a pattern that eliminated ratio misinterpretation errors entirely. See [Design Decision #1](#1-sql-pre-computation-over-llm-numerical-reasoning).

### Reporter

The reporter generates Korean-language answers grounded in retrieved data. The system prompt underwent 3 iterations of improvement:

**v1** (initial): Simple instruction to answer based on data. Produced ratio misinterpretation and date format errors.

**v2** (interpretation rules added):
- **Ratio semantics**: "ratio ≥ 1.0 means Antitro surpassed HNS. ratio < 1.0 means HNS still ahead."
- **Date conventions**: "Dates use month-end format (e.g. 2025-06-30 = June 2025). Say 'X월 기준', never 'X월 30일 현재'."
- **Signal definitions**: "signal=이탈위험 means churn risk. churn_score > 0 means churn signals detected."

**v3** (guardrails strengthened):
- "Answer based ONLY on provided data. Do NOT contradict the data."
- "If VoC documents show complaints, report them as complaints."
- "Keep answers concise (3-5 sentences). Cite specific numbers and months."

---

## Data Layer

### Dual Storage Design

| Store | Purpose | Data |
|-------|---------|------|
| PostgreSQL | Structured queries, aggregation, cross-layer JOINs | 10 tables, 3,694 rows |
| ChromaDB | Semantic similarity search over VoC text | 1,744 documents, ko-sroberta-multitask embeddings |

**Why two stores?** "경쟁사 언급 이탈률은?" requires SQL aggregation (`GROUP BY competitor_mentioned` → 82.2% vs 20.4%). "안티트로 비교한 사람들은 뭐라고 말했어?" requires semantic search across 1,744 documents. Neither store alone can answer both. This dual-store architecture enables the agent to combine **statistical evidence** (SQL) with **qualitative evidence** (VoC) in a single response.

### PostgreSQL Schema (10 tables)

| Table | Source | Rows | Key Columns |
|-------|--------|------|-------------|
| voc_documents | Layer 1 | 1,744 | source, date, raw_text, signal_type, churn_score, positive_score, competitor_mentioned |
| temporal_signals | Layer 1 | 43 | month, total, churn, positive, competitor, churn_rate, positive_rate |
| lda_topics | Layer 1 | 56 | scope, source, mode, topic_id, coherence, keywords |
| bertopic_documents | Layer 1 | 1,742 | source, date, raw_text, bertopic_id |
| lda_bertopic_consensus | Layer 1 | 12 | lda_topic, bertopic_id, overlap_keywords, confidence |
| trend_monthly | Layer 2 | 76 | date, category_click, 헤드앤숄더샴푸, 안티트로샴푸, + 14 more Korean columns |
| chronos_forecast | Layer 2 | 12 | date, forecast_median, forecast_low, forecast_high |
| segment_summary | Layer 3 | 4 | segment, n_docs, churn_rate, competitor_rate, switching_probability |
| switching_implications | Layer 3 | 4 | segment, risk_level, intervention_timing, recommended_action |
| timeline_analysis | Layer 3 | 1 | antitro_first_entry, antitro_reversal_point, current_antitro_ratio |

### ChromaDB Collection

- **Model**: `jhgan/ko-sroberta-multitask` (Korean sentence embedding, 768-dim)
- **Documents**: 1,744 VoC texts with metadata filters (source, signal_type, churn_score, positive_score, net_signal, competitor_mentioned)
- **Metadata filtering**: supports filtered search — e.g., `--filter-signal 이탈위험` returns only churn-risk documents, `--filter-signal 긍정` returns only positive documents
- **Known data issue**: YouTube comments contain duplicate entries (e.g., "헤드앤숄더쓰고 두피염증 싹나음" appears 3 times). A deduplication step before indexing is planned for v2.

---

## Evaluation

### Router Accuracy

**Overall: 83.1% (74/89 questions)**

| Iteration | Change | Accuracy |
|-----------|--------|----------|
| v1 | LLM-only router (Llama 8B) | 44.0% |
| v2 | Keyword hints in LLM prompt | 62.0% |
| v3 | Hybrid router (keyword fast-path + LLM fallback) + methodology category added | 78.0% |
| v3 + eval fix | expected_type re-examination (9 questions reclassified to methodology) + query style normalization (casual professional tone) + 4 irrelevant questions removed | **83.1%** |

Average response time: **9.2s** (Llama 3.1 8B local inference). Claude Haiku (deployed) is faster at ~3-5s.

### Evaluation Set Design

89 questions across 8 categories, each tagged with `eval_category` and `eval_strategy`:

| Category | Questions | What It Tests |
|----------|-----------|---------------|
| fact_checking | 15 | Exact number/date retrieval from database |
| nuance_sentiment | 15 | Sentiment vs intent separation, uncertainty detection, hallucination resistance |
| strategic_reasoning | 10 | Causal reasoning, resource allocation, strategic tradeoffs, counter-intuitive insights |
| conflict_ambiguity | 11 | Leading vs lagging indicators, fallacy of average, model limitations, scenario planning |
| edge_case | 8 | Slang normalization, boundary adherence, multi-intent extraction, contradiction resolution |
| domain_knowledge | 10 | Ingredient trends, channel trust analysis, seasonal patterns, cross-category expectations |
| pipeline_diagnostic | 10 | Compound filters, schema awareness, aggregation accuracy, output control (raw vs summary) |
| methodology | 10 | LDA/BERTopic/Chronos/KMeans method knowledge and selection rationale |

### Evaluation Strategy Highlights

The evaluation set employs **23 distinct eval_strategy tags**. Key strategies and why they matter:

- **`sentiment_intent_separation`**: Tests whether the agent can distinguish between sentiment (positive/negative) and intent (retention/churn risk). A conditionally satisfied consumer ("효과는 있는데 냄새가...") has mixed sentiment but Feature Request intent — not churn. Conflating these leads to incorrect segment assignment.

- **`hallucination_test`**: Deliberately asks questions where the correct answer is "insufficient data to determine." VoC like "이거 원래 거품이 안 나는 건지 불량인 건지 모르겠어요" should NOT be force-classified as positive or negative. An agent that says "판단하기 어렵습니다" scores higher than one that fabricates a classification.

- **`business_action_differentiation`**: Tests whether the agent recommends different actions for different emotional states. Anger (service failure) → immediate compensation. Disappointment (expectation gap) → product page revision. Same negative sentiment, different business response.

- **`fallacy_of_average`**: Tests whether the agent recognizes that aggregate metrics can be misleading. Overall brand risk score 0.068 appears safe, but At-risk (91 docs) + Active Switcher (83 docs) = 10% of users carry concentrated risk.

- **`causal_reasoning`**: Tests whether the agent claims causation vs correlation. Antitro search volume growth and HNS churn signals are temporally correlated, but without marketing strategy data, the agent should NOT claim Antitro's marketing "caused" HNS churn.

- **`schema_awareness`**: Tests whether the agent honestly reports when a requested data column does not exist (e.g., "재구매 의사 컬럼이 있어?"), rather than fabricating data.

### Category-Level Results

| Category | Accuracy |
|----------|----------|
| pipeline_diagnostic | **100.0%** (10/10) |
| fact_checking | **93.3%** (14/15) |
| nuance_sentiment | **93.3%** (14/15) |
| strategic_reasoning | **80.0%** (8/10) |
| methodology | **80.0%** (8/10) |
| edge_case | **75.0%** (6/8) |
| domain_knowledge | **70.0%** (7/10) |
| conflict_ambiguity | **63.6%** (7/11) |

Note: These accuracy scores measure **router classification** (whether the query was sent to the correct data source). Answer quality is a separate dimension — deployed Claude Haiku produces significantly more accurate and detailed answers than the Llama 8B used during evaluation.

---

## Design Decisions and Iteration Log

### 1. SQL Pre-computation over LLM Numerical Reasoning

**Problem**: LLM (Llama 8B) interpreted ratio 0.334 as "reversal", incorrectly identifying March 2025 as the Antitro reversal point instead of June 2025 (ratio 1.027).

**Solution**: Added `ANTITRO_LEADS` / `HNS_LEADS` status labels directly in the SQL query. The LLM reads labels instead of comparing floating-point numbers.

**Result**: Reversal point accuracy corrected from "2025년 3월" (wrong) to "2025년 6월" (correct).

**Takeaway**: In production RAG systems, push interpretation logic to the data layer. LLMs generate text; databases compare numbers.

### 2. RAG + SQL Aggregation for Analytical Questions

**Problem**: VoC-only retrieval (5 documents) produced biased answers — e.g., citing one Clinical Strength import complaint as the main churn reason, when the actual top drivers are 가려움 (291 cases), 자극 (90 cases), 뾰루지 (63 cases).

**Solution**: Combined ChromaDB retrieval (specific VoC examples for qualitative evidence) with SQL aggregation (`unnest` churn signal breakdown for quantitative evidence) in the same LLM context.

**Result**: Answers shifted from anecdotal ("직구 불만이 원인") to quantitative ("가려움 291건, 자극 90건, 뾰루지 63건이 주요 이탈 원인").

**Takeaway**: RAG alone gives examples; SQL gives statistics. Individual VoC documents provide anecdotal evidence, while aggregation provides statistical evidence. Combining both produces analyst-grade answers.

### 3. Hybrid Router over Pure LLM Router

**Problem**: Llama 8B showed default-value bias in Korean 5-category classification (44%). Prompt engineering with keyword hints raised accuracy to 62% but only shifted the bias from "trend" to "voc" — the fundamental limitation persisted.

**Solution**: Keyword-based fast-path for unambiguous queries + LLM fallback for ambiguous ones. This preserves the "Agentic AI" aspect (LLM is still involved) while achieving deterministic accuracy on clear-cut queries.

**Result**: Router accuracy 44% → 83.1% with lower latency and zero API cost for keyword-matched queries.

**Takeaway**: "LLM을 쓸 수 있다"와 "LLM을 써야 한다"는 다른 문제. Deterministic classification where patterns are clear; LLM where ambiguity exists. This is a standard production pattern, not a compromise.

### 4. Date Format Interpretation Rule

**Problem**: LLM reported "2026년 4월 30일 현재" — treating the month-end resampled date ("2026-04-30" in `trend_monthly`) as "today's date."

**Solution**: Added explicit interpretation rule to reporter prompt: "Dates use month-end format. Say 'X월 기준' instead of 'X월 30일 현재'."

**Result**: Date references corrected across all trend queries.

### 5. Segment JOIN for Actionable Answers

**Problem**: "At-risk 대응 전략은?" returned only segment statistics (churn_rate, competitor_rate) from `segment_summary`. The intervention recommendations (risk_level, recommended_action) were stored in a separate table (`switching_implications`).

**Solution**: SQL JOIN across `segment_summary` and `switching_implications` in a single query, providing both characteristics and recommended actions to the LLM in one context block.

**Result**: Answers now include "ingredient transparency content, medical frame alignment" — actionable strategy linked to specific segment data, not just numbers.

### 6. Multi-LLM Architecture

**Problem**: Local development used Ollama (Llama 3.1 8B), but Cloud Run cannot run Ollama (serverless, no persistent process). Google Gemini free tier hit rate limits. Vertex AI had project ID configuration issues.

**Solution**: Environment-variable-based LLM provider switching (`LLM_PROVIDER=ollama|gemini|anthropic`). Each provider is imported conditionally at startup. Local development uses Ollama (free) or Gemini (free tier), production uses Claude Haiku (Anthropic API, ~$0.004/query).

**Result**: Same agent code runs across three LLM backends with no code changes — only environment variable configuration.

---

## API Reference

### `POST /api/v1/analyze`

Run the agent on a natural-language query.

**Request**:
```json
{
  "query": "안티트로가 헤드앤숄더를 역전한 시점은 언제야?"
}
```

**Response**:
```json
{
  "query": "안티트로가 헤드앤숄더를 역전한 시점은 언제야?",
  "query_type": "trend",
  "answer": "안티트로가 헤드앤숄더를 처음 역전한 시점은 **2025년 6월 기준**입니다. 6월에 안티트로의 비율이 1.027로 1.0을 넘으면서 처음으로 헤드앤숄더를 앞지렀습니다. 다만 7월과 8월에는 다시 헤드앤숄더가 앞서갔다가, **2025년 9월부터 안티트로가 본격적으로 우위를 점하기 시작**하여 이후 지속적으로 리드를 유지하고 있습니다."
}
```

### `GET /health`

Health check — verifies database connectivity and returns basic stats.

**Response**:
```json
{
  "status": "ok",
  "tables": 10,
  "voc_count": 1744
}
```

---

## Deployment

### Production (Google Cloud Run)

The platform is deployed on Cloud Run with:
- **Compute**: Cloud Run (serverless, asia-northeast3, Seoul)
- **Database**: Supabase PostgreSQL (free tier, Session Pooler for IPv4 compatibility, Seoul region)
- **LLM**: Claude Haiku 4.5 via Anthropic API
- **VoC Embeddings**: ChromaDB in-container with pre-downloaded ko-sroberta-multitask model (built into Docker image to avoid cold-start download delays)
- **CI/CD**: GitHub Actions (ruff lint + schema validation + API tests on every push)

**Cost**: ~$0 idle (Cloud Run scales to zero), ~$0.004 per query (LLM token cost). Supabase free tier covers database hosting.

---

## Local Development

### Prerequisites

- Docker Desktop (for PostgreSQL container)
- Python 3.10+
- Ollama (for local LLM — install from [ollama.com](https://ollama.com))

### Quick Start

```bash
# Clone
git clone https://github.com/ChangyeolAidenOh/consumer-signal-agentic-platform.git
cd consumer-signal-agentic-platform

# Start PostgreSQL (runs on port 5433 to avoid conflict with local postgres)
docker-compose up -d

# Python environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Load data (requires upstream pipeline output CSVs)
python etl/load_all.py --data-dir /path/to/pg-hns-consumer-signal-pipeline

# Index VoC into ChromaDB
python rag/index.py

# Pull local LLM model
ollama pull llama3.1:8b

# Start API server
uvicorn api.main:app --reload --port 8000

# Open Swagger UI
open http://localhost:8000/docs
```

### CLI Usage

```bash
# Direct agent query
python -m agent.run "안티트로가 헤드앤숄더를 역전한 시점은 언제야?"

# VoC semantic search
python rag/search.py "안티트로 비교 후기"
python rag/search.py --filter-signal 이탈위험 "샴푸 바꿔야 할 것 같아"

# Run evaluation set (89 questions, ~15 min with Llama 8B)
python -m evals.run_eval
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| DATABASE_URL | postgresql://...@localhost:5433/... | PostgreSQL connection string |
| LLM_PROVIDER | ollama | LLM backend: `ollama`, `gemini`, or `anthropic` |
| OLLAMA_HOST | http://localhost:11434 | Ollama server URL (when LLM_PROVIDER=ollama) |
| GOOGLE_API_KEY | — | Google AI Studio API key (when LLM_PROVIDER=gemini) |
| ANTHROPIC_API_KEY | — | Anthropic API key (when LLM_PROVIDER=anthropic) |
| GCP_PROJECT | — | GCP project ID (when using Vertex AI) |
| GCP_LOCATION | — | GCP region (when using Vertex AI) |

---

## Project Structure

```
consumer-signal-agentic-platform/
│
├── agent/                          # LangGraph agent
│   ├── state.py                    # Agent state definition (TypedDict)
│   ├── tools.py                    # VoC search (ChromaDB) + SQL query (PostgreSQL)
│   ├── graph.py                    # Hybrid Router → Retriever → Reporter graph
│   └── run.py                      # CLI entry point
│
├── api/                            # FastAPI serving layer
│   ├── main.py                     # Endpoints: /api/v1/analyze, /health
│   └── schemas.py                  # Pydantic request/response models
│
├── db/                             # Database
│   ├── schema.sql                  # PostgreSQL schema (10 tables, indexes)
│   └── sample_queries.sql          # Analysis queries (cross-layer JOINs, aggregations)
│
├── etl/                            # Data loading
│   ├── load_all.py                 # CSV → PostgreSQL loader (env-var aware)
│   └── check_columns.py           # CSV column inspector for schema alignment
│
├── rag/                            # Vector search
│   ├── index.py                    # VoC → ChromaDB indexing with metadata
│   └── search.py                   # CLI search with metadata filters
│
├── evals/                          # Evaluation
│   ├── evaluation_set.json         # 89 questions, 8 categories, 23 eval strategies
│   └── run_eval.py                 # Automated evaluation with per-category breakdown
│
├── tests/                          # CI tests
│   └── test_api.py                 # Schema verification + health endpoint test
│
├── .github/workflows/
│   └── ci.yml                      # GitHub Actions: ruff lint + pytest on push
│
├── Dockerfile                      # Cloud Run container (pre-downloads embedding model)
├── Dockerfile.local                # Local development Dockerfile (backup)
├── startup.sh                      # Container entrypoint (uvicorn with PORT)
├── docker-compose.yml              # Local: PostgreSQL (5433) + FastAPI (8000)
├── requirements.txt                # Python dependencies
├── .env.example                    # Environment variable template
└── .gitignore
```

---

## Known Limitations and Future Work

### Current Limitations

1. **Router cross-layer accuracy (63.6% on conflict_ambiguity)**: Queries requiring both VoC and trend data sometimes get routed to a single source. 15 remaining mismatches are primarily caused by keyword overlap — e.g., "카테고리 성장에도 HNS가 위험한 이유" triggers `trend` due to "카테고리" keyword, but should be `mixed`. A multi-label scoring router (scoring each category independently and selecting the highest-scoring combination) would address this structural limitation.

2. **YouTube comment duplicates**: Some YouTube comments are duplicated in the source data (e.g., "헤드앤숄더쓰고 두피염증 싹나음" appears 3 times). This inflates certain VoC search results. A deduplication step before ChromaDB indexing is planned.

3. **No real-time data ingestion**: The platform queries a static snapshot of H&S pipeline outputs. New VoC data requires manual re-indexing (`python rag/index.py`). An automated ingestion pipeline (Airflow/Prefect) would enable continuous updates.

4. **Single-brand scope**: Currently limited to H&S vs Antitro analysis. The architecture supports multi-brand extension but would require schema changes and additional data collection.

5. **Answer quality varies by LLM**: Llama 3.1 8B (local) produces shorter, sometimes inaccurate answers. Claude Haiku (deployed) is significantly more accurate and detailed. Evaluation results reflect router classification accuracy; deployed answer quality is higher.

### Planned Improvements

- **Reconciliation Framework in Reporter prompt**: Three principles to be embedded: (1) Data source hierarchy — "Search trends show the market temperature; VoC provides the diagnosis. Report the phenomenon first, then interpret with VoC." (2) Fallacy-of-average guardrail — "When citing aggregate metrics, always check for segment-level concentration." (3) Limitation acknowledgment protocol — "When data is insufficient, state what additional data would resolve the ambiguity rather than fabricating an answer."

- **Evaluation set v2 enrichment**: Add synthetic test VoC documents to ChromaDB (conditional satisfaction, switching hesitation, uncertainty expressions) to enable direct testing of Nuance & Sentiment category accuracy at the answer level, not just router level.

- **Langfuse integration**: LLM call tracing for cost, latency, and failure rate monitoring per query type.

- **Multi-label router**: Score queries across all 5 categories simultaneously and select the highest-scoring combination, rather than first-match keyword routing.

---

## Related Projects

- **[H&S Consumer Signal Detection Pipeline](https://github.com/ChangyeolAidenOh/pg-hns-consumer-signal-pipeline)** — The upstream 3-layer analysis pipeline (VoC NLP × Trend × Switching ML) that generates the data this platform serves
- **[CNP VoC Pipeline](https://github.com/ChangyeolAidenOh/cnp-voc-pipeline)** — Earlier Korean VoC analysis project (causal signal detection, Streamlit dashboard)
- **[ANUA Review NLP](https://github.com/ChangyeolAidenOh/anua-review-nlp)** — English-language VoC analysis with Amazon review data
