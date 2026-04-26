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

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                      User Query                         │
│            "At-risk 세그먼트의 특징과 대응 전략은?"          │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│                  LangGraph Agent                        │
│                                                         │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐            │
│  │  Router   │──▶│ Retriever│──▶│ Reporter │            │
│  │ (Hybrid) │   │          │   │  (LLM)   │            │
│  └──────────┘   └────┬─────┘   └──────────┘            │
│                      │                                  │
│         ┌────────────┼────────────┐                     │
│         ▼            ▼            ▼                     │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐                │
│  │PostgreSQL│ │ ChromaDB │ │ Canned   │                │
│  │  (SQL)   │ │  (VoC)   │ │ Queries  │                │
│  └──────────┘ └──────────┘ └──────────┘                │
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
| LLM (local) | Ollama (Llama 3.1 8B) / Gemini 2.0 Flash | Development and evaluation |
| LLM (deployed) | Claude Haiku 4.5 (Anthropic) | Production API — environment-variable switchable |
| API | FastAPI + Pydantic | REST endpoints with schema validation |
| Deployment | Google Cloud Run | Serverless, pay-per-request ($0 when idle) |
| Database (cloud) | Supabase PostgreSQL | Free tier, Session Pooler for IPv4 |
| CI/CD | GitHub Actions | Lint (ruff) + schema check + API tests on every push |
| Containerization | Docker + Docker Compose | Local: PostgreSQL + FastAPI in single compose |

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

- **voc** → ChromaDB semantic search (top 5 documents with metadata)
- **trend** → Pre-built SQL queries against `trend_monthly`, `chronos_forecast`
- **switching** → Pre-built SQL with JOIN across `segment_summary` + `switching_implications`
- **mixed** → Both ChromaDB + SQL, with keyword-based SQL selection (churn reasons, timeline, segments)
- **methodology** → SQL queries against `lda_topics`, `bertopic_documents`, `lda_bertopic_consensus`

Key design: SQL queries include pre-computed interpretation labels (e.g., `ANTITRO_LEADS` / `HNS_LEADS` for ratio > 1.0) so the LLM doesn't need to perform numerical comparison — a pattern that eliminated ratio misinterpretation errors entirely.

### Reporter

The reporter generates Korean-language answers grounded in retrieved data. The system prompt includes:

- **Interpretation rules**: ratio semantics, date format conventions, signal type definitions
- **Guardrails**: "answer based ONLY on provided data", "do NOT contradict the data"
- **Format rules**: cite specific numbers and months, keep answers concise

---

## Data Layer

### Dual Storage Design

| Store | Purpose | Data |
|-------|---------|------|
| PostgreSQL | Structured queries, aggregation, cross-layer JOINs | 10 tables, 3,694 rows |
| ChromaDB | Semantic similarity search over VoC text | 1,744 documents, ko-sroberta-multitask embeddings |

**Why two stores?** "경쟁사 언급 이탈률은?" requires SQL aggregation (`GROUP BY competitor_mentioned`). "안티트로 비교한 사람들은 뭐라고 말했어?" requires semantic search. Neither store alone can answer both.

### PostgreSQL Schema (10 tables)

| Table | Source | Rows | Key Columns |
|-------|--------|------|-------------|
| voc_documents | Layer 1 | 1,744 | source, signal_type, churn_score, competitor_mentioned |
| temporal_signals | Layer 1 | 43 | month, churn_rate, positive_rate |
| lda_topics | Layer 1 | 56 | source, mode, coherence, keywords |
| bertopic_documents | Layer 1 | 1,742 | bertopic_id |
| lda_bertopic_consensus | Layer 1 | 12 | lda_topic, confidence |
| trend_monthly | Layer 2 | 76 | 16 search volume columns (Korean) |
| chronos_forecast | Layer 2 | 12 | forecast_median, forecast_low, forecast_high |
| segment_summary | Layer 3 | 4 | segment, switching_probability |
| switching_implications | Layer 3 | 4 | risk_level, recommended_action |
| timeline_analysis | Layer 3 | 1 | antitro_reversal_point, current_ratio |

### ChromaDB Collection

- **Model**: `jhgan/ko-sroberta-multitask` (Korean sentence embedding)
- **Documents**: 1,744 VoC texts with metadata filters (source, signal_type, churn_score, competitor_mentioned)
- **Metadata filtering**: supports queries like "이탈위험 신호 중 경쟁사 언급 문서만 검색"

---

## Evaluation

### Router Accuracy

**Overall: 83.1% (74/89 questions)**

| Iteration | Change | Accuracy |
|-----------|--------|----------|
| v1 | LLM-only router | 44.0% |
| v2 | Keyword hints in prompt | 62.0% |
| v3 | Hybrid router + methodology category | 78.0% |
| v3 + eval fix | expected_type re-examination + style normalization | **83.1%** |

### Evaluation Set Design

89 questions across 8 categories, each tagged with `eval_category` and `eval_strategy`:

