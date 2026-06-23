"""LLM Augmentation Service — Local Ollama Integration.

Provides natural-language synthesis on top of the deterministic
intelligence pipeline using a locally-running Ollama instance
with Qwen2.5:3b.

Modes
-----
- ``disabled``  — bypass LLM entirely, return deterministic text as-is.
- ``local``     — call Ollama on localhost for augmented output.

Every public function guarantees a safe return value: if the LLM
call fails for *any* reason (timeout, connection error, malformed
response) the deterministic output is returned and the failure is
logged.  The pipeline never crashes due to an LLM issue.
"""

import json
import os
import time
import logging

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
# Internal helpers
# ---------------------------------------------------------------------------

def _build_deterministic_result(
    text: str,
    start_time: float,
    *,
    model: str = "deterministic",
    success: bool = True,
) -> dict:
    """Standard response envelope used by every public function."""
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
        # Remove first line (```json) and last line (```)
        lines = [
            line for line in lines
            if not line.strip().startswith("```")
        ]
        cleaned = "\n".join(lines).strip()

    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_assessment(
    goal_question: str,
    deterministic_text: str,
    evidence=None,
    gaps=None,
) -> dict:
    """Augment a deterministic assessment with LLM natural-language synthesis.

    Parameters
    ----------
    goal_question : str
        The investigation goal question.
    deterministic_text : str
        The assessment text produced by the deterministic engine.
    evidence : list | dict | None
        Evidence summary from the deterministic pipeline.
    gaps : list | dict | None
        Knowledge gaps from the deterministic pipeline.

    Returns
    -------
    dict
        Standard response envelope with keys:
        ``text``, ``latency``, ``model``, ``input_tokens``,
        ``output_tokens``, ``success``.
    """
    start_time = time.time()
    evidence = evidence or []
    gaps = gaps or []

    if LLM_SERVICE_MODE == "disabled":
        return _build_deterministic_result(deterministic_text, start_time)

    prompt = f"""You are an intelligence analyst. Analyze the following evidence and provide a refined assessment.

INVESTIGATION GOAL:
{goal_question}

DETERMINISTIC ANALYSIS:
{deterministic_text}

EVIDENCE:
{json.dumps(evidence, indent=2, default=str)}

KNOWLEDGE GAPS:
{json.dumps(gaps, indent=2, default=str)}

Provide your analysis as valid JSON with these keys:
{{
    "executive_summary": "",
    "evidence_strength": "",
    "risks": [],
    "opportunities": [],
    "alternative_explanations": [],
    "future_scenarios": [],
    "confidence_assessment": ""
}}

Return ONLY valid JSON, no additional text."""

    result = _ollama_generate(prompt)

    if result:
        return {
            "text": result["text"],
            "latency": round(time.time() - start_time, 3),
            "model": f"Ollama/{OLLAMA_MODEL}",
            "input_tokens": result.get("prompt_eval_count", 0),
            "output_tokens": result.get("eval_count", 0),
            "success": True,
        }

    # Fallback
    logger.warning("Assessment LLM augmentation failed — using deterministic output.")
    return _build_deterministic_result(
        deterministic_text, start_time, model="fallback", success=False,
    )


def generate_scenarios(
    scenarios: dict,
    category: str,
) -> dict:
    """Augment deterministic future scenarios with LLM natural-language synthesis.

    Parameters
    ----------
    scenarios : dict
        Dict with keys ``likely``, ``possible``, ``unlikely``.
    category : str
        The goal type / category label.

    Returns
    -------
    dict
        Enhanced scenarios dict (same keys), or the original on failure.
    """
    if LLM_SERVICE_MODE == "disabled" or not scenarios:
        return scenarios

    prompt = f"""You are an intelligence analyst specializing in scenario forecasting.

CATEGORY: {category}

CURRENT SCENARIO ANALYSIS:
- Likely: {scenarios.get('likely', 'N/A')}
- Possible: {scenarios.get('possible', 'N/A')}
- Unlikely: {scenarios.get('unlikely', 'N/A')}

Refine and expand these scenarios using available evidence and signals.
Return ONLY valid JSON:
{{
    "likely": "Enhanced likely scenario description",
    "possible": "Enhanced possible scenario description",
    "unlikely": "Enhanced unlikely scenario description"
}}

Return ONLY valid JSON, no additional text."""

    result = _ollama_generate(prompt)

    if result:
        parsed = _try_parse_json(result["text"])
        if parsed and all(k in parsed for k in ("likely", "possible", "unlikely")):
            return parsed
        logger.warning("Scenario LLM response was not valid JSON — using deterministic.")

    return scenarios


def generate_alternatives(alternatives: dict) -> dict:
    """Augment deterministic alternative explanations with LLM synthesis.

    Parameters
    ----------
    alternatives : dict
        Dict with keys ``primary`` (str) and ``alternatives`` (list).

    Returns
    -------
    dict
        Enhanced alternatives dict, or the original on failure.
    """
    if LLM_SERVICE_MODE == "disabled" or not alternatives:
        return alternatives

    primary = alternatives.get("primary", "")
    alt_list = alternatives.get("alternatives", [])

    prompt = f"""You are an intelligence analyst evaluating competing hypotheses.

PRIMARY EXPLANATION:
{primary}

ALTERNATIVE EXPLANATIONS:
{json.dumps(alt_list, indent=2, default=str)}

Provide refined competing hypotheses ranked by probability.
Explain the evidence supporting each hypothesis.
Return ONLY valid JSON:
{{
    "primary": "Most probable explanation with supporting evidence",
    "alternatives": [
        {{
            "explanation": "Alternative explanation",
            "probability": "HIGH/MEDIUM/LOW",
            "supporting_evidence": "Evidence that supports this"
        }}
    ]
}}

Return ONLY valid JSON, no additional text."""

    result = _ollama_generate(prompt)

    if result:
        parsed = _try_parse_json(result["text"])
        if parsed and "primary" in parsed:
            return parsed
        logger.warning("Alternatives LLM response was not valid JSON — using deterministic.")

    return alternatives


def generate_summary(exec_summary: dict) -> dict:
    """Augment deterministic executive summary with LLM natural-language synthesis.

    Parameters
    ----------
    exec_summary : dict
        Executive summary dict from the deterministic engine.

    Returns
    -------
    dict
        Enhanced summary dict, or the original on failure.
    """
    if LLM_SERVICE_MODE == "disabled" or not exec_summary:
        return exec_summary

    prompt = f"""You are a senior intelligence analyst writing an executive briefing.

CURRENT EXECUTIVE SUMMARY:
{json.dumps(exec_summary, indent=2, default=str)}

Refine this executive summary for clarity, actionability, and impact.
Return ONLY valid JSON:
{{
    "key_findings": "Refined key findings summary",
    "confidence": {{
        "level": "HIGH/MEDIUM/LOW",
        "score": 0.0
    }},
    "risks": "Refined risk assessment",
    "opportunities": "Refined opportunity analysis",
    "unknowns": ["list", "of", "critical", "unknowns"]
}}

Return ONLY valid JSON, no additional text."""

    result = _ollama_generate(prompt)

    if result:
        parsed = _try_parse_json(result["text"])
        if parsed and "key_findings" in parsed:
            # Preserve the original confidence score if LLM didn't produce a valid one
            if "confidence" in exec_summary and "confidence" in parsed:
                original_score = exec_summary["confidence"].get("score")
                if isinstance(original_score, (int, float)):
                    parsed["confidence"]["score"] = original_score
            return parsed
        logger.warning("Summary LLM response was not valid JSON — using deterministic.")

    return exec_summary
