"""LLM Augmentation Service — Unified Intelligence Generation Engine.

Provides natural-language synthesis on top of the deterministic
intelligence pipeline using a locally-running Ollama instance
with Qwen2.5:3b.

Architecture
------------
A single ``generate_intelligence_package()`` call replaces four
independent LLM calls, cutting latency from ~33s to ~12s while
ensuring consistent reasoning across all output sections.

The four legacy functions (``generate_assessment``,
``generate_scenarios``, ``generate_alternatives``,
``generate_summary``) are preserved for backward compatibility
and internally delegate to the unified call.

Modes
-----
- ``disabled``  — bypass LLM entirely, return deterministic text as-is.
- ``local``     — call Ollama on localhost for augmented output.

Cache
-----
An optional SHA-256 prompt-hash cache avoids redundant Ollama calls
when identical evidence is submitted. Cache is stored in the same
SQLite database via the ``LLMCache`` model.
"""

import hashlib
import json
import os
import time
import logging
from datetime import datetime, timezone

import requests as _requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration (read once at import time)
# ---------------------------------------------------------------------------

LLM_SERVICE_MODE: str = os.getenv("LLM_SERVICE_MODE", "disabled")

OLLAMA_URL: str = os.getenv(
    "OLLAMA_URL",
    "http://localhost:11434/api/generate",
)
OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
OLLAMA_TIMEOUT: int = int(os.getenv("OLLAMA_TIMEOUT", "120"))

logger.info(
    "LLM service initialised  mode=%s  model=%s  url=%s  timeout=%ds",
    LLM_SERVICE_MODE,
    OLLAMA_MODEL,
    OLLAMA_URL,
    OLLAMA_TIMEOUT,
)

# ---------------------------------------------------------------------------
# Intelligence JSON schema — required keys and defaults
# ---------------------------------------------------------------------------

INTELLIGENCE_SCHEMA: dict[str, type] = {
    "executive_summary": str,
    "assessment": str,
    "confidence": str,
    "risks": list,
    "opportunities": list,
    "alternative_explanations": list,
    "future_scenarios": list,
    "knowledge_gaps": list,
    "key_entities": list,
    "recommendations": list,
}

_DEFAULTS: dict[str, str | list] = {
    "executive_summary": "insufficient evidence",
    "assessment": "insufficient evidence",
    "confidence": "unknown",
    "risks": [],
    "opportunities": [],
    "alternative_explanations": [],
    "future_scenarios": [],
    "knowledge_gaps": [],
    "key_entities": [],
    "recommendations": [],
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_deterministic_result(
    text: str,
    start_time: float,
    *,
    model: str = "deterministic",
    success: bool = True,
) -> dict:
    """Standard response envelope used by legacy public functions."""
    return {
        "text": text,
        "latency": round(time.time() - start_time, 3),
        "model": model,
        "input_tokens": 0,
        "output_tokens": 0,
        "success": success,
    }


def _ollama_generate(prompt: str) -> dict | None:
    """Send a prompt to local Ollama and return the parsed response.

    Returns ``None`` on any failure so that callers can fall back to
    deterministic output without additional try/except boilerplate.
    """
    try:
        response = _requests.post(
            OLLAMA_URL,
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
            },
            timeout=OLLAMA_TIMEOUT,
        )

        if response.status_code != 200:
            logger.warning(
                "Ollama returned HTTP %d: %s",
                response.status_code,
                response.text[:200],
            )
            return None

        data = response.json()
        raw_text = data.get("response", "")

        if not raw_text:
            logger.warning("Ollama returned an empty response body.")
            return None

        return {
            "text": raw_text,
            "eval_count": data.get("eval_count", 0),
            "prompt_eval_count": data.get("prompt_eval_count", 0),
        }

    except _requests.exceptions.ConnectionError:
        logger.warning(
            "Ollama connection failed — is Ollama running on %s?",
            OLLAMA_URL,
        )
    except _requests.exceptions.Timeout:
        logger.warning(
            "Ollama request timed out after %ds.", OLLAMA_TIMEOUT,
        )
    except _requests.exceptions.JSONDecodeError:
        logger.warning("Ollama returned a non-JSON response.")
    except Exception as exc:
        logger.warning("Unexpected Ollama error: %s", str(exc))

    return None


def _try_parse_json(text: str) -> dict | None:
    """Best-effort JSON extraction from LLM output.

    The model sometimes wraps JSON in markdown code fences — this
    helper strips those before parsing.
    """
    cleaned = text.strip()

    # Strip ```json ... ``` wrappers
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        lines = [
            line for line in lines
            if not line.strip().startswith("```")
        ]
        cleaned = "\n".join(lines).strip()

    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        return None


