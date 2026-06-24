# DeepDive Intelligence — Full Project Analysis

## Overview

DeepDive Intelligence is a deterministic, rule-based news intelligence analysis platform that ingests RSS feeds, processes news articles through a multi-stage pipeline, builds a causal knowledge graph, and produces structured intelligence assessments with confidence scoring, alternative hypotheses, and future scenario projections. It features recursive graph expansion driven by investigation goals and a comprehensive evaluation framework.

---

## Technology Stack

### Backend (Python)
- **Framework:** FastAPI (with CORS middleware)
- **ORM:** SQLAlchemy (declarative models)
- **Database:** PostgreSQL (local via `.env`, Supabase-compatible)
- **Config:** Pydantic Settings (`.env` file)
- **RSS Parsing:** feedparser
- **Server:** uvicorn[standard]
- **Auth:** API key header verification
- **LLM Layer (optional):** Qwen2.5-7B via Google Colab tunnel (httpx), default deterministic

### Frontend (JavaScript/React)
- **Framework:** React 19
- **Build Tool:** Vite 8
- **UI:** Tailwind CSS 4
- **Graph Visualization:** React Flow (reactflow 11)
- **HTTP Client:** Axios
- **Linting:** ESLint 9

---

## Project Structure

```
deepdive-intelligence/
├── main.py                        # Entry: re-exports FastAPI app
├── requirements.txt               # Python dependencies
├── .env.example                   # Environment config template
├── README.md                      # Setup docs
├── Qwen_Server.ipynb              # Google Colab notebook for LLM augmentation
│
├── api/                           # FastAPI application
│   ├── main.py                    # App factory, middleware, router registration
│   ├── auth.py                    # API key verification dependency
│   ├── deps.py                    # DB session dependency
│   └── routers/                   # 8 router modules
│       ├── expansion.py           # Expansion cycle, lead queue, graph tree, dashboard
│       ├── goals.py               # CRUD for investigation goals
│       ├── health.py              # Health check endpoint
│       ├── intelligence.py        # Event search, timeline, impact, signals, pipeline
│       ├── research.py            # On-demand node research
│       ├── evaluation.py          # Evaluation snapshots, system health dashboard
│       ├── assessment.py          # Intelligence assessment CRUD, publish
│       └── validation.py          # Validation dashboard, readiness
│
├── database/                      # DB configuration
│   ├── config.py                  # Settings (DATABASE_URL or component fields)
│   ├── session.py                 # SessionLocal, engine, create_tables
│   └── base.py                    # SQLAlchemy declarative Base
│
├── models/                        # SQLAlchemy ORM models
│   ├── article.py                 # Simple Article model (legacy)
│   └── news_intelligence.py       # 20+ tables (see schema section below)
│
├── pipeline/                      # Orchestration pipeline
│   ├── main_pipeline.py           # 8-step deterministic pipeline runner
│   └── validation.py              # Consistency validation checks
│
├── ingestion/                     # Raw source ingestion
│   ├── rss.py                     # RSS feed fetcher
│   └── service.py                 # Raw news insertion with dedup
│
├── preprocessing/                 # Text cleaning
│   └── service.py                 # Clean, normalize, detect language
│
├── clustering/                    # Rule-based grouping
│   └── service.py                 # Token-based Jaccard clustering
│
├── timeline/                      # Chronological ordering
│   └── service.py                 # Position-indexed timeline per cluster
│
├── expansion/                     # Recursive expansion system
│   ├── service.py                 # BFS expansion from timeline nodes
│   ├── recursive_expander.py      # Orchestrator: leads -> novelty gate -> create/enhance/link/merge
│   ├── prioritization.py          # Dynamic score recomputation, top-lead selection
│   ├── novelty.py                 # Knowledge novelty engine (Jaccard trigram)
│   ├── goals.py                   # Investigation goal engine (750 lines)
│   ├── scoring.py                 # Importance scoring, candidate scoring, confidence decay
│   ├── assessment.py              # Intelligence assessment synthesis engine
│   └── research.py                # 3-gate research filter (entity, context, time)
│
├── research/                      # Node research engine
│   ├── engine.py                  # Orchestrator: gather -> synthesize -> persist -> push leads
│   ├── gather.py                  # 5-pillar data gathering
│   ├── synthesis.py               # Profile synthesis, investigation lead generation
│   └── typing.py                  # Candidate generation from text
│
├── impact/                        # Impact analysis
│   └── service.py                 # Rule-based short/long-term winner/loser detection
│
├── signal_detection/              # Early-warning signal extraction
│   └── service.py                 # Keyword-driven signal detection
│
├── evaluation/                    # Quality evaluation framework
│   ├── dashboard.py               # Evaluation snapshot creation, health dashboard
│   ├── metrics.py                 # Expansion, knowledge, reuse, efficiency metrics
│   ├── entity_quality.py          # Entity quality evaluation
│   ├── goal_quality.py            # Goal quality evaluation
│   ├── scenario_quality.py        # Scenario quality evaluation
│   ├── explanation_quality.py     # Explanation quality evaluation
│   ├── failures.py                # Failure analysis & classification
│   ├── readiness.py               # System Readiness Score (SRS) computation
│   ├── benchmark_runner.py        # Benchmark scenario executor
│   ├── benchmarks.py              # Benchmark scenario models
│
├── services/
│   └── llm_service.py             # LLM augmentation layer (disabled | colab | local)
│
├── utils/                         # Shared utilities
│   └── datetime_helpers.py        # UTC timezone utilities
│
├── frontend/                      # React SPA
│   ├── package.json               # React 19, Vite 8, Tailwind 4, React Flow
│   ├── vite.config.js             # Proxy /api -> localhost:8000
│   ├── index.html                 # Entry HTML
│   └── src/
│       ├── main.jsx               # React root
│       ├── App.jsx                # Main app: workspace + validation views
│       ├── api.js                 # Axios API client (22 endpoints)
│       ├── index.css              # Tailwind imports
│       └── components/            # 16 React components
│           ├── SearchBar.jsx      # Event search
│           ├── EventCard.jsx      # Event result card
│           ├── IntelligenceAssessmentCard.jsx
│           ├── EvidencePanel.jsx
│           ├── GapPanel.jsx
│           ├── ScenarioPanel.jsx
│           ├── GoalPanel.jsx
│           ├── ResearchPanel.jsx
│           ├── AlternativeExplanations.jsx
│           ├── EvaluationPanel.jsx
│           ├── GraphPanel.jsx     # React Flow graph visualization
│           ├── ValidationDashboard.jsx  # System readiness UI
│           ├── TimelineView.jsx
│           ├── ImpactView.jsx
│           ├── SignalView.jsx
│           └── MetadataPanel.jsx

├── intelligence.db                # SQLite database files
├── news_intelligence.db
├── batch_results.md               # Batch processing results
└── implementation_recommendations.md
```

