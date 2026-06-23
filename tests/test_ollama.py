"""Standalone test suite for Ollama + Qwen2.5:3b integration.

Tests the unified intelligence generation engine, backward-compatible
wrapper functions, prompt-hash cache, JSON validation, and fallback
behavior.

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


def _reload_svc(mode: str = "local"):
    """Reload the LLM service module with a specific mode."""
    os.environ["LLM_SERVICE_MODE"] = mode
    import importlib
    import services.llm_service as svc
    importlib.reload(svc)
    return svc


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
# Test 3 — generate_intelligence_package() — CORE TEST
# ---------------------------------------------------------------------------

def test_intelligence_package() -> bool:
    """Test the unified intelligence package generation."""
    name = "generate_intelligence_package()"
    try:
        svc = _reload_svc("local")

        start = time.time()
        result = svc.generate_intelligence_package(
            goal_question="What is the impact of AI on global markets?",
            deterministic_text="AI investments are increasing across major tech companies.",
            evidence=["Microsoft AI investment", "Google data centers", "NVIDIA chip demand"],
            gaps=["regulatory impact unknown", "consumer sentiment unclear"],
            signals=["AI chip demand surge", "enterprise adoption accelerating"],
            impacts=["positive market sentiment", "increased R&D spending"],
            confidence_score=0.72,
            confidence_level="MEDIUM",
        )
        latency = round(time.time() - start, 2)

        # Check envelope keys
        required_envelope = {"response_json", "latency", "model", "input_tokens", "output_tokens", "success", "cached"}
        if not required_envelope.issubset(result.keys()):
            missing = required_envelope - set(result.keys())
            log(name, "fail", f"Missing envelope keys: {missing}")
            return False

        if not result["success"]:
            log(name, "fail", "success=False")
            return False

        # Check intelligence JSON keys
        rj = result["response_json"]
        required_json = {
            "executive_summary", "assessment", "confidence", "risks",
            "opportunities", "alternative_explanations", "future_scenarios",
            "knowledge_gaps", "key_entities", "recommendations"
        }
        if not required_json.issubset(rj.keys()):
            missing = required_json - set(rj.keys())
            log(name, "fail", f"Missing JSON keys: {missing}")
            return False

        log(name, "pass", f"{latency}s — model={result['model']}, all 10 keys present")
        return True

    except Exception as e:
        log(name, "fail", str(e))
        return False


# ---------------------------------------------------------------------------
# Test 4 — JSON validation
# ---------------------------------------------------------------------------

def test_intelligence_validation() -> bool:
    """Test that _validate_intelligence_json repairs malformed data."""
    name = "JSON Schema Validation"
    try:
        svc = _reload_svc("disabled")

        # Test with None
        result = svc._validate_intelligence_json(None)
        if not isinstance(result, dict):
            log(name, "fail", "None input did not produce dict")
            return False

        # Test with partial data
        partial = {"executive_summary": "test", "risks": "should be a list"}
        result = svc._validate_intelligence_json(partial)

        if not isinstance(result.get("risks"), list):
            log(name, "fail", "String 'risks' not coerced to list")
            return False

        if result.get("assessment") != "insufficient evidence":
            log(name, "fail", f"Missing 'assessment' not defaulted, got: {result.get('assessment')}")
            return False

        # Test with complete valid data
        valid = {
            "executive_summary": "test summary",
            "assessment": "test assessment",
            "confidence": "HIGH",
            "risks": ["risk1"],
            "opportunities": ["opp1"],
            "alternative_explanations": ["alt1"],
            "future_scenarios": ["scenario1"],
            "knowledge_gaps": ["gap1"],
            "key_entities": ["entity1"],
            "recommendations": ["rec1"],
        }
        result = svc._validate_intelligence_json(valid)
        if result != valid:
            log(name, "fail", "Valid data was modified")
            return False

        log(name, "pass", "None, partial, and valid data all handled correctly")
        return True

    except Exception as e:
        log(name, "fail", str(e))
        return False


# ---------------------------------------------------------------------------
# Test 5 — Cache hit
# ---------------------------------------------------------------------------

def test_cache_hit() -> bool:
    """Test that a second identical call returns a cached result."""
    name = "Prompt Cache Hit"
    try:
        svc = _reload_svc("local")

        # First call — should be a cache miss
        result1 = svc.generate_intelligence_package(
            goal_question="Cache test: AI market impact analysis",
            deterministic_text="Testing cache behavior with identical prompts.",
            evidence=["cache test evidence 1"],
        )

        if not result1["success"]:
            log(name, "fail", "First call failed")
            return False

        first_latency = result1["latency"]

        # Second call — identical prompt, should be cache hit
        result2 = svc.generate_intelligence_package(
            goal_question="Cache test: AI market impact analysis",
            deterministic_text="Testing cache behavior with identical prompts.",
            evidence=["cache test evidence 1"],
        )

        if not result2["success"]:
            log(name, "fail", "Second call failed")
            return False

        if not result2.get("cached", False):
            log(name, "fail", "Second call was not cached")
            return False

        second_latency = result2["latency"]

        log(name, "pass", f"1st: {first_latency}s, 2nd: {second_latency}s (cached={result2['cached']})")
        return True

    except Exception as e:
        log(name, "fail", str(e))
        return False


# ---------------------------------------------------------------------------
# Test 6 — Backward compat: generate_assessment()
# ---------------------------------------------------------------------------

def test_backward_compat_assessment() -> bool:
    """Test that generate_assessment() returns the legacy envelope format."""
    name = "Backward Compat: generate_assessment()"
    try:
        svc = _reload_svc("local")

        start = time.time()
        result = svc.generate_assessment(
            goal_question="What is the geopolitical impact of semiconductor supply chains?",
            deterministic_text="Semiconductor supply chains are concentrated in East Asia.",
            evidence=["TSMC dominance", "US CHIPS Act", "EU semiconductor strategy"],
            gaps=["Chinese foundry capability unclear"],
        )
        latency = round(time.time() - start, 2)

        # Check legacy envelope format
        required_keys = {"text", "latency", "model", "input_tokens", "output_tokens", "success"}
        if not required_keys.issubset(result.keys()):
            missing = required_keys - set(result.keys())
            log(name, "fail", f"Missing keys: {missing}")
            return False

        if not result["success"]:
            log(name, "fail", "success=False")
            return False

        if not isinstance(result["text"], str) or len(result["text"]) == 0:
            log(name, "fail", "Text is empty or not a string")
            return False

        log(name, "pass", f"{latency}s — {len(result['text'])} chars")
        return True

    except Exception as e:
        log(name, "fail", str(e))
        return False


# ---------------------------------------------------------------------------
# Test 7 — Backward compat: generate_scenarios()
# ---------------------------------------------------------------------------

def test_backward_compat_scenarios() -> bool:
    """Test that generate_scenarios() returns dict with likely/possible/unlikely."""
    name = "Backward Compat: generate_scenarios()"
    try:
        svc = _reload_svc("local")

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

        log(name, "pass", f"{latency}s — likely={str(result['likely'])[:60]}...")
        return True

    except Exception as e:
        log(name, "fail", str(e))
        return False


# ---------------------------------------------------------------------------
# Test 8 — Backward compat: generate_alternatives()
# ---------------------------------------------------------------------------

def test_backward_compat_alternatives() -> bool:
    """Test that generate_alternatives() returns dict with primary/alternatives."""
    name = "Backward Compat: generate_alternatives()"
    try:
        svc = _reload_svc("local")

        start = time.time()
        result = svc.generate_alternatives(
            alternatives={
                "primary": "Tech companies investing for competitive advantage.",
                "alternatives": [
                    {"explanation": "Government subsidies driving investment", "score": 0.6},
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

        log(name, "pass", f"{latency}s — primary={str(result['primary'])[:60]}...")
        return True

    except Exception as e:
        log(name, "fail", str(e))
        return False


# ---------------------------------------------------------------------------
# Test 9 — Backward compat: generate_summary()
# ---------------------------------------------------------------------------

def test_backward_compat_summary() -> bool:
    """Test that generate_summary() returns dict with key_findings."""
    name = "Backward Compat: generate_summary()"
    try:
        svc = _reload_svc("local")

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

        log(name, "pass", f"{latency}s — findings={str(result['key_findings'])[:60]}...")
        return True

    except Exception as e:
        log(name, "fail", str(e))
        return False


# ---------------------------------------------------------------------------
# Test 10 — Disabled mode fallback
# ---------------------------------------------------------------------------

def test_disabled_fallback() -> bool:
    """Verify that disabled mode returns deterministic text unchanged."""
    name = "Disabled Mode Fallback"
    try:
        svc = _reload_svc("disabled")

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
# Test 11 — Disabled mode for intelligence package
# ---------------------------------------------------------------------------

def test_disabled_package() -> bool:
    """Verify that disabled mode returns default intelligence JSON."""
    name = "Disabled Package Fallback"
    try:
        svc = _reload_svc("disabled")

        result = svc.generate_intelligence_package(
            goal_question="Test goal",
            deterministic_text="Test text",
        )

        if not result["success"]:
            log(name, "fail", "success=False in disabled mode")
            return False

        rj = result["response_json"]
        if rj.get("assessment") != "insufficient evidence":
            log(name, "fail", f"Expected default assessment, got: {rj.get('assessment')}")
            return False

        if result["latency"] != 0.0:
            log(name, "fail", f"Expected 0 latency, got: {result['latency']}")
            return False

        log(name, "pass", "Default intelligence JSON returned")
        return True

    except Exception as e:
        log(name, "fail", str(e))
        return False


# ---------------------------------------------------------------------------
# Test 12 — Benchmark latency
# ---------------------------------------------------------------------------

def test_benchmark_latency() -> bool:
    """Verify single unified call completes under 30 seconds."""
    name = "Benchmark Latency (<30s)"
    try:
        svc = _reload_svc("local")

        start = time.time()
        result = svc.generate_intelligence_package(
            goal_question="Benchmark: Comprehensive AI market analysis for latency testing",
            deterministic_text="Multiple AI companies are scaling infrastructure investments.",
            evidence=[
                "Microsoft $10B OpenAI investment",
                "Google DeepMind advances",
                "NVIDIA H100 demand",
                "Meta open-source AI models",
                "Amazon Bedrock expansion",
            ],
            gaps=["Regulatory timeline", "Energy consumption concerns"],
            signals=["Chip shortage easing", "Enterprise AI adoption"],
            impacts=["Positive market cap growth", "Job displacement concerns"],
            confidence_score=0.78,
            confidence_level="MEDIUM",
        )
        latency = round(time.time() - start, 2)

        if not result["success"]:
            log(name, "fail", "Call failed")
            return False

        if latency > 30:
            log(name, "fail", f"Latency {latency}s exceeds 30s threshold")
            return False

        log(name, "pass", f"{latency}s — well within 30s target")
        return True

    except Exception as e:
        log(name, "fail", str(e))
        return False


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def main() -> None:
    print("\n" + "=" * 64)
    print("  DeepDive Intelligence — Unified Engine Integration Tests")
    print("=" * 64 + "\n")

    connected = test_ollama_connectivity()

    if connected:
        test_raw_generate()
        print()

        print("  --- Unified Engine ---")
        test_intelligence_package()
        test_intelligence_validation()
        test_cache_hit()
        print()

        print("  --- Backward Compatibility ---")
        test_backward_compat_assessment()
        test_backward_compat_scenarios()
        test_backward_compat_alternatives()
        test_backward_compat_summary()
        print()

        print("  --- Benchmark ---")
        test_benchmark_latency()
    else:
        print("\n  Skipping LLM tests — Ollama not available.\n")
        for name in [
            "Raw Ollama Generate",
            "generate_intelligence_package()",
            "JSON Schema Validation",
            "Prompt Cache Hit",
            "Backward Compat: generate_assessment()",
            "Backward Compat: generate_scenarios()",
            "Backward Compat: generate_alternatives()",
            "Backward Compat: generate_summary()",
            "Benchmark Latency (<30s)",
        ]:
            log(name, "skip", "Ollama not available")

    print()
    print("  --- Fallback (no Ollama needed) ---")
    test_disabled_fallback()
    test_disabled_package()

    # Summary
    passed = sum(1 for _, s in results if s == "pass")
    failed = sum(1 for _, s in results if s == "fail")
    skipped = sum(1 for _, s in results if s == "skip")

    print(f"\n{'=' * 64}")
    print(f"  Results: {passed} passed, {failed} failed, {skipped} skipped")
    print(f"{'=' * 64}\n")

    sys.exit(1 if failed > 0 else 0)


if __name__ == "__main__":
    main()