def _validate_intelligence_json(data: dict | None) -> dict:
    """Validate and repair an intelligence JSON response.

    Ensures all required keys exist with correct types. Missing or
    malformed fields are replaced with safe defaults.
    """
    if not isinstance(data, dict):
        return dict(_DEFAULTS)

    result = {}
    for key, expected_type in INTELLIGENCE_SCHEMA.items():
        value = data.get(key)

        if value is None or not isinstance(value, expected_type):
            # Attempt type coercion for common LLM mistakes
            if expected_type is list and isinstance(value, str):
                result[key] = [value] if value else []
            elif expected_type is str and isinstance(value, (list, dict)):
                result[key] = json.dumps(value)
            else:
                result[key] = _DEFAULTS[key]
        else:
            result[key] = value

    return result


def _build_intelligence_prompt(
    goal_question: str,
    deterministic_text: str,
    evidence: list | dict | None = None,
    gaps: list | dict | None = None,
    signals: list | None = None,
    impacts: list | None = None,
    confidence_score: float | None = None,
    confidence_level: str | None = None,
    scenarios: dict | None = None,
    alternatives: dict | None = None,
) -> str:
    """Construct the unified intelligence analyst prompt."""

    evidence_str = json.dumps(evidence or [], indent=2, default=str)
    gaps_str = json.dumps(gaps or [], indent=2, default=str)
    signals_str = json.dumps(signals or [], indent=2, default=str)
    impacts_str = json.dumps(impacts or [], indent=2, default=str)

    confidence_str = ""
    if confidence_score is not None:
        confidence_str = f"Score: {confidence_score}, Level: {confidence_level or 'UNKNOWN'}"

    scenarios_str = ""
    if scenarios:
        scenarios_str = json.dumps(scenarios, indent=2, default=str)

    alternatives_str = ""
    if alternatives:
        alternatives_str = json.dumps(alternatives, indent=2, default=str)

    return f"""You are a senior intelligence analyst. Analyze the following evidence, signals, impacts, and investigation goals. Provide a complete intelligence package.

INVESTIGATION GOAL:
{goal_question}

DETERMINISTIC ANALYSIS:
{deterministic_text}

EVIDENCE:
{evidence_str}

SIGNALS:
{signals_str}

IMPACTS:
{impacts_str}

CONFIDENCE:
{confidence_str}

KNOWLEDGE GAPS:
{gaps_str}

CURRENT SCENARIOS:
{scenarios_str}

CURRENT ALTERNATIVES:
{alternatives_str}

Provide your complete intelligence package as valid JSON with exactly these keys:
{{
    "executive_summary": "A concise executive briefing of key findings",
    "assessment": "Detailed intelligence assessment of the situation",
    "confidence": "HIGH/MEDIUM/LOW with explanation",
    "risks": ["risk 1", "risk 2"],
    "opportunities": ["opportunity 1", "opportunity 2"],
    "alternative_explanations": ["alternative 1", "alternative 2"],
    "future_scenarios": ["likely scenario", "possible scenario", "unlikely scenario"],
    "knowledge_gaps": ["gap 1", "gap 2"],
    "key_entities": ["entity 1", "entity 2"],
    "recommendations": ["recommendation 1", "recommendation 2"]
}}

Return ONLY valid JSON. Do not include markdown. Do not explain your reasoning."""


def _compute_prompt_hash(prompt: str) -> str:
    """SHA-256 hash of the prompt for cache lookups."""
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def _cache_lookup(prompt_hash: str) -> dict | None:
    """Check the LLM cache for a previous result with this prompt hash.

    Uses a standalone connection to avoid coupling to the API request
    lifecycle.  Returns None on any failure (cache is best-effort).
    """
    try:
        from database.session import SessionLocal
        from models.news_intelligence import LLMCache

        db = SessionLocal()
        try:
            from sqlalchemy import select
            row = db.scalar(
                select(LLMCache).where(LLMCache.prompt_hash == prompt_hash)
            )
            if row:
                logger.info("LLM cache HIT for hash %s…", prompt_hash[:12])
                return {
                    "response_json": row.response_json,
                    "model": row.model,
                    "latency": row.latency,
                    "input_tokens": row.input_tokens,
                    "output_tokens": row.output_tokens,
                    "cached": True,
                }
        finally:
            db.close()
    except Exception as exc:
        logger.debug("Cache lookup failed (non-critical): %s", str(exc))

    return None


