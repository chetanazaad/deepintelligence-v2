"""Standalone test suite for Ollama + Qwen2.5:3b integration.

Run with:
    python tests/test_ollama.py

Prerequisites:
    - Ollama must be running locally (``ollama serve``)
    - qwen2.5:3b must be pulled (``ollama pull qwen2.5:3b``)
"""

import json
import os
import sys
import time

# Ensure project root is on sys.path so we can import services.*
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_BASE = OLLAMA_URL.rsplit("/api/", 1)[0]  # http://localhost:11434
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
SKIP = "\033[93mSKIP\033[0m"

results: list[tuple[str, str]] = []


def log(name: str, status: str, detail: str = "") -> None:
    results.append((name, status))
    tag = PASS if status == "pass" else FAIL if status == "fail" else SKIP
    suffix = f"  ({detail})" if detail else ""
    print(f"  [{tag}] {name}{suffix}")


# ---------------------------------------------------------------------------
# Test 1 — Ollama connectivity
# ---------------------------------------------------------------------------

def test_ollama_connectivity() -> bool:
    """Verify Ollama is reachable and the target model is available."""
    name = "Ollama Connectivity"
    try:
        resp = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=5)
        if resp.status_code != 200:
            log(name, "fail", f"HTTP {resp.status_code}")
            return False

        models = [m["name"] for m in resp.json().get("models", [])]
        if not any(OLLAMA_MODEL in m for m in models):
            log(name, "fail", f"Model '{OLLAMA_MODEL}' not found in {models}")
            return False

        log(name, "pass", f"Found model in {len(models)} available models")
        return True

    except requests.exceptions.ConnectionError:
        log(name, "fail", "Ollama is not running")
        return False


# ---------------------------------------------------------------------------
# Test 2 — Raw Ollama generate
# ---------------------------------------------------------------------------

def test_raw_generate() -> bool:
    """Send a simple prompt and verify we get a non-empty response."""
    name = "Raw Ollama Generate"
    try:
        start = time.time()
        resp = requests.post(
            OLLAMA_URL,
            json={"model": OLLAMA_MODEL, "prompt": "Say hello in one sentence.", "stream": False},
            timeout=60,
        )
        latency = round(time.time() - start, 2)

        if resp.status_code != 200:
            log(name, "fail", f"HTTP {resp.status_code}")
            return False

        text = resp.json().get("response", "")
        if not text:
            log(name, "fail", "Empty response")
            return False

        log(name, "pass", f"{latency}s — {text[:60]}...")
        return True

    except Exception as e:
        log(name, "fail", str(e))
        return False


# ---------------------------------------------------------------------------
# Test 3 — generate_assessment()
# ---------------------------------------------------------------------------

def test_generate_assessment() -> bool:
    """Test the generate_assessment function from llm_service."""
    name = "generate_assessment()"
    try:
        # Force local mode for this test
        os.environ["LLM_SERVICE_MODE"] = "local"

        # Re-import to pick up env change
        import importlib
        import services.llm_service as svc
        importlib.reload(svc)

        start = time.time()
        result = svc.generate_assessment(
            goal_question="What is the impact of AI on global markets?",
            deterministic_text="AI investments are increasing across major tech companies.",
            evidence=["Microsoft AI investment", "Google data centers", "NVIDIA chip demand"],
            gaps=["regulatory impact unknown", "consumer sentiment unclear"],
        )
        latency = round(time.time() - start, 2)

        required_keys = {"text", "latency", "model", "input_tokens", "output_tokens", "success"}
        if not required_keys.issubset(result.keys()):
            missing = required_keys - set(result.keys())
            log(name, "fail", f"Missing keys: {missing}")
            return False

        if not result["success"]:
            log(name, "fail", "success=False")
            return False

        log(name, "pass", f"{latency}s — model={result['model']}, {len(result['text'])} chars")
        return True

    except Exception as e:
        log(name, "fail", str(e))
        return False


# ---------------------------------------------------------------------------
# Test 4 — generate_scenarios()
# ---------------------------------------------------------------------------

def test_generate_scenarios() -> bool:
    """Test the generate_scenarios function from llm_service."""
    name = "generate_scenarios()"
    try:
        os.environ["LLM_SERVICE_MODE"] = "local"
        import importlib
        import services.llm_service as svc
        importlib.reload(svc)

        start = time.time()
        result = svc.generate_scenarios(
            scenarios={
                "likely": "AI adoption accelerates in enterprise.",
                "possible": "Regulatory pushback slows adoption.",
                "unlikely": "Complete AI market collapse.",
            },
            category="TECHNOLOGY",
        )
        latency = round(time.time() - start, 2)

        if not isinstance(result, dict):
            log(name, "fail", f"Expected dict, got {type(result)}")
            return False

        if "likely" not in result:
            log(name, "fail", "Missing 'likely' key")
            return False

        log(name, "pass", f"{latency}s — likely={result['likely'][:60]}...")
        return True

    except Exception as e:
        log(name, "fail", str(e))
        return False


