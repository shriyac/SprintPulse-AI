"""Production configuration safety checks; never connect to external services."""
from pathlib import Path
from unittest.mock import Mock

import pytest

import agents.graph as graph
import agents.semantic_memory as memory
import agents.semantic_ledger as ledger_module
from agents.memory import new_conversation_key
from tools.sprint_data import load_sprint_data


@pytest.fixture
def settings(monkeypatch):
    for name, value in {
        "MEM0_ENABLED": "true",
        "MEM0_PROJECT_ID": "synthetic_config_test",
        "MEM0_API_KEY": "synthetic-not-a-real-key",
        "MEM0_LEDGER_DATABASE_URL": "postgresql://synthetic.invalid/test",
        "MEM0_TELEMETRY": "false",
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("REPLIT_DEPLOYMENT", raising=False)
    monkeypatch.setenv("REPLIT_ENVIRONMENT", "production")  # Editor quirk.


@pytest.mark.parametrize("deployed,namespace", [
    ("1", "development"), (None, "production"), ("0", "production"),
    ("true", "production"), ("1", ""), ("1", "invalid"),
])
def test_namespace_mismatch_rejected_before_backend_access(settings, monkeypatch, deployed, namespace):
    if deployed is not None:
        monkeypatch.setenv("REPLIT_DEPLOYMENT", deployed)
    monkeypatch.setenv("MEM0_ENVIRONMENT", namespace)
    provider = Mock(side_effect=AssertionError("Provider must not be constructed"))
    ledger = Mock(side_effect=AssertionError("Ledger must not be constructed"))
    monkeypatch.setattr(memory, "HostedMem0", provider)
    monkeypatch.setattr(ledger_module, "PostgresLedger", ledger)
    service = memory.configured_semantic_memory()
    assert isinstance(service, memory.DisabledMemory)
    assert service.status == "unavailable"
    assert service.project_scope is None
    assert memory.configured_project_scope() is None
    provider.assert_not_called()
    ledger.assert_not_called()


@pytest.mark.parametrize("deployed,namespace", [(None, "development"), ("1", "production")])
def test_matching_namespace_selects_only_configured_backend(settings, monkeypatch, deployed, namespace):
    if deployed is not None:
        monkeypatch.setenv("REPLIT_DEPLOYMENT", deployed)
    monkeypatch.setenv("MEM0_ENVIRONMENT", namespace)
    provider, ledger = Mock(), Mock()
    provider_factory, ledger_factory = Mock(return_value=provider), Mock(return_value=ledger)
    monkeypatch.setattr(memory, "HostedMem0", provider_factory)
    monkeypatch.setattr(ledger_module, "PostgresLedger", ledger_factory)
    service = memory.configured_semantic_memory()
    assert isinstance(service, memory.SemanticMemory)
    assert service.project_scope == f"{namespace}:synthetic_config_test"
    provider_factory.assert_called_once_with("synthetic-not-a-real-key")
    ledger_factory.assert_called_once_with("postgresql://synthetic.invalid/test")
    provider.ready.assert_not_called()
    ledger.ready.assert_not_called()


@pytest.mark.parametrize("failing_backend", ["ledger", "provider"])
def test_production_service_outage_keeps_real_graph_and_fresh_metrics(
    settings, monkeypatch, tmp_path, failing_backend,
):
    monkeypatch.setenv("REPLIT_DEPLOYMENT", "1")
    monkeypatch.setenv("MEM0_ENVIRONMENT", "production")
    provider, ledger = Mock(), Mock()
    getattr({"ledger": ledger, "provider": provider}[failing_backend], "ready").side_effect = TimeoutError(
        "synthetic outage"
    )
    monkeypatch.setattr(memory, "HostedMem0", Mock(return_value=provider))
    monkeypatch.setattr(ledger_module, "PostgresLedger", Mock(return_value=ledger))
    monkeypatch.setattr(graph, "CHECKPOINT_PATH", tmp_path / "checkpoints.sqlite")
    monkeypatch.setattr(graph, "generate_grounded_text", lambda *args: (None, "test fallback"))
    data = load_sprint_data(Path(__file__).parents[1] / "data")
    result = graph.invoke_sprint_graph(
        "Current completion metrics?", "Sprint 26", data, new_conversation_key(),
    )
    assert not result["error"]
    assert result["tool_outputs"]["sprint"]["completion_rate"] == 66.7
    assert result["response"]
    assert result["semantic_memory_status"] == {"search": "unavailable", "write": "unavailable"}
    provider.search.assert_not_called()
    provider.add.assert_not_called()
    ledger.enqueue.assert_not_called()
    ledger.claim.assert_not_called()