| Category | Questions | Tests |
|----------|-----------|-------|
| fact_checking | 15 | Exact number/date retrieval from database |
| nuance_sentiment | 15 | Sentiment vs intent separation, uncertainty detection, hallucination test |
| strategic_reasoning | 10 | Causal reasoning, resource allocation, strategic tradeoffs |
| conflict_ambiguity | 11 | Leading vs lagging indicators, fallacy of average, model limitations |
| edge_case | 8 | Slang normalization, boundary adherence, multi-intent extraction |
| domain_knowledge | 10 | Ingredient trends, channel analysis, seasonal patterns |
| pipeline_diagnostic | 10 | Compound filters, schema awareness, output control |
| methodology | 10 | LDA/BERTopic/Chronos method knowledge |

**23 evaluation strategies** including: `sentiment_intent_separation`, `hallucination_test`, `business_action_differentiation`, `causal_reasoning`, `fallacy_of_average`, `strategic_tradeoff`, `compound_filter_test`, `schema_awareness`.

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

---

## Design Decisions and Iteration Log

### 1. SQL Pre-computation over LLM Numerical Reasoning

**Problem**: LLM (Llama 8B) interpreted ratio 0.334 as "reversal", incorrectly identifying March 2025 as the reversal point instead of June 2025 (ratio 1.027).

**Solution**: Added `ANTITRO_LEADS` / `HNS_LEADS` labels in the SQL query layer. The LLM reads labels instead of comparing numbers.

**Result**: Reversal point accuracy corrected from "2025년 3월" (wrong) to "2025년 6월" (correct).

**Takeaway**: In production RAG systems, push interpretation logic to the data layer. LLMs generate text; databases compare numbers.

### 2. RAG + SQL Aggregation for Analytical Questions

**Problem**: VoC-only retrieval (5 documents) produced biased answers — e.g., citing one Clinical Strength import complaint as the main churn reason.

**Solution**: Combined ChromaDB retrieval (specific VoC examples) with SQL aggregation (category-level counts: 가려움 291, 자극 90, 뾰루지 63) in the same LLM context.

**Result**: Answers shifted from anecdotal ("직구 불만") to quantitative ("가려움 291건, 자극 90건, 뾰루지 63건이 주요 이탈 원인").

**Takeaway**: RAG alone gives examples; SQL gives statistics. Combining both produces analyst-grade answers.

### 3. Hybrid Router over Pure LLM Router

**Problem**: Llama 8B showed default-value bias in Korean 5-category classification. Prompt engineering moved the bias from "trend" to "voc" but didn't eliminate it.

**Solution**: Keyword-based fast-path for unambiguous queries + LLM fallback for ambiguous ones. This is a common production pattern — using LLM only where it adds value.

**Result**: Router accuracy 44% → 83.1% with lower latency and zero API cost for keyword-matched queries.

**Takeaway**: "LLM을 쓸 수 있다"와 "LLM을 써야 한다"는 다른 문제. Deterministic classification where patterns are clear; LLM where ambiguity exists.

### 4. Date Format Interpretation Rule

**Problem**: LLM reported "2026년 4월 30일 현재" — treating the month-end resampled date as "today's date."

**Solution**: Added explicit interpretation rule to reporter prompt: "Dates use month-end format. Say 'X월 기준' instead of 'X월 30일 현재'."

**Result**: Date references corrected across all trend queries.

### 5. Segment JOIN for Actionable Answers

**Problem**: "At-risk 대응 전략은?" only returned segment statistics. The intervention recommendations were in a separate table (`switching_implications`).

**Solution**: SQL JOIN across `segment_summary` and `switching_implications` in a single query, providing both characteristics and recommended actions to the LLM.

**Result**: Answers now include "ingredient transparency content, medical frame alignment" — actionable strategy, not just numbers.

### 6. Multi-LLM Architecture

**Problem**: Ollama (local) doesn't work on Cloud Run (serverless). Gemini free tier hit quota limits. Vertex AI had project ID mismatches.

**Solution**: Environment-variable-based LLM provider switching (`LLM_PROVIDER=ollama|gemini|anthropic`). Local development uses Ollama (free), production uses Claude Haiku (cost-effective).

**Result**: Same agent code runs across three LLM backends. Cloud Run deployment uses Claude Haiku at ~$0.004/query.

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
  "answer": "안티트로가 헤드앤숄더를 처음 역전한 시점은 **2025년 6월 기준**입니다. 6월에 안티트로의 비율이 1.027로 1.0을 넘으면서 처음으로 헤드앤숄더를 앞지렀습니다."
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
- **Compute**: Cloud Run (serverless, asia-northeast3)
- **Database**: Supabase PostgreSQL (free tier, Seoul region)
- **LLM**: Claude Haiku 4.5 via Anthropic API
- **VoC Embeddings**: ChromaDB in-container with pre-downloaded ko-sroberta-multitask model
- **CI/CD**: GitHub Actions (lint + test on push)

**Cost**: ~$0 idle, ~$0.004 per query (LLM token cost). Cloud Run charges only for active requests.

---

## Local Development

### Prerequisites

- Docker Desktop
- Python 3.10+
- Ollama (for local LLM)