---

## Database Schema (22+ Tables)

Core tables in `models/news_intelligence.py`:

| Table | Purpose |
|-------|---------|
| `raw_news` | Ingested RSS articles (unique_id, title, content, source, url, published_at) |
| `cleaned_news` | Preprocessed/normalized text per raw article |
| `event_clusters` | Rule-based clusters (cluster_key, main_topic) |
| `cluster_news_map` | M:N mapping of cleaned_news <-> event_clusters |
| `nodes` | Knowledge graph nodes (entity, event_type, expansion_depth, importance, confidence, parent FK) |
| `edges` | Directed causal edges between nodes (relation_type, confidence) |
| `timeline` | Chronological timeline entries (position_index, timeline_group_id) |
| `impact` | Impact analysis (short/long-term winners/losers as JSON) |
| `signals` | Early-warning signal detections (signal_type, phrase, entity, source_count) |
| `node_research_log` | Audit trail for each research attempt on a node |
| `node_research_profile` | 1:1 profile with comprehensive research JSON blob |
| `lead_queue` | Central expansion queue (entity, score_profile, base_score, dynamic_score, status) |
| `investigation_goals` | Hierarchical investigation goals (goal_question, keywords, budget, status) |
| `evaluation_snapshots` | Point-in-time system metrics (30+ metric columns) |
| `goal_evaluations` | Per-goal evaluation records (completion, coverage, efficiency, etc.) |
| `benchmark_scenarios` | Reusable investigation scenarios for benchmarking |
| `benchmark_results` | Links benchmark runs to evaluation snapshots |
| `intelligence_assessments` | Structured intelligence reports (evidence, gaps, scenarios, summary) |
| `assessment_quality_metrics` | Quality tracking for assessments (evidence_strength, causal_consistency, etc.) |
| `human_feedback` | Analyst feedback on assessments (usefulness, correctness, confidence, explanation) |
| `failure_reports` | Failure analysis reports per assessment |
| `system_readiness` | System Readiness Score history (entity/assessment/explanation/scenario/goal quality) |
| `llm_assessments` | LLM augmentation audit trail (prompt, response, model, latency, tokens) |
| `validation_snapshots` | Validation check history |

