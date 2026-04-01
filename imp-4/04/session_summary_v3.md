# DeepDive Intelligence: Project Summary & Status (2026-04-01) - Causal Engine

This session marked a massive architectural shift for DeepDive Intelligence, evolving it from a keyword-based topical news aggregator into a **Multi-Node Implicit Causal Reasoning Engine**.

---

## 1. Key Accomplishments: The Causal Paradigm Shift

### A. Atomic Event Logic (Nodes)
*   **Farewell Article Summaries:** We deprecated the naive approach of combining titles (`Title 1 | Title 2`).
*   **Structural Parsing:** Implemented `_extract_causal_primitives()` in `timeline/service.py` which actively breaks down raw news strings via rules (e.g. `due to`, `sparked by`, `after`, `leads to`).
*   **Primitives Extracted:** `event`, `actor/entity`, `trigger_phrase`, and `predecessor`.
*   **Debug Constraints:** The Node's `description` field is now used to permanently imprint the exact causal logic, confidence interval, and raw quote (Evidence) that justifies its existence on the graph.

### B. Explicit Backward Expansion (Edges)
*   **Explicit Edge Verification:** If an article tells us *Event B* happened because of *Event A*, the system isolates the entity for *A*, looks for an older Node matching *A* on the timeline, and explicitly draws a `causes` edge with extremely high confidence.

### C. Multi-Hop Implicit Inference (The Brain)
*   Instead of giving up when no explicit "due to" phrase is found, the system now runs an implicit evaluation loop (`_compute_edge_score`) over older timeline nodes.
*   **Multi-Signal Evaluation:** It evaluates keyword alignment (e.g. Action vs Reaction verbs), exponential temporal decay (`gap_days < 30`), and entity set overlaps (`Jaccard Similarity`).
*   **Dynamic Predecessor Injection:** If confidence is robust (`>0.45%), it replaces a missing `PREDECESSOR: N/A` tag with `[INFERRED] <Older Event Name>` directly in the downstream node's memory, ensuring a continuous A → B → C pipeline that surfaces hidden associations.
*   **Harsh Penalty System:** Non-causal keywords / random topic coverage nodes that don't pass the minimum implicit causality thresholds are dropped, drastically reducing graph noise.

---

## 2. Technical Context
*   **Modified Service:** `timeline/service.py` handling all NLP rule-based intelligence.
*   **Execution Rule:** 100% deterministic mathematical execution. No LLM non-determinism, no hallucinations. 
*   **Version Control:** Committed to `main` via `ac2088c` and `507edb7`.

---

## 3. Current State & Validation
*   **System Status:** **Fully Operational.** The pipeline correctly drops non-causal nodes, draws explicit associations based on journalistic grammar, and builds long-term multi-node bridges using semantic decay.
*   **UI Status:** Perfectly backwards compatible with existing frontend React architectures. Graph explains itself visually.

---

## 4. Next Steps & Weaknesses
*   **Coreference Challenge:** We still rely on strict keyword arrays. If the raw string resolves an entity using pronouns (*"It triggered an explosion"*), the causal chain breaks because it cannot link "It" to the actual predecessor namespace. LLM coreference resolution prior to parsing would solve this.
*   **Node Synthesis:** A single paragraph containing both a cause and an effect only generates *one* UI Node. Ideally, `timeline/service.py` should be upgraded to instantiate *Virtual Nodes* allowing independent root causes to exist visually without waiting for prior articles.
*   **Hosting Deployment:** Vercel (Frontend), Render (FastAPI), with PostgreSQL integration.

---

## 5. Running the Engine
*   **Backend:** `cd d:\deepdive-intelligence && .venv\Scripts\python.exe -m uvicorn main:app --reload --port 8000`
*   **Frontend:** `cd d:\deepdive-intelligence\frontend && npm run dev`
*   **Execute Pipeline Batch:**
    ```powershell
    Invoke-WebRequest -Uri "http://localhost:8000/pipeline/run" -Method POST -Headers @{"X-API-Key"="dev-test-key-12345"} -UseBasicParsing
    ```
