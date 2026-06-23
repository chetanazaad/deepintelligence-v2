import os
import time
import httpx
import logging

logger = logging.getLogger(__name__)

# Modes:
# disabled = use deterministic output only
# colab = use Qwen running on Colab
# local = future local transformer support

LLM_SERVICE_MODE = os.getenv(
    "LLM_SERVICE_MODE",
    "disabled"
)

COLAB_TUNNEL_URL = os.getenv(
    "COLAB_TUNNEL_URL",
    "http://localhost:8000"
)


def _colab_generate(endpoint: str, payload: dict) -> dict:
    """
    Send payload to Colab FastAPI server.
    """

    try:
        url = f"{COLAB_TUNNEL_URL.rstrip('/')}/{endpoint}"

        logger.info(f"Sending request to {url}")

        with httpx.Client(timeout=120.0) as client:
            response = client.post(
                url,
                json=payload
            )

            if response.status_code == 200:
                return response.json()

            logger.warning(
                f"Colab returned {response.status_code}"
            )

    except Exception as e:
        logger.warning(
            f"Colab inference failed: {str(e)}"
        )

    return {}


def generate_assessment(
    goal_question: str,
    deterministic_text: str,
    evidence=None,
    gaps=None,
) -> dict:
    """
    LLM assessment refinement.
    """

    start_time = time.time()

    evidence = evidence or []
    gaps = gaps or []

    # -----------------------
    # Deterministic fallback
    # -----------------------
    if LLM_SERVICE_MODE == "disabled":
        return {
            "text": deterministic_text,
            "latency": 0.0,
            "model": "deterministic",
            "input_tokens": 0,
            "output_tokens": 0,
            "success": True
        }

    payload = {
        "goal": goal_question,
        "assessment": deterministic_text,
        "evidence": evidence,
        "gaps": gaps
    }

    # -----------------------
    # Colab Qwen
    # -----------------------
    if LLM_SERVICE_MODE == "colab":

        result = _colab_generate(
            "generate",
            payload
        )

        if result:

            return {
                "text": result.get(
                    "enhanced_assessment",
                    deterministic_text
                ),
                "latency": round(
                    time.time() - start_time,
                    3
                ),
                "model": "Qwen2.5-7B-Colab",
                "input_tokens": result.get(
                    "input_tokens",
                    0
                ),
                "output_tokens": result.get(
                    "output_tokens",
                    0
                ),
                "success": True
            }

        logger.warning(
            "Colab failed. Using deterministic fallback."
        )

    # -----------------------
    # Local future model
    # -----------------------
    if LLM_SERVICE_MODE == "local":

        enhanced_text = (
            "[LOCAL QWEN AUGMENTATION]\n\n"
            f"Goal: {goal_question}\n\n"
            f"{deterministic_text}"
        )

        return {
            "text": enhanced_text,
            "latency": round(
                time.time() - start_time,
                3
            ),
            "model": "Qwen-Local",
            "input_tokens": 0,
            "output_tokens": 0,
            "success": True
        }

    # -----------------------
    # Emergency fallback
    # -----------------------
    return {
        "text": deterministic_text,
        "latency": round(
            time.time() - start_time,
            3
        ),
        "model": "fallback",
        "input_tokens": 0,
        "output_tokens": 0,
        "success": False
    }


def generate_scenarios(
    scenarios: dict,
    category: str
):
    """
    Future Qwen scenario generation.
    """

    if (
        LLM_SERVICE_MODE == "disabled"
        or not scenarios
    ):
        return scenarios

    return scenarios


def generate_alternatives(
    alternatives: dict
):
    """
    Future alternative hypothesis generation.
    """

    if (
        LLM_SERVICE_MODE == "disabled"
        or not alternatives
    ):
        return alternatives

    return alternatives


def generate_summary(
    exec_summary: dict
):
    """
    Future executive summary generation.
    """

    if (
        LLM_SERVICE_MODE == "disabled"
        or not exec_summary
    ):
        return exec_summary

    return exec_summary
