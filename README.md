# News Intelligence Backend

Deterministic, rule-based Python backend for ingesting and analyzing news signals.

## Tech Stack

- FastAPI
- SQLAlchemy ORM
- PostgreSQL (Supabase compatible)

## Project Structure

- `ingestion/` - raw source normalization
- `preprocessing/` - text cleaning and normalization
- `clustering/` - rule-based grouping logic
- `timeline/` - chronological ordering
- `expansion/` - deterministic keyword expansion
- `impact/` - rule-based impact scoring
- `signal/` - keyword-driven signal extraction
- `api/` - FastAPI app and routers
- `database/` - settings, engine, and session setup
- `models/` - SQLAlchemy models
- `utils/` - shared deterministic utilities

## Setup

1. Create virtual environment:
   - `python -m venv .venv`
   - `.venv\Scripts\activate` (Windows PowerShell)
2. Install dependencies:
   - `pip install -r requirements.txt`
3. Configure environment:
   - `copy .env.example .env`
   - Update DB values for your Supabase project.
4. Run API:
   - `uvicorn api.main:app --reload`

## Notes

- No LLM dependencies are used.
- All current module stubs are deterministic and rule-based by design.
