from unittest.mock import Mock

import pytest

from scripts import validate_mem0_retrieval as validation


def test_retrieval_runner_refuses_production(monkeypatch):
    monkeypatch.setenv("REPLIT_DEPLOYMENT", "1")
    client = Mock(side_effect=AssertionError("Network forbidden"))
    monkeypatch.setattr(validation, "RetrievalProvider", client)
    assert validation.run_validation()["status"] == "BLOCKED"
    client.assert_not_called()


def test_retrieval_runner_forbids_deletion():
    provider = validation.RetrievalProvider("synthetic-key", float("inf"))
    with pytest.raises(RuntimeError, match="Deletion is not approved"):
        provider.delete_exact("synthetic-id")
    assert provider.counts["delete_attempts"] == 0


def test_retrieval_deadline_blocks_network(monkeypatch):
    provider = validation.RetrievalProvider("synthetic-key", 0)
    add = Mock(side_effect=AssertionError("Network forbidden"))
    monkeypatch.setattr(validation.BoundedProvider, "add", add)
    with pytest.raises(TimeoutError):
        provider.add({})
    add.assert_not_called()


def test_retrieval_search_budget_and_sanitized_schema(monkeypatch):
    from agents.semantic_memory import HostedMem0
    search = Mock(return_value={"results": [{
        "score": .7, "user_id": "private-owner", "memory": "private-body",
        "metadata": {"summary": "private-body", "source_ticket_ids": "SP-1"},
    }]})
    monkeypatch.setattr(HostedMem0, "search", search)
    provider = validation.RetrievalProvider("synthetic-key", float("inf"))
    for _ in range(12):
        provider.search("private-query", {})
    with pytest.raises(RuntimeError, match="budget"):
        provider.search("private-query", {})
    assert search.call_count == 12
    assert "private" not in str(provider.search_schemas)


def test_node_trace_retains_only_node_names():
    trace = validation.NodeTrace()
    trace.on_chain_start(None, {"secret": "private"}, metadata={"langgraph_node": "answer"})
    trace.on_chain_start(None, {}, metadata={"langgraph_node": "answer"})
    trace.on_chain_start(None, {}, metadata={"langgraph_node": "private-value"})
    assert trace.nodes == ["answer"]