def _cache_store(
    prompt_hash: str,
    prompt_text: str,
    response_json: dict,
    model: str,
    latency: float,
    input_tokens: int,
    output_tokens: int,
) -> None:
    """Store a validated intelligence response in the LLM cache."""
    try:
        from database.session import SessionLocal
        from models.news_intelligence import LLMCache

        db = SessionLocal()
        try:
            entry = LLMCache(
                prompt_hash=prompt_hash,
                prompt_text=prompt_text,
                response_json=response_json,
                model=model,
                latency=latency,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                created_at=datetime.now(timezone.utc),
            )
            db.add(entry)
            db.commit()
            logger.info("LLM cache STORE for hash %s…", prompt_hash[:12])
        finally:
            db.close()
    except Exception as exc:
        logger.debug("Cache store failed (non-critical): %s", str(exc))


# ---------------------------------------------------------------------------
# Core unified function
# ---------------------------------------------------------------------------

def generate_intelligence_package(
    goal_question: str,
    deterministic_text: str,
    evidence: list | dict | None = None,
    gaps: list | dict | None = None,
    signals: list | None = None,
    impacts: list | None = None,
    confidence_score: float | None = None,
    confidence_level: str | None = None,
    scenarios: dict | None = None,
    alternatives: dict | None = None,
) -> dict:
    """Generate a complete intelligence package in a single LLM call.

    This is the primary entry point for LLM augmentation. It builds
    a unified prompt containing all available intelligence context,
    makes one Ollama call, validates the JSON response, and returns
    the complete intelligence package.

    Parameters
    ----------
    goal_question : str
        The investigation goal question.
    deterministic_text : str
        Assessment text from the deterministic engine.
    evidence, gaps, signals, impacts : optional
        Contextual data from the deterministic pipeline.
    confidence_score, confidence_level : optional
        Deterministic confidence metrics.
    scenarios, alternatives : optional
        Existing deterministic scenarios and alternatives.

    Returns
    -------
    dict
        Keys: ``response_json``, ``latency``, ``model``,
        ``input_tokens``, ``output_tokens``, ``success``, ``cached``.
    """
    start_time = time.time()

    # --- Disabled mode: return defaults immediately ---
    if LLM_SERVICE_MODE == "disabled":
        return {
            "response_json": dict(_DEFAULTS),
            "latency": 0.0,
            "model": "deterministic",
            "input_tokens": 0,
            "output_tokens": 0,
            "success": True,
            "cached": False,
        }

    # --- Build prompt ---
    prompt = _build_intelligence_prompt(
        goal_question=goal_question,
        deterministic_text=deterministic_text,
        evidence=evidence,
        gaps=gaps,
        signals=signals,
        impacts=impacts,
        confidence_score=confidence_score,
        confidence_level=confidence_level,
        scenarios=scenarios,
        alternatives=alternatives,
    )

    prompt_hash = _compute_prompt_hash(prompt)

    # --- Cache check ---
    cached = _cache_lookup(prompt_hash)
    if cached:
        return {
            "response_json": cached["response_json"],
            "latency": 0.0,
            "model": cached["model"],
            "input_tokens": cached["input_tokens"],
            "output_tokens": cached["output_tokens"],
            "success": True,
            "cached": True,
        }

    # --- Call Ollama ---
    result = _ollama_generate(prompt)

    if result:
        parsed = _try_parse_json(result["text"])
        validated = _validate_intelligence_json(parsed)

        latency = round(time.time() - start_time, 3)
        model_name = f"Ollama/{OLLAMA_MODEL}"
        input_tokens = result.get("prompt_eval_count", 0)
        output_tokens = result.get("eval_count", 0)

        # Store in cache
        _cache_store(
            prompt_hash=prompt_hash,
            prompt_text=prompt[:2000],  # Truncate for storage
            response_json=validated,
            model=model_name,
            latency=latency,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

        return {
            "response_json": validated,
            "latency": latency,
            "model": model_name,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "success": True,
            "cached": False,
        }

    # --- Fallback ---
    logger.warning("Intelligence package LLM call failed — using deterministic defaults.")
    return {
        "response_json": dict(_DEFAULTS),
        "latency": round(time.time() - start_time, 3),
        "model": "fallback",
        "input_tokens": 0,
        "output_tokens": 0,
        "success": False,
        "cached": False,
    }


# ---------------------------------------------------------------------------
# Backward-compatible public API
# ---------------------------------------------------------------------------

def generate_assessment(
    goal_question: str,
    deterministic_text: str,
    evidence=None,
    gaps=None,
) -> dict:
    """Augment a deterministic assessment via the unified intelligence engine.

    Backward-compatible wrapper that preserves the original return
    format: ``{text, latency, model, input_tokens, output_tokens, success}``.
    """
    start_time = time.time()

    if LLM_SERVICE_MODE == "disabled":
        return _build_deterministic_result(deterministic_text, start_time)

    pkg = generate_intelligence_package(
        goal_question=goal_question,
        deterministic_text=deterministic_text,
        evidence=evidence,
        gaps=gaps,
    )

    if pkg["success"]:
        rj = pkg["response_json"]
        # Combine assessment + executive summary into a single text block
        text = rj.get("assessment", deterministic_text)
        summary = rj.get("executive_summary", "")
        if summary and summary != "insufficient evidence":
            text = f"EXECUTIVE SUMMARY:\n{summary}\n\nASSESSMENT:\n{text}"

        return {
            "text": text,
            "latency": pkg["latency"],
            "model": pkg["model"],
            "input_tokens": pkg["input_tokens"],
            "output_tokens": pkg["output_tokens"],
            "success": True,
        }

    return _build_deterministic_result(
        deterministic_text, start_time, model="fallback", success=False,
    )


def generate_scenarios(
    scenarios: dict,
    category: str,
) -> dict:
    """Augment deterministic scenarios via the unified intelligence engine.

    Returns a dict with keys ``likely``, ``possible``, ``unlikely``.
    """
    if LLM_SERVICE_MODE == "disabled" or not scenarios:
        return scenarios

    pkg = generate_intelligence_package(
        goal_question=f"Generate future scenarios for category: {category}",
        deterministic_text=json.dumps(scenarios, default=str),
        scenarios=scenarios,
    )

    if pkg["success"]:
        fs = pkg["response_json"].get("future_scenarios", [])
        if isinstance(fs, list) and len(fs) >= 3:
            return {
                "likely": fs[0],
                "possible": fs[1],
                "unlikely": fs[2],
            }
        elif isinstance(fs, list) and len(fs) > 0:
            return {
                "likely": fs[0],
                "possible": fs[1] if len(fs) > 1 else scenarios.get("possible", "N/A"),
                "unlikely": fs[2] if len(fs) > 2 else scenarios.get("unlikely", "N/A"),
            }

    return scenarios


def generate_alternatives(alternatives: dict) -> dict:
    """Augment deterministic alternatives via the unified intelligence engine.

    Returns a dict with keys ``primary`` and ``alternatives``.
    """
    if LLM_SERVICE_MODE == "disabled" or not alternatives:
        return alternatives

    pkg = generate_intelligence_package(
        goal_question="Evaluate competing hypotheses and alternative explanations",
        deterministic_text=json.dumps(alternatives, default=str),
        alternatives=alternatives,
    )

    if pkg["success"]:
        alt_list = pkg["response_json"].get("alternative_explanations", [])
        if isinstance(alt_list, list) and len(alt_list) > 0:
            return {
                "primary": alt_list[0] if isinstance(alt_list[0], str) else alternatives.get("primary", ""),
                "alternatives": [
                    {"explanation": a} if isinstance(a, str) else a
                    for a in alt_list[1:]
                ],
            }

    return alternatives


def generate_summary(exec_summary: dict) -> dict:
    """Augment deterministic executive summary via the unified intelligence engine.

    Returns a dict with keys ``key_findings``, ``confidence``,
    ``risks``, ``opportunities``, ``unknowns``.
    """
    if LLM_SERVICE_MODE == "disabled" or not exec_summary:
        return exec_summary

    pkg = generate_intelligence_package(
        goal_question="Refine executive intelligence briefing",
        deterministic_text=json.dumps(exec_summary, default=str),
        confidence_score=exec_summary.get("confidence", {}).get("score"),
        confidence_level=exec_summary.get("confidence", {}).get("level"),
    )

    if pkg["success"]:
        rj = pkg["response_json"]
        result = {
            "key_findings": rj.get("executive_summary", exec_summary.get("key_findings", "")),
            "confidence": exec_summary.get("confidence", {"level": "UNKNOWN", "score": 0.0}),
            "risks": rj.get("risks", exec_summary.get("risks", "")),
            "opportunities": rj.get("opportunities", exec_summary.get("opportunities", "")),
            "unknowns": rj.get("knowledge_gaps", exec_summary.get("unknowns", [])),
        }
        # Preserve the original confidence score (deterministic is authoritative)
        if "confidence" in exec_summary:
            result["confidence"] = exec_summary["confidence"]
        return result

    return exec_summary
