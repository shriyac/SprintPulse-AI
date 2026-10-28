"""Opt-in only; approved sandbox credentials, bounded writes and exact cleanup."""
import os

import pytest


def test_live_mem0_development_validation():
    if os.getenv("SPRINTPULSE_RUN_MEM0_LIVE_TESTS") != "true":
        pytest.skip("Live mem0 sandbox test is not enabled; no remote retrieval verified.")
    if not os.getenv("MEM0_TEST_API_KEY"):
        pytest.fail("A dedicated MEM0_TEST_API_KEY is required; never use a production key.")
    from scripts.validate_mem0_sandbox import run_validation
    result = run_validation()
    assert result["status"] == "PASS", result
