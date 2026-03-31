# Implementation Recommendations

> **Project:** DeepDive Intelligence — News Intelligence Backend  
> **Generated:** 2026-03-31  
> **Total Issues Found:** 28  
> **Breakdown:** 🔴 Critical: 5 | 🟡 Major: 10 | 🟢 Minor: 13

---

## Table of Contents

1. [Critical Issues (Fix Immediately)](#1-critical-issues)
2. [Major Issues (Fix This Sprint)](#2-major-issues)
3. [Minor Issues (Fix When Possible)](#3-minor-issues)
4. [Implementation Priority Order](#4-implementation-priority-order)

---

## 1. Critical Issues

---

### 🔴 ISSUE-001: No Version Control (Git)

**Location:** Project Root  
**Risk:** Complete code loss on any mistake, no rollback capability  

**Fix:**

```bash
cd d:\deepdive-intelligence
git init
git add .
git commit -m "initial commit: deterministic news intelligence backend"
```

Also update `.gitignore` to include additional patterns:

```gitignore
# Add to .gitignore
.venv/
__pycache__/
*.pyc
.env
*.egg-info/
dist/
build/
.pytest_cache/
.mypy_cache/
*.db
```

---

### 🔴 ISSUE-002: No Authentication on API

**Location:** `api/main.py`, `api/routers/intelligence.py`  
**Risk:** Anyone can trigger `/pipeline/run` and access all data endpoints  

**Fix — Add API Key Authentication:**

Create `api/auth.py`:

```python
from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader

from database.config import get_settings

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: str = Security(API_KEY_HEADER)) -> str:
    settings = get_settings()
    if not api_key or api_key != settings.api_key:
        raise HTTPException(status_code=403, detail="Invalid or missing API key.")
    return api_key
```

Add to `database/config.py` Settings class:

```python
api_key: str = Field(default="change-me-in-production", alias="API_KEY")
```

Add to `.env.example`:

```
API_KEY=your-secret-api-key-here
```

Apply to protected routes in `api/routers/intelligence.py`:

```python
from api.auth import verify_api_key

@router.post("/pipeline/run", dependencies=[Depends(verify_api_key)])
def run_pipeline() -> dict[str, object]:
    ...
```

---

### 🔴 ISSUE-003: Synchronous Pipeline Execution Blocks API

**Location:** `api/routers/intelligence.py` → `run_pipeline()`  
**Risk:** Long RSS fetches + 7-step processing will timeout HTTP requests, block the server  

**Fix — Use FastAPI BackgroundTasks:**

```python
# api/routers/intelligence.py

from fastapi import BackgroundTasks

# Module-level status tracking (replace with Redis/DB in production)
_pipeline_status: dict[str, object] = {"state": "idle", "last_result": None}


def _run_pipeline_background() -> None:
    global _pipeline_status
    _pipeline_status = {"state": "running", "last_result": None}
    try:
        result = run_full_pipeline()
        _pipeline_status = {"state": "completed", "last_result": result}
    except Exception as exc:
        _pipeline_status = {"state": "failed", "last_result": str(exc)}


@router.post("/pipeline/run")
def trigger_pipeline(background_tasks: BackgroundTasks) -> dict[str, object]:
    if _pipeline_status["state"] == "running":
        return {"message": "Pipeline is already running.", "status": _pipeline_status}
    background_tasks.add_task(_run_pipeline_background)
    return {"message": "Pipeline started in background."}


@router.get("/pipeline/status")
def pipeline_status() -> dict[str, object]:
    return {"status": _pipeline_status}
```

---

### 🔴 ISSUE-004: No Database Migrations

**Location:** `database/session.py` → `create_tables()`  
**Risk:** Any model change (add/rename/drop column) requires dropping tables = data loss  

**Fix — Add Alembic:**

```bash
pip install alembic
cd d:\deepdive-intelligence
alembic init alembic
```

Edit `alembic/env.py`:

```python
from database.base import Base
from database.config import get_settings
import models  # Force model registration

settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.sqlalchemy_database_uri)
target_metadata = Base.metadata
```

Edit `alembic.ini` — remove the default `sqlalchemy.url` line (it's set in `env.py`).

Generate first migration:

```bash
alembic revision --autogenerate -m "initial schema"
alembic upgrade head
```

Then remove `create_tables()` call from `api/main.py` startup:

```python
# REMOVE this:
# @app.on_event("startup")
# def on_startup() -> None:
#     create_tables()
```

Add to `requirements.txt`:

```
alembic
```

---

### 🔴 ISSUE-005: No Tests

**Location:** Project-wide  
**Risk:** Zero regression safety; any code change can silently break the pipeline  

**Fix — Add pytest with test structure:**

```bash
pip install pytest pytest-cov httpx
```

Create test directory structure:

```
tests/
├── __init__.py
├── conftest.py
├── test_ingestion.py
├── test_preprocessing.py
├── test_clustering.py
├── test_timeline.py
├── test_expansion.py
├── test_impact.py
├── test_signal_detection.py
└── test_api.py
```

Create `tests/conftest.py`:

```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from database.base import Base
import models  # noqa: F401


@pytest.fixture
def db_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine)
    session = TestSession()
    yield session
    session.close()
```

Example `tests/test_preprocessing.py`:

```python
from preprocessing.service import clean_text, normalize_text, infer_language, is_fuzzy_duplicate


def test_clean_text_strips_html():
    assert clean_text("<p>Hello <b>World</b></p>") == "Hello World"


def test_clean_text_removes_special_chars():
    assert clean_text("Hello@#$World") == "Hello World"


def test_normalize_text_lowercases():
    assert normalize_text("Hello World") == "hello world"


def test_infer_language_english():
    assert infer_language("This is an English sentence.") == "en"


def test_infer_language_unknown_on_empty():
    assert infer_language("") == "unknown"


def test_fuzzy_duplicate_detects_similar():
    existing = ["breaking news massive earthquake hits region"]
    assert is_fuzzy_duplicate("Breaking News: Massive Earthquake Hits Region", existing)


def test_fuzzy_duplicate_rejects_different():
    existing = ["stock market reaches all time high"]
    assert not is_fuzzy_duplicate("Weather forecast for next week", existing)
```

Add to `requirements.txt`:

```
pytest
pytest-cov
httpx
```

Run with:

```bash
pytest tests/ -v --cov=. --cov-report=term-missing
```

---

## 2. Major Issues

---

### 🟡 ISSUE-006: O(n²) Fuzzy Deduplication

**Location:** `preprocessing/service.py` → `is_fuzzy_duplicate()`  
**Risk:** Each new headline compared against ALL existing headlines; will not scale past ~5,000 items  

**Fix — Use MinHash for approximate dedup:**

```bash
pip install datasketch
```

```python
# preprocessing/service.py — replace is_fuzzy_duplicate

from datasketch import MinHash, MinHashLSH

_LSH = MinHashLSH(threshold=0.92, num_perm=128)
_LSH_COUNTER = 0


def _text_to_minhash(text: str) -> MinHash:
    m = MinHash(num_perm=128)
    tokens = normalize_text(clean_text(text)).split()
    for token in tokens:
        m.update(token.encode("utf-8"))
    return m


def is_fuzzy_duplicate_fast(headline: str, headline_id: str) -> bool:
    mh = _text_to_minhash(headline)
    result = _LSH.query(mh)
    if result:
        return True
    _LSH.insert(headline_id, mh)
    return False
```

**Complexity:** O(1) per query instead of O(n).

---

### 🟡 ISSUE-007: Unpinned Dependencies

**Location:** `requirements.txt`  
**Risk:** Different installs produce different environments; builds are non-reproducible  

**Fix:**

```bash
pip freeze > requirements.lock
```

Update `requirements.txt` with pinned versions (example):

```
fastapi==0.115.0
uvicorn[standard]==0.32.0
SQLAlchemy==2.0.36
psycopg2-binary==2.9.10
pydantic-settings==2.7.0
python-dotenv==1.0.1
feedparser==6.0.11
```

Also consider switching to `pyproject.toml` for modern Python packaging.

---

### 🟡 ISSUE-008: No CORS Middleware

**Location:** `api/main.py`  
**Risk:** Any frontend trying to call this API from a browser will be blocked  

**Fix — Add 3 lines to `api/main.py`:**

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

For production, replace `allow_origins=["*"]` with specific domains and add to Settings:

```python
cors_origins: str = Field(default="*", alias="CORS_ORIGINS")
```

---

### 🟡 ISSUE-009: Impact & Signals Re-process ALL Nodes Every Run

**Location:** `impact/service.py` → `analyze_impact()`, `signal_detection/service.py` → `detect_and_store_signals()`  
**Risk:** Wasted computation, potential data overwrites, O(n) growth per pipeline run  

**Fix — Add incremental processing filter:**

In `impact/service.py`:

```python
# Replace the current query with:
from models.news_intelligence import Impact

rows = (
    db.execute(
        select(Node)
        .outerjoin(Impact, Impact.node_id == Node.id)
        .where(Impact.id.is_(None))  # Only unanalyzed nodes
        .order_by(Node.created_at.asc(), Node.id.asc())
        .limit(limit)
    )
    .scalars()
    .all()
)
```

In `signal_detection/service.py`:

```python
# Replace the current query with:
from models.news_intelligence import Signal

nodes = (
    db.execute(
        select(Node)
        .outerjoin(Signal, Signal.node_id == Node.id)
        .where(Signal.id.is_(None))  # Only nodes without signals
        .order_by(Node.created_at.asc(), Node.id.asc())
        .limit(limit)
    )
    .scalars()
    .all()
)
```

---

### 🟡 ISSUE-010: Deprecated `datetime.utcnow` Usage

**Location:** `models/article.py`, `models/news_intelligence.py` (8 occurrences)  
**Risk:** `datetime.utcnow` is deprecated since Python 3.12 and will be removed  

**Fix — Global find & replace across all model files:**

```python
# BEFORE (deprecated):
default=datetime.utcnow

# AFTER (correct):
from datetime import datetime, timezone

default=lambda: datetime.now(timezone.utc)
```

**Files to update:**
- `models/article.py` (line 17)
- `models/news_intelligence.py` (lines 36, 57, 76, 120, 155, 174, 193, 215)

---

### 🟡 ISSUE-011: Deprecated FastAPI Startup Event

**Location:** `api/main.py` (line 14)  
**Risk:** `@app.on_event("startup")` is deprecated in favor of `lifespan`  

**Fix:**

```python
# api/main.py — BEFORE:
@app.on_event("startup")
def on_startup() -> None:
    create_tables()

# AFTER:
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    create_tables()
    yield

app = FastAPI(
    title=settings.app_name,
    debug=settings.app_debug,
    lifespan=lifespan,
)
```

---

### 🟡 ISSUE-012: No Pagination on `/event` Endpoint

**Location:** `api/routers/intelligence.py` → `get_event()`  
**Risk:** Hardcoded `limit=20` with no offset; clients can't page through results  

**Fix:**

```python
@router.get("/event")
def get_event(
    query: str = Query(..., min_length=2, description="Search term"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Results per page"),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    pattern = f"%{query.strip()}%"
    offset = (page - 1) * page_size

    # Get total count
    from sqlalchemy import func
    total = db.scalar(
        select(func.count(Node.id)).where(
            or_(
                Node.entity.ilike(pattern),
                Node.event_type.ilike(pattern),
                Node.description.ilike(pattern),
            )
        )
    )

    nodes = (
        db.execute(
            select(Node)
            .where(or_(...))
            .order_by(Node.timestamp.desc(), Node.id.desc())
            .offset(offset)
            .limit(page_size)
        )
        .scalars()
        .all()
    )

    # ... build results ...

    return {
        "query": query,
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": (total + page_size - 1) // page_size,
        "count": len(results),
        "results": results,
    }
```

---

### 🟡 ISSUE-013: No RSS Feed Timeout / Error Handling

**Location:** `ingestion/rss.py` → `fetch_rss_feed()`  
**Risk:** Unresponsive feeds hang the entire pipeline indefinitely  

**Fix:**

```python
# ingestion/rss.py
import urllib.request
import socket

def fetch_rss_feed(feed_url: str, source: str, timeout: int = 15) -> list[dict[str, object]]:
    try:
        # feedparser doesn't natively support timeout, use urllib handler
        response = urllib.request.urlopen(feed_url, timeout=timeout)
        parsed = feedparser.parse(response.read())
    except (urllib.error.URLError, socket.timeout, Exception) as exc:
        # Log and return empty — don't crash the pipeline
        import logging
        logging.getLogger(__name__).warning("Failed to fetch %s: %s", feed_url, exc)
        return []

    items: list[dict[str, object]] = []
    # ... rest unchanged ...
```

---

### 🟡 ISSUE-014: N+1 Query Pattern in Timeline Builder

**Location:** `timeline/service.py` → `build_timeline()` (lines 174-181)  
**Risk:** Individual title query per cluster = N extra database round-trips  

**Fix — Batch titles query:**

```python
# timeline/service.py — replace per-cluster title queries with batch

from sqlalchemy import tuple_

# Collect all cluster IDs first
cluster_ids = [int(info["cluster_id"]) for info in cluster_stats]

# Batch query: get top 3 titles per cluster using window function
from sqlalchemy import func as sa_func
from sqlalchemy.sql import expression

title_rows = db.execute(
    select(
        ClusterNewsMap.cluster_id,
        RawNews.title,
    )
    .join(CleanedNews, CleanedNews.id == ClusterNewsMap.cleaned_news_id)
    .join(RawNews, RawNews.id == CleanedNews.raw_news_id)
    .where(ClusterNewsMap.cluster_id.in_(cluster_ids))
    .order_by(ClusterNewsMap.cluster_id, RawNews.created_at.desc())
).all()

# Group titles by cluster_id (keep max 3 per cluster)
from collections import defaultdict
titles_by_cluster: dict[int, list[str]] = defaultdict(list)
for row in title_rows:
    if len(titles_by_cluster[row[0]]) < 3:
        titles_by_cluster[row[0]].append(row[1])
```

---

### 🟡 ISSUE-015: No Pydantic Response Models

**Location:** `api/routers/intelligence.py`  
**Risk:** No API contract enforcement, no auto-documentation of response shapes  

**Fix — Create `api/schemas.py`:**

```python
from pydantic import BaseModel


class TimelineItem(BaseModel):
    position_index: int
    node_id: int
    entity: str
    event_type: str | None
    description: str | None
    timestamp: str | None
    is_anchor: bool


class TimelinePayload(BaseModel):
    timeline_group_id: str | None
    items: list[TimelineItem]
    explanation: str


class ImpactPayload(BaseModel):
    node_id: int
    available: bool
    short_term_winners: list[str] = []
    short_term_losers: list[str] = []
    long_term_winners: list[str] = []
    long_term_losers: list[str] = []
    confidence_score: float | None = None
    explanation: str


class SignalItem(BaseModel):
    id: int
    type: str
    phrase: str
    entity: str | None
    source_count: int | None
    time_span: str | None
    confidence_score: float | None
    note: str


class SignalsPayload(BaseModel):
    node_id: int
    count: int
    items: list[SignalItem]
    explanation: str


class EventResult(BaseModel):
    node_id: int
    entity: str
    event_type: str | None
    description: str | None
    timestamp: str | None
    timeline: TimelinePayload
    impact: ImpactPayload
    signals: SignalsPayload
    explanation: str


class EventSearchResponse(BaseModel):
    query: str
    count: int
    results: list[EventResult]
```

Then use in router:

```python
@router.get("/event", response_model=EventSearchResponse)
def get_event(...):
    ...
```

---

## 3. Minor Issues

---

### 🟢 ISSUE-016: Unused `Article` Model

**Location:** `models/article.py`  
**Risk:** Dead code, confusion for new developers  

**Fix:** Delete `models/article.py` and remove from `models/__init__.py`:

```python
# Remove this line from models/__init__.py:
from models.article import Article

# Remove from __all__:
"Article",
```

---

### 🟢 ISSUE-017: Unused `utils/rules.py`

**Location:** `utils/rules.py`  
**Risk:** Dead code  

**Fix:** Delete `utils/rules.py`. The `contains_any()` function is never imported anywhere.

---

### 🟢 ISSUE-018: `RSS_FEEDS` Missing from `.env.example`

**Location:** `.env.example`  
**Risk:** New developers won't know this config exists  

**Fix — Add to `.env.example`:**

```env
# Comma-separated RSS feed URLs
RSS_FEEDS=https://rss.nytimes.com/services/xml/rss/nyt/World.xml,https://feeds.bbci.co.uk/news/rss.xml
```

---

### 🟢 ISSUE-019: No `updated_at` Columns

**Location:** All models in `models/news_intelligence.py`  
**Risk:** No way to track when records were last modified  

**Fix — Add to all models that support upsert:**

```python
from sqlalchemy import DateTime, event
from datetime import datetime, timezone

# Add this column to: RawNews, CleanedNews, Node, Impact, Signal
updated_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True),
    default=lambda: datetime.now(timezone.utc),
    onupdate=lambda: datetime.now(timezone.utc),
    nullable=False,
)
```

---

### 🟢 ISSUE-020: Single Timeline Group Only

**Location:** `timeline/service.py`  
**Risk:** All clusters collapse into one timeline; can't track multiple independent stories  

**Fix (future enhancement):** Partition clusters into disconnected components before building timeline. Each component gets its own `timeline_group_id`.

---

### 🟢 ISSUE-021: Impact Default Fallback is Always "policy"

**Location:** `impact/service.py` → `classify_event_type()` (line 55)  
**Risk:** Events with no keyword matches are always classified as "policy"  

**Fix:**

```python
def classify_event_type(text: str) -> str:
    terms = _tokenize(text)
    scores = {
        event_type: len(terms.intersection(keywords))
        for event_type, keywords in _EVENT_TYPE_KEYWORDS.items()
    }
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    if not ranked or ranked[0][1] == 0:
        return "general"  # Changed from "policy"

# Also add "general" to _IMPACT_RULES:
_IMPACT_RULES["general"] = {
    "short_term_winners": ["diversified entities"],
    "short_term_losers": ["exposed entities"],
    "long_term_winners": ["adaptive organizations"],
    "long_term_losers": ["rigid structures"],
}
```

---

### 🟢 ISSUE-022: Signal Detection — "may" Matches "Mayor"

**Location:** `signal_detection/service.py` → `detect_phrases()`  
**Risk:** False positives — tokenized text loses word boundaries  

**Fix — Use word-boundary matching:**

```python
import re

def detect_phrases(text: str) -> list[str]:
    normalized = _normalize_text(text)
    matched = []
    for phrase in _DETECTION_PHRASES:
        # Word boundary check to avoid matching substrings
        pattern = r'\b' + re.escape(phrase) + r'\b'
        if re.search(pattern, normalized):
            matched.append(phrase)
    return sorted(set(matched))
```

---

### 🟢 ISSUE-023: Clustering `main_topic` is Not Meaningful

**Location:** `clustering/service.py` → `_choose_main_topic()` (line 80)  
**Risk:** Topic is just "first 3 sorted keywords" — e.g. `"abc bank crisis"` instead of real topic  

**Fix — Use TF-IDF inspired selection:**

```python
from collections import Counter

def _choose_main_topic(titles: list[str], keywords: set[str]) -> str:
    if not titles:
        return "general-event"
    
    # Use most frequent title words as topic
    all_words = []
    for title in titles:
        all_words.extend(w.lower() for w in title.split() if len(w) >= 3)
    
    counter = Counter(all_words)
    # Remove stopwords
    for sw in _STOPWORDS:
        counter.pop(sw, None)
    
    top_words = [word for word, _ in counter.most_common(3)]
    return " ".join(top_words) if top_words else "general-event"
```

---

### 🟢 ISSUE-024: `psycopg2-binary` Not Recommended for Production

**Location:** `requirements.txt`  
**Risk:** Binary wheel has known issues on some platforms  

**Fix for production:**

```
# Development:
psycopg2-binary

# Production:
psycopg2
```

Or migrate to the modern `psycopg` (v3):

```
psycopg[binary]
```

---

### 🟢 ISSUE-025: No Structured Logging

**Location:** `pipeline/main_pipeline.py`  
**Risk:** Logs are plain text, hard to parse in production monitoring  

**Fix — Add a logging config:**

Create `utils/logging_config.py`:

```python
import logging
import sys


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logging.basicConfig(level=level, handlers=[handler])
```

Call in `api/main.py` startup:

```python
from utils.logging_config import setup_logging
setup_logging()
```

---

### 🟢 ISSUE-026: Health Check Doesn't Verify DB

**Location:** `api/routers/health.py`  
**Risk:** Returns `ok` even if DB is unreachable  

**Fix:**

```python
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.deps import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check(db: Session = Depends(get_db)) -> dict[str, str]:
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}
    except Exception:
        return {"status": "degraded", "database": "unreachable"}
```

---

### 🟢 ISSUE-027: No Dockerfile

**Location:** Project Root  
**Risk:** No containerized deployment option  

**Fix — Create `Dockerfile`:**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Create `docker-compose.yml`:

```yaml
version: "3.9"
services:
  api:
    build: .
    ports:
      - "8000:8000"
    env_file: .env
    depends_on:
      - db

  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: news_intelligence
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

volumes:
  pgdata:
```

---

### 🟢 ISSUE-028: Expansion Edge Dedup Loads ALL Edges Into Memory

**Location:** `expansion/service.py` (line 125-128)  
**Risk:** Memory usage grows linearly with total edges; will crash on large datasets  

**Fix — Use DB-level existence check:**

```python
# Replace in-memory set with DB query
def _edge_exists(db: Session, from_id: int, to_id: int, relation: str) -> bool:
    return db.scalar(
        select(Edge.id).where(
            Edge.from_node_id == from_id,
            Edge.to_node_id == to_id,
            Edge.relation_type == relation,
        )
    ) is not None
```

Or for batch operations, load only edges for the relevant node IDs:

```python
relevant_node_ids = {n.id for n in seed_nodes}
existing_edges = {
    (r[0], r[1], r[2])
    for r in db.execute(
        select(Edge.from_node_id, Edge.to_node_id, Edge.relation_type)
        .where(Edge.from_node_id.in_(relevant_node_ids))
    ).all()
}
```

---

## 4. Implementation Priority Order

Execute in this order for maximum impact with minimum risk:

```
Week 1 — Foundation
├── ISSUE-001: git init                          [10 min]
├── ISSUE-007: Pin dependencies                  [30 min]
├── ISSUE-010: Fix datetime.utcnow               [30 min]
├── ISSUE-011: Fix deprecated startup event       [30 min]
├── ISSUE-016: Remove unused Article model        [10 min]
├── ISSUE-017: Remove unused utils/rules.py       [5 min]
├── ISSUE-018: Add RSS_FEEDS to .env.example      [5 min]
└── ISSUE-008: Add CORS middleware                [15 min]

Week 2 — Security & Reliability
├── ISSUE-002: Add API key authentication         [2 hrs]
├── ISSUE-003: Async pipeline execution           [3 hrs]
├── ISSUE-013: RSS feed timeout                   [1 hr]
├── ISSUE-026: DB-aware health check              [30 min]
└── ISSUE-025: Structured logging                 [1 hr]

Week 3 — Performance
├── ISSUE-009: Incremental impact/signal          [3 hrs]
├── ISSUE-006: MinHash fuzzy dedup                [4 hrs]
├── ISSUE-014: Batch timeline queries             [3 hrs]
├── ISSUE-028: Edge dedup optimization            [2 hrs]
└── ISSUE-012: Pagination                         [3 hrs]

Week 4 — Quality & Deployment
├── ISSUE-004: Alembic migrations                 [3 hrs]
├── ISSUE-005: Unit tests                         [2-3 days]
├── ISSUE-015: Pydantic response models           [4 hrs]
├── ISSUE-027: Dockerfile + docker-compose        [2 hrs]
└── ISSUE-019: Add updated_at columns             [1 hr]

Future — Enhancements
├── ISSUE-020: Multi-story timelines
├── ISSUE-021: Better impact fallback
├── ISSUE-022: Word-boundary signal matching
├── ISSUE-023: Meaningful cluster topics
└── ISSUE-024: psycopg2 → psycopg3
```

---

> **Total Estimated Effort:** ~6-8 working days for all 28 issues  
> **Quick Wins (< 2 hours total):** Issues 001, 007, 008, 010, 011, 016, 017, 018