### Quick Start

```bash
# Clone
git clone https://github.com/ChangyeolAidenOh/consumer-signal-agentic-platform.git
cd consumer-signal-agentic-platform

# Start PostgreSQL
docker-compose up -d

# Python environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Load data (requires upstream pipeline output CSVs)
python etl/load_all.py --data-dir /path/to/pg-hns-consumer-signal-pipeline

# Index VoC into ChromaDB
python rag/index.py

# Start API server
uvicorn api.main:app --reload --port 8000

# Open Swagger UI
open http://localhost:8000/docs
```

### CLI Usage

```bash
# Direct agent query
python -m agent.run "안티트로가 헤드앤숄더를 역전한 시점은 언제야?"

# Run evaluation set (89 questions)
python -m evals.run_eval
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| DATABASE_URL | localhost:5433 | PostgreSQL connection string |
| LLM_PROVIDER | ollama | LLM backend: `ollama`, `gemini`, or `anthropic` |
| OLLAMA_HOST | http://localhost:11434 | Ollama server URL |
| GOOGLE_API_KEY | — | Gemini API key (if LLM_PROVIDER=gemini) |
| ANTHROPIC_API_KEY | — | Anthropic API key (if LLM_PROVIDER=anthropic) |

---

## Project Structure

```
consumer-signal-agentic-platform/
│
├── agent/                          # LangGraph agent
│   ├── state.py                    # Agent state definition (TypedDict)
│   ├── tools.py                    # VoC search (ChromaDB) + SQL query (PostgreSQL)
│   ├── graph.py                    # Router → Retriever → Reporter graph
│   └── run.py                      # CLI entry point
│
├── api/                            # FastAPI serving layer
│   ├── main.py                     # Endpoints: /api/v1/analyze, /health
│   └── schemas.py                  # Pydantic request/response models
│
├── db/                             # Database
│   ├── schema.sql                  # PostgreSQL schema (10 tables)
│   └── sample_queries.sql          # 10 analysis queries for verification
│
├── etl/                            # Data loading
│   ├── load_all.py                 # CSV → PostgreSQL loader
│   └── check_columns.py           # CSV column inspector
│
├── rag/                            # Vector search
│   ├── index.py                    # VoC → ChromaDB indexing
│   └── search.py                   # CLI search with metadata filters
│
├── evals/                          # Evaluation
│   ├── evaluation_set.json         # 89 questions, 8 categories, 23 strategies
│   └── run_eval.py                 # Automated evaluation runner
│
├── tests/                          # CI tests
│   └── test_api.py                 # Health + schema verification
│
├── .github/workflows/
│   └── ci.yml                      # GitHub Actions: lint + test
│
├── Dockerfile                      # Cloud Run container
├── startup.sh                      # Container entrypoint
├── docker-compose.yml              # Local: PostgreSQL + FastAPI
├── requirements.txt
├── .env.example
└── .gitignore
```

---

## Known Limitations and Future Work

### Current Limitations

1. **Router cross-layer accuracy (63.6% on conflict_ambiguity)**: Queries that need both VoC and trend data sometimes get routed to a single source. 15 remaining mismatches are primarily caused by keyword overlap — e.g., "카테고리 성장에도 HNS가 위험한 이유" triggers `trend` due to "카테고리" keyword, but should be `mixed`. A multi-label scoring router would resolve this.

2. **No real-time data ingestion**: The platform queries a static snapshot of H&S pipeline outputs. New VoC data requires manual re-indexing (`python rag/index.py`). An automated ingestion pipeline (Airflow/Prefect) would enable continuous updates.

3. **Single-brand scope**: Currently limited to H&S vs Antitro analysis. The architecture supports multi-brand extension but would require schema changes and additional data collection.

4. **Answer quality varies by LLM**: Llama 3.1 8B (local) produces shorter, sometimes inaccurate answers. Claude Haiku (deployed) is significantly more accurate and detailed. Evaluation results in this README reflect the Llama 8B router accuracy; deployed answer quality is higher.

### Planned Improvements

- **Evaluation set v2 enrichment**: Add test VoC documents to ChromaDB for Nuance & Sentiment category testing (方式 B)
- **Reporter prompt v3**: Incorporate Reconciliation Framework (data source hierarchy, fallacy-of-average guardrail, limitation acknowledgment protocol)
- **Langfuse integration**: LLM call tracing for cost/latency/failure monitoring
- **Multi-label router**: Score queries across all categories simultaneously instead of first-match keyword routing

---

## Related Projects

- **[H&S Consumer Signal Detection Pipeline](https://github.com/ChangyeolAidenOh/pg-hns-consumer-signal-pipeline)** — The upstream 3-layer analysis pipeline that generates the data this platform serves
- **[CNP VoC Pipeline](https://github.com/ChangyeolAidenOh/cnp-voc-pipeline)** — Earlier VoC analysis project (Korean NLP, causal signal detection)
- **[ANUA Review NLP](https://github.com/ChangyeolAidenOh/anua-review-nlp)** — English-language VoC analysis with Amazon review data