---

## 8-Step Deterministic Pipeline

Defined in `pipeline/main_pipeline.py`:

1. **Ingestion** — Fetch RSS feeds, insert raw news with duplicate detection
2. **Preprocessing** — Clean HTML, normalize text, detect language
3. **Clustering** — Token-based Jaccard similarity grouping
4. **Timeline** — Chronological position indexing per cluster
5. **Expansion** — BFS expansion from timeline nodes (entity overlap + context similarity + time proximity gates)
6. **Impact Analysis** — Rule-based short/long-term winner/loser detection
7. **Signal Detection** — Keyword-driven early-warning signal extraction
8. **Validation** — Consistency checks across all tables

---

## Recursive Graph Expansion System

The core intelligence mechanism goes beyond the linear pipeline:

### Lead Prioritization Engine (`expansion/prioritization.py`)
- Recomputes `dynamic_score` for pending leads using formula: `base_score + novelty_bonus + context_bonus - loop_penalty + goal_relevance + contribution + gap_closure`
- Selects top leads above threshold (0.90), capped at 3 per source node

### Knowledge Novelty Engine (`expansion/novelty.py`)
- Computes Jaccard trigram similarity between lead entity and existing nodes
- Maps novelty score to decisions: MERGE (<0.20), ENHANCE (<0.40), LINK (<0.65), CREATE (>=0.65)
- Loop prevention via lineage traversal (up to depth 5)

### Investigation Goal Engine (`expansion/goals.py`, 750 lines)
- **Intent Classification:** Syntactic prefix + lexical keyword scoring → 8 intent types (ROOT_CAUSE, ECONOMIC_DRIVER, POLICY_DRIVER, GEOPOLITICAL_DRIVER, ACTOR_MOTIVATION, FUTURE_CONSEQUENCES, RISK_ANALYSIS, OPPORTUNITY_ANALYSIS)
- **Goal Relevance:** Keyword overlap + type alignment + evidence proximity
- **Completion Scoring:** 6-dimension weighted composite (evidence, coverage, connections, signals, impacts, causal depth)
- **Stopping Logic:** CONTINUE / PAUSED / COMPLETED / ABANDONED based on score, budget, and stall detection
- **Sub-Goal Generation:** Automatic sub-goal creation from research profile
- **Knowledge Coverage & Gap Analysis:** Required category tracking, missing pillar detection, causal gap identification

### Recursive Expander (`expansion/recursive_expander.py`)
- One expansion cycle: select leads → novelty gate → MERGE/ENHANCE/LINK/CREATE decisions → Node Research Engine → goal state evaluation → evaluation snapshot

### Node Research Engine (`research/engine.py`)
- Gathers 5 pillars: Source Material, Causal Context, Consequence Profiling, Early-Warning Signals, Chronological Context
- Synthesizes research profile with typed investigation leads
- Pushes leads to LeadQueue for next expansion cycle
- Generates sub-goals

### Research Module (`expansion/research.py`)
- 3-gate filter: entity overlap (Jaccard), context similarity (SequenceMatcher), temporal proximity
- Scores qualified candidates → creates NodeResearchLog entries

---

## Intelligence Assessment Engine

Defined in `expansion/assessment.py` (483 lines):

- **Evidence Strength Synthesis:** Weighted composite of node confidence (30%), edge confidence (25%), goal coverage (20%), impact sectors (15%), signals (10%)
- **Confidence Calculation:** 5 dimensions — evidence strength (25%), source diversity (25%), causal consistency (20%), knowledge coverage (15%), signal agreement (15%) → mapped to HIGH / MEDIUM / LOW
- **Alternative Explanations:** Category-ranked alternative hypotheses
- **Knowledge Gaps:** Critical / Moderate / Minor classification
- **Future Scenarios:** Signal-weighted likely/possible/unlikely scenario generation
- **Executive Summary:** Key findings, risks, opportunities, unknowns
- **Quality Tracking:** AssessmentQualityMetric per version (evidence_strength, causal_consistency, completeness, stability)
- **Failure Analysis:** Entity, goal, scenario, and explanation quality validation + FailureReport

---

## Evaluation Framework (6 Pillars)

Defined across `evaluation/` module:

1. **Entity Quality** — Quality of extracted entities
2. **Goal Quality** — Quality of goal questions
3. **Scenario Quality** — Quality of generated scenarios
4. **Explanation Quality** — Quality of explanations (causal depth, evidence, gaps)
5. **Assessment Quality** — Accuracy and completeness of intelligence assessments
6. **System Readiness Score (SRS)** — Weighted composite (0-100) with classification: EXPERIMENTAL / LEARNING / STABLE / PRODUCTION_READY

### Dashboard Metrics
- **Knowledge Health:** Total nodes/edges, unique/linked concepts, knowledge density, compression ratio
- **System Health Dashboard:** 30+ metrics across goals, expansion, knowledge, reuse, efficiency, learning index
- **Trend Analysis:** Completion, density, reuse, efficiency trends over time
- **Benchmarking:** Reusable scenarios for version-to-version comparison

---

## LLM Augmentation Layer

Defined in `services/llm_service.py`:

- Three modes: `disabled` (deterministic-only, default), `colab` (Qwen2.5-7B via tunnel), `local` (future)
- Colab notebook `Qwen_Server.ipynb` serves Qwen model via FastAPI
- Augments: assessment text, scenarios, alternatives, executive summaries
- Falls back to deterministic on failure

---

## Frontend (React 19 + React Flow)

Single-page application with:

- **Workspace View** — 3-column layout: events/goals (left), assessment/evidence/graph (center), gaps/scenarios/alternatives (right)
- **Validation View** — System readiness dashboard
- **Features:** Event search with relevance ranking, investigation goal management, intelligence assessment display with evidence/gaps/scenarios, research panel showing lead queue, React Flow graph visualization, system health evaluation panel
- **API Client:** 22 endpoint wrappers via Axios

---

## API Endpoints (8 Routers, ~25+ Endpoints)

### Health
- `GET /health`

### Intelligence
- `GET /event?query=&limit=` — Search events with relevance ranking
- `GET /timeline/{id}` — Timeline with causal connections
- `GET /impact/{id}` — Structured impact analysis
- `GET /signals/{id}` — Early-warning signals
- `POST /pipeline/run` — Trigger pipeline (API key protected)
- `GET /pipeline/status` — Pipeline status
- `GET /pipeline/validate` — Run validation checks

### Expansion
- `POST /expansion/cycle` — Trigger expansion cycle
- `GET /expansion/queue?status=` — Lead queue
- `GET /expansion/dashboard` — Knowledge health dashboard
- `GET /graph/{node_id}?depth=` — Expansion tree

### Research
- `POST /research/{node_id}` — Trigger node research
- `GET /node/{node_id}/children` — Node children
- `GET /node/{node_id}/research` — Research history

### Goals
- `GET /goals` — List goals
- `GET /goals/{goal_id}` — Goal details
- `POST /goals` — Create goal
- `POST /goals/{goal_id}/assessments` — Generate assessment
- `GET /goals/{goal_id}/assessments/latest` — Latest assessment
- `GET /goals/{goal_id}/assessments/llm` — LLM-enhanced assessment

### Assessment
- `GET /assessments/{assessment_id}` — Get assessment
- `POST /assessments/{assessment_id}/publish` — Publish assessment

### Evaluation
- `GET /evaluation/status` — System health dashboard
- `POST /evaluation/snapshot` — Create snapshot
- `GET /evaluation/snapshots` — List snapshots

### Validation
- `GET /validation/dashboard` — Validation dashboard
- `GET /validation/readiness` — System readiness score

---

## Git History (27 commits, main branch)

Key commit milestones:
- Initial deterministic pipeline setup with ingestion, preprocessing, clustering
- Rule-based entity extraction with normalization and priority ranking
- Multi-node implicit causal reasoning engine
- Recursive graph expansion and goal intent engine
- Intelligence Assessment Engine and System Evaluation Framework
- React SPA with React Flow graph visualization
- Real-World Intelligence Validation Framework
- LLM Augmentation Layer with Qwen Colab integration
- Current state: Refactored LLM service with improved Colab integration

---

## Design Philosophy

The entire system is **deterministic and rule-based by design** — no LLM dependencies are used for core intelligence operations. All modules implement explicit algorithms with clear configurable thresholds. The LLM layer is an optional augmentation overlay for enhanced natural language output.

Key principles:
- No neural network or ML dependencies in core pipeline
- All thresholds and weights are configurable constants
- Complete audit trail via NodeResearchLog, EvaluationSnapshots, FailureReports
- Hierarchical investigation goals drive recursive graph expansion
- Knowledge quality is continuously evaluated across 6+ dimensions
- System readiness is quantified via the SRS framework
