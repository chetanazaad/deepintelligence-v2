# News Intelligence Backend

Deterministic, rule-based Python backend for ingesting and analyzing news signals, with optional LLM augmentation via local Ollama.

## Tech Stack

- FastAPI
- SQLAlchemy ORM
- PostgreSQL / SQLite
- Ollama + Qwen2.5:3b (optional LLM augmentation)

## Project Structure

- `ingestion/` - raw source normalization
- `preprocessing/` - text cleaning and normalization
- `clustering/` - rule-based grouping logic
- `timeline/` - chronological ordering
- `expansion/` - deterministic keyword expansion and assessment engine
- `impact/` - rule-based impact scoring
- `signal_detection/` - keyword-driven signal extraction
- `evaluation/` - quality metrics and validation framework
- `services/` - unified LLM intelligence generation engine
- `api/` - FastAPI app and routers
- `database/` - settings, engine, and session setup
- `models/` - SQLAlchemy models
- `utils/` - shared deterministic utilities
- `tests/` - integration tests

## Setup

1. Create virtual environment:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate    # Windows PowerShell
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Configure environment:
   ```bash
   copy .env.example .env
   ```
   Update DB values and LLM settings as needed.

4. Run API:
   ```bash
   uvicorn api.main:app --reload
   ```

## LLM Augmentation (Optional)

The deterministic intelligence pipeline is the primary analysis engine. The LLM layer is an **optional augmentation** that enhances natural-language synthesis of assessments, scenarios, alternatives, and summaries.

### Unified Intelligence Engine

The LLM service uses a **single unified call** (`generate_intelligence_package()`) instead of multiple independent calls, producing a complete intelligence package in one pass:

```
Evidence + Signals + Impacts + Goal
         ↓
   Single Ollama Call (~12s)
         ↓
   Validated JSON Package
```

**Output schema:**
```json
{
    "executive_summary": "",
    "assessment": "",
    "confidence": "",
    "risks": [],
    "opportunities": [],
    "alternative_explanations": [],
    "future_scenarios": [],
    "knowledge_gaps": [],
    "key_entities": [],
    "recommendations": []
}
```

### Prompt Cache

Identical evidence submissions are automatically cached using SHA-256 prompt hashing. Cached responses return instantly without hitting Ollama.

### Setup Ollama

1. **Install Ollama**:
   - Download from [ollama.com](https://ollama.com/) or run:
     ```bash
     winget install Ollama.Ollama
     ```

2. **Pull the model**:
   ```bash
   ollama pull qwen2.5:3b
   ```

3. **Verify Ollama is running**:
   ```bash
   curl http://localhost:11434/api/tags
   ```

### Configure LLM Mode

In your `.env` file:

```env
# Set to "local" to enable Ollama augmentation, "disabled" to use deterministic only
LLM_SERVICE_MODE=local
OLLAMA_MODEL=qwen2.5:3b
OLLAMA_URL=http://localhost:11434/api/generate
OLLAMA_TIMEOUT=120
```

| Mode       | Behavior                                              |
|------------|-------------------------------------------------------|
| `disabled` | LLM bypassed entirely, deterministic output only      |
| `local`    | Augments output via local Ollama + Qwen2.5:3b         |

### Run LLM Tests

```bash
python tests/test_ollama.py
```

### Fallback Behavior

If the LLM is unavailable (Ollama not running, timeout, or malformed response), the system **automatically falls back** to the deterministic output. The pipeline never crashes due to an LLM failure.

## Notes

- The deterministic intelligence system is the primary engine.
- The LLM acts only as an augmentation layer for natural-language synthesis.
- No external APIs, no cloud inference, no LangChain.