# ---------------------------------------------------------------------------
# Test 5 — generate_alternatives()
# ---------------------------------------------------------------------------

def test_generate_alternatives() -> bool:
    """Test the generate_alternatives function from llm_service."""
    name = "generate_alternatives()"
    try:
        os.environ["LLM_SERVICE_MODE"] = "local"
        import importlib
        import services.llm_service as svc
        importlib.reload(svc)

        start = time.time()
        result = svc.generate_alternatives(
            alternatives={
                "primary": "Tech companies are investing in AI for competitive advantage.",
                "alternatives": [
                    {"explanation": "Government subsidies driving AI investment", "score": 0.6},
                    {"explanation": "Consumer demand pulling AI products to market", "score": 0.4},
                ],
            }
        )
        latency = round(time.time() - start, 2)

        if not isinstance(result, dict):
            log(name, "fail", f"Expected dict, got {type(result)}")
            return False

        if "primary" not in result:
            log(name, "fail", "Missing 'primary' key")
            return False

        log(name, "pass", f"{latency}s — primary={result['primary'][:60]}...")
        return True

    except Exception as e:
        log(name, "fail", str(e))
        return False


# ---------------------------------------------------------------------------
# Test 6 — generate_summary()
# ---------------------------------------------------------------------------

def test_generate_summary() -> bool:
    """Test the generate_summary function from llm_service."""
    name = "generate_summary()"
    try:
        os.environ["LLM_SERVICE_MODE"] = "local"
        import importlib
        import services.llm_service as svc
        importlib.reload(svc)

        start = time.time()
        result = svc.generate_summary(
            exec_summary={
                "key_findings": "AI investment is accelerating globally.",
                "confidence": {"level": "MEDIUM", "score": 0.65},
                "risks": "Regulatory uncertainty remains.",
                "opportunities": "First-mover advantage in enterprise AI.",
                "unknowns": ["consumer adoption rate", "regulatory timeline"],
            }
        )
        latency = round(time.time() - start, 2)

        if not isinstance(result, dict):
            log(name, "fail", f"Expected dict, got {type(result)}")
            return False

        if "key_findings" not in result:
            log(name, "fail", "Missing 'key_findings' key")
            return False

        log(name, "pass", f"{latency}s — findings={result['key_findings'][:60]}...")
        return True

    except Exception as e:
        log(name, "fail", str(e))
        return False


# ---------------------------------------------------------------------------
# Test 7 — Fallback when disabled
# ---------------------------------------------------------------------------

def test_disabled_fallback() -> bool:
    """Verify that disabled mode returns deterministic text unchanged."""
    name = "Disabled Mode Fallback"
    try:
        os.environ["LLM_SERVICE_MODE"] = "disabled"
        import importlib
        import services.llm_service as svc
        importlib.reload(svc)

        original_text = "This is the deterministic output."
        result = svc.generate_assessment(
            goal_question="Test goal",
            deterministic_text=original_text,
        )

        if result["text"] != original_text:
            log(name, "fail", "Text was modified in disabled mode")
            return False

        if result["model"] != "deterministic":
            log(name, "fail", f"Expected model='deterministic', got '{result['model']}'")
            return False

        log(name, "pass", "Deterministic output preserved")
        return True

    except Exception as e:
        log(name, "fail", str(e))
        return False


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def main() -> None:
    print("\n" + "=" * 60)
    print("  DeepDive Intelligence — Ollama Integration Tests")
    print("=" * 60 + "\n")

    connected = test_ollama_connectivity()

    if connected:
        test_raw_generate()
        test_generate_assessment()
        test_generate_scenarios()
        test_generate_alternatives()
        test_generate_summary()
    else:
        print("\n  Skipping LLM tests — Ollama not available.\n")
        for name in [
            "Raw Ollama Generate",
            "generate_assessment()",
            "generate_scenarios()",
            "generate_alternatives()",
            "generate_summary()",
        ]:
            log(name, "skip", "Ollama not available")

    # Always run fallback test (no Ollama needed)
    test_disabled_fallback()

    # Summary
    passed = sum(1 for _, s in results if s == "pass")
    failed = sum(1 for _, s in results if s == "fail")
    skipped = sum(1 for _, s in results if s == "skip")

    print(f"\n{'=' * 60}")
    print(f"  Results: {passed} passed, {failed} failed, {skipped} skipped")
    print(f"{'=' * 60}\n")

    sys.exit(1 if failed > 0 else 0)


if __name__ == "__main__":
    main()
