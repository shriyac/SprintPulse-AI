from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import copy
import json
from pathlib import Path
from threading import Lock
from unittest.mock import Mock

import pytest

import agents.graph as graph
import agents.llm as llm
from agents.findings import Finding, extract_findings
from agents.memory import new_conversation_key
from agents.semantic_memory import (
    DisabledMemory, HostedMem0, MAX_WRITES, SemanticMemory, configured_semantic_memory,
)
from tools.sprint_data import load_sprint_data

ROOT = Path(__file__).parents[1]


class Ledger:
    """Thread-safe test double for the durable unique-key outbox contract."""
    def __init__(self):
        self.rows = {}
        self.lock = Lock()
        self.ready = Mock()

    def enqueue(self, records):
        with self.lock:
            for record in records:
                self.rows.setdefault(record["finding_id"], {
                    "payload": record, "status": "queued", "event_id": None,
                })

    def claim(self, project, owner, environment):
        with self.lock:
            for row in self.rows.values():
                value = row["payload"]
                if row["status"] == "queued" and (
                    value["project_id"], value["owner_scope"], value["environment"]
                ) == (project, owner, environment):
                    row["status"] = "reserved"
                    return value

    def finish(self, finding_id, status, event_id=None):
        with self.lock:
            self.rows[finding_id].update(status=status, event_id=event_id)

    def get_finding(self, finding_id, project, owner, environment):
        with self.lock:
            row = self.rows.get(finding_id)
            if row and row["status"] in {"pending", "reserved", "unknown"}:
                record = row["payload"]
                if (record["project_id"], record["owner_scope"], record["environment"]) == (project, owner, environment):
                    return copy.deepcopy(record)


@pytest.fixture
def context(tmp_path, monkeypatch):
    data = load_sprint_data(ROOT / "data")
    key = new_conversation_key()
    provider = Mock()
    provider.search.return_value = {"results": []}
    provider.add.return_value = {"status": "PENDING", "event_id": "test-event"}
    ledger = Ledger()
    service = SemanticMemory("project_alpha", "development", provider, ledger)
    monkeypatch.setenv("MEM0_PROJECT_ID", "project_alpha")
    monkeypatch.setenv("MEM0_ENVIRONMENT", "development")
    monkeypatch.setattr(graph, "CHECKPOINT_PATH", tmp_path / "checkpoints.sqlite")
    model = Mock(return_value=(None, "test fallback"))
    monkeypatch.setattr(graph, "generate_grounded_text", model)
    monkeypatch.setattr(graph, "configured_semantic_memory", lambda: service)
    return data, key, service, provider, ledger, model


def finding(**changes):
    values = dict(
        kind="dependency", summary="Partner sandbox access delayed SP-118.",
        source_ticket_ids=("SP-118",), sprint_name="Sprint 25",
        observed_at="2026-06-26T00:00:00+00:00",
        evidence={"source_field": "blocker_reason", "statement": "Waiting on partner access"},
    )
    return Finding(**{**values, **changes})


def match(service, key, fact=None, **updates):
    value = (fact or finding()).envelope(
        service.project, service._owner(key), service.environment,
    )
    value.update(updates)
    return {"user_id": value["owner_scope"], "metadata": value, "score": .93}


def test_default_disabled_performs_no_backend_or_sdk_access(monkeypatch):
    monkeypatch.delenv("MEM0_ENABLED", raising=False)
    monkeypatch.setattr(HostedMem0, "__init__", Mock(side_effect=AssertionError("SDK accessed")))
    service = configured_semantic_memory()
    assert isinstance(service, DisabledMemory)
    assert service.recall("What keeps delaying access?", "shared") == ([], "disabled")
    assert service.remember([finding()], "shared") == "disabled"


@pytest.mark.parametrize("missing", [
    "MEM0_PROJECT_ID", "MEM0_ENVIRONMENT", "MEM0_API_KEY",
    "MEM0_LEDGER_DATABASE_URL", "MEM0_TELEMETRY",
])
def test_enabled_without_required_configuration_fails_closed(monkeypatch, missing):
    monkeypatch.setenv("REPLIT_DEPLOYMENT", "1")
    for key, value in {
        "MEM0_ENABLED": "true", "MEM0_PROJECT_ID": "project_alpha",
        "MEM0_ENVIRONMENT": "production", "MEM0_API_KEY": "synthetic-not-a-real-key",
        "MEM0_LEDGER_DATABASE_URL": "postgresql://not-a-real-server/test",
        "MEM0_TELEMETRY": "false",
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv(missing)
    if missing == "MEM0_LEDGER_DATABASE_URL":
        monkeypatch.delenv("DATABASE_URL", raising=False)
    assert configured_semantic_memory().status == "unavailable"


def test_same_project_and_private_key_cannot_share_records_across_environments(context):
    _, key, development, provider, ledger, _ = context
    production = SemanticMemory(development.project, "production", provider, ledger)
    assert development._owner(key) != production._owner(key)
    assert development.remember([finding()], key) == "pending"
    assert production.remember([finding()], key) == "pending"
    assert len(ledger.rows) == 2
    assert {row["payload"]["environment"] for row in ledger.rows.values()} == {
        "development", "production",
    }
    assert all(row["status"] == "pending" for row in ledger.rows.values())
    provider.search.return_value = {"results": [match(development, key)]}
    assert production.recall("Earlier access blockers?", key) == ([], "ok")
    provider.search.return_value = {"results": [match(production, key)]}
    assert development.recall("Earlier access blockers?", key) == ([], "ok")


def test_structured_findings_are_sourced_timestamped_and_not_llm_extracted(context):
    data, _, _, _, _, _ = context
    facts = graph._facts_for_route("risk", "Sprint 26", data)
    records = extract_findings(data["Sprint 26"], facts, "Decision for SP-118: Use the sandbox fallback.")
    assert {record.kind for record in records} == {"recurring_blocker", "risk", "dependency", "decision"}
    assert all(record.source_ticket_ids for record in records)
    assert all(datetime.fromisoformat(record.observed_at).tzinfo for record in records)
    decision = next(record for record in records if record.kind == "decision")
    assert decision.evidence["source"] == "explicit_user_statement"
    no_decision = extract_findings(data["Sprint 26"], facts, "What should we decide?")
    assert not any(record.kind == "decision" for record in no_decision)
    unknown = extract_findings(data["Sprint 26"], facts, "Decision for XX-999: Invented ticket.")
    assert not any(record.kind == "decision" for record in unknown)


def test_fingerprint_ignores_recording_time_and_ticket_order(context):
    _, key, service, _, _, _ = context
    owner = service._owner(key)
    first = finding(source_ticket_ids=("SP-118", "SP-122"))
    second = finding(source_ticket_ids=("SP-122", "SP-118"), observed_at="2026-07-01T00:00:00+00:00")
    assert first.envelope("project_alpha", owner, "development")["finding_id"] == (
        second.envelope("project_alpha", owner, "development")["finding_id"]
    )
    assert finding(summary="New sourced evidence").envelope(
        "project_alpha", owner, "development"
    )["finding_id"] != first.envelope("project_alpha", owner, "development")["finding_id"]


def test_repeated_and_concurrent_creation_submits_once(context):
    _, key, service, provider, ledger, _ = context
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: service.remember([finding()], key), range(12)))
    assert provider.add.call_count == 1 and len(ledger.rows) == 1
    record = provider.add.call_args.args[0]
    assert record["source_ticket_ids"] == ["SP-118"]
    assert record["project_id"] == "project_alpha"
    assert key not in json.dumps(record)
    assert next(iter(ledger.rows.values()))["status"] == "pending"


def test_all_findings_are_queued_then_drained_in_bounded_batches(context):
    _, key, service, provider, ledger, _ = context
    findings = [finding(summary=f"Explicit finding {index}") for index in range(MAX_WRITES + 2)]
    assert service.remember(findings, key) == "pending"
    assert len(ledger.rows) == len(findings)
    assert provider.add.call_count == MAX_WRITES
    assert sum(row["status"] == "queued" for row in ledger.rows.values()) == 2
    assert service.remember([], key) == "pending"
    assert provider.add.call_count == len(findings)


def test_semantic_paraphrase_is_forwarded_and_relevant_result_reaches_graph(context):
    data, key, service, provider, _, model = context
    provider.search.return_value = {"results": [match(service, key)]}
    question = "Why does obtaining third-party access keep slowing us down?"
    result = graph.invoke_sprint_graph(question, "Sprint 26", data, key)
    assert provider.search.call_args.args[0] == question
    historical = model.call_args.args[1]["semantic_memory"]
    assert historical[0]["summary"] == finding().summary
    assert historical[0]["historical"] is True
    assert result["error"] is None
    assert result["semantic_memory_status"]["search"] == "ok"


def transformed_match(service, key, fact=None):
    row = match(service, key, fact)
    row["memory"] = row["metadata"]["summary"]
    row["metadata"]["source_ticket_ids"] = "SP-118"
    row["metadata"]["evidence"] = ["provider representation"]
    return row


def test_provider_changed_metadata_is_restored_from_scoped_ledger(context):
    _, key, service, provider, ledger, _ = context
    service.remember([finding()], key)
    provider.search.return_value = {"results": [transformed_match(service, key)]}
    records, status = service.recall("Why does partner access keep stalling?", key)
    assert status == "ok" and len(records) == 1
    assert records[0]["source_ticket_ids"] == ["SP-118"]
    assert records[0]["evidence"] == finding().evidence
    assert records[0]["historical"] and not records[0]["current_status_authority"]
    assert service.last_recall_diagnostics["restored_provenance"] == 1
    assert len(ledger.rows) == 1 and provider.add.call_count == 1


def test_transformed_metadata_enters_actual_graph_context_with_fresh_tools(context):
    data, key, service, provider, _, model = context
    service.remember([finding()], key)
    provider.search.return_value = {"results": [transformed_match(service, key)]}
    result = graph.invoke_sprint_graph("Which access dependencies recur historically?", "Sprint 26", data, key)
    facts = model.call_args.args[1]
    assert facts["semantic_memory"][0]["source_ticket_ids"] == ["SP-118"]
    assert facts["semantic_memory"][0]["observed_at"] == finding().observed_at
    assert facts["sprint"]["completion_rate"] == 66.7
    assert result["semantic_memory_status"]["search"] == "ok" and not result["error"]


@pytest.mark.parametrize("failure", ["missing", "queued", "foreign", "content", "fingerprint", "outage"])
def test_provenance_recovery_fails_closed(context, failure):
    _, key, service, provider, ledger, _ = context
    service.remember([finding()], key)
    row = transformed_match(service, key)
    stored = next(iter(ledger.rows.values()))
    if failure == "missing":
        ledger.rows.clear()
    elif failure == "queued":
        stored["status"] = "queued"
    elif failure == "foreign":
        stored["payload"]["project_id"] = "project_other"
    elif failure == "content":
        row["memory"] = "Unrelated content"
    elif failure == "fingerprint":
        stored["payload"]["evidence"] = {"source": "different"}
    elif failure == "outage":
        ledger.get_finding = Mock(side_effect=ConnectionError("private database details"))
    provider.search.return_value = {"results": [row]}
    records, status = service.recall("Recurring access delays?", key)
    assert not records
    assert status == ("unavailable" if failure == "outage" else "ok")


@pytest.mark.parametrize("scope", ["project_id", "owner_scope", "environment", "user_id", "app_id"])
def test_cross_scope_transformed_results_never_trigger_ledger_lookup(context, scope):
    _, key, service, provider, ledger, _ = context
    row = transformed_match(service, key)
    if scope in {"user_id", "app_id"}:
        row[scope] = "foreign"
    else:
        row["metadata"][scope] = "foreign"
    ledger.get_finding = Mock(side_effect=AssertionError("Forbidden lookup"))
    provider.search.return_value = {"results": [row]}
    assert service.recall("Recurring access delays?", key) == ([], "ok")
    ledger.get_finding.assert_not_called()
    assert service.last_recall_diagnostics["rejections"] == {"scope_mismatch": 1}


def test_remote_expiry_is_not_lost_during_provenance_restoration(context):
    _, key, service, provider, _, _ = context
    service.remember([finding()], key)
    row = transformed_match(service, key)
    row["metadata"]["expires_at"] = "2000-01-01T00:00:00+00:00"
    provider.search.return_value = {"results": [row]}
    assert service.recall("Old access findings?", key) == ([], "ok")
    assert service.last_recall_diagnostics["rejections"] == {"expired": 1}


def test_ledger_expiry_cannot_be_extended_by_remote_metadata(context):
    _, key, service, provider, ledger, _ = context
    service.remember([finding()], key)
    next(iter(ledger.rows.values()))["payload"]["expires_at"] = "2000-01-01T00:00:00+00:00"
    row = transformed_match(service, key)
    row["metadata"]["expires_at"] = "2999-01-01T00:00:00+00:00"
    provider.search.return_value = {"results": [row]}
    assert service.recall("Old access findings?", key) == ([], "ok")


def test_provenance_outage_recovers_without_stale_diagnostics(context):
    _, key, service, provider, ledger, _ = context
    service.remember([finding()], key)
    provider.search.return_value = {"results": [transformed_match(service, key)]}
    lookup = ledger.get_finding
    ledger.get_finding = Mock(side_effect=TimeoutError("private diagnostic"))
    assert service.recall("Earlier access?", key) == ([], "unavailable")
    ledger.get_finding = lookup
    assert len(service.recall("Earlier access?", key)[0]) == 1
    assert "unavailable" not in service.last_recall_diagnostics
    assert "private" not in json.dumps(service.last_recall_diagnostics)


@pytest.mark.parametrize("response", [[], {}, {"results": None}, {"results": "not a list"}])
def test_search_contract_rejects_unrecognized_response(context, response):
    _, key, service, provider, _, _ = context
    provider.search.return_value = response
    assert service.recall("Earlier access?", key) == ([], "unavailable")
    assert service.last_recall_diagnostics["rejections"] == {"unexpected_response_schema": 1}


def test_sdk_search_matches_documented_v3_parameters():
    sdk = Mock()
    sdk.search.return_value = {"results": []}
    adapter = HostedMem0("synthetic-not-a-real-key")
    adapter._client = sdk
    filters = {"AND": [{"user_id": "synthetic-owner"}, {"metadata": {"project_id": "synthetic"}}]}
    assert adapter.search("Paraphrased access delay?", filters) == {"results": []}
    sdk.search.assert_called_once_with(
        "Paraphrased access delay?", filters=filters, top_k=3, threshold=0.1, show_expired=False,
    )


def test_pending_ledger_does_not_resurrect_an_absent_remote_record(context):
    _, key, service, provider, ledger, _ = context
    service.remember([finding()], key)
    ledger.get_finding = Mock(side_effect=AssertionError("No remote candidate"))
    provider.search.return_value = {"results": []}
    assert service.recall("Previously deleted blocker?", key) == ([], "ok")
    ledger.get_finding.assert_not_called()
    assert service.remember([finding()], key) == "unchanged"
    provider.add.assert_called_once()


@pytest.mark.parametrize("score,accepted", [(.2717, True), (.1, True), (.099, False), (-.1, False), (1.1, False)])
def test_v3_hybrid_score_uses_documented_cutoff(context, score, accepted):
    _, key, service, provider, _, _ = context
    row = match(service, key)
    row["score"] = score
    provider.search.return_value = {"results": [row]}
    records, status = service.recall("Which access permissions repeatedly delayed work?", key)
    assert status == "ok" and bool(records) is accepted


def test_recovered_provenance_duplicate_and_low_score_are_bounded(context):
    _, key, service, provider, _, _ = context
    service.remember([finding()], key)
    row = transformed_match(service, key)
    weak = copy.deepcopy(row)
    weak["score"] = .05
    provider.search.return_value = {"results": [weak, row, copy.deepcopy(row)]}
    assert len(service.recall("Repeated partner access trouble?", key)[0]) == 1
    assert service.last_recall_diagnostics["rejections"] == {"low_score": 1, "duplicate": 1}


@pytest.mark.parametrize("scope", ["project", "owner", "environment"])
def test_scope_filters_and_return_validation_reject_cross_scope_results(context, scope):
    _, key, service, provider, _, _ = context
    other = SemanticMemory(
        "project_beta" if scope == "project" else service.project,
        "production" if scope == "environment" else service.environment,
        provider, Ledger(),
    )
    other_key = new_conversation_key() if scope == "owner" else key
    provider.search.return_value = {"results": [match(other, other_key)]}
    assert service.recall("Recurring access problems?", key)[0] == []
    filters = provider.search.call_args.args[1]["AND"]
    assert {"metadata": {"project_id": service.project}} in filters
    assert {"user_id": service._owner(key)} in filters
    assert {"metadata": {"environment": "development"}} in filters


def test_new_keys_do_not_share_records_and_predictable_keys_are_rejected(context):
    _, key, service, provider, ledger, _ = context
    other = new_conversation_key()
    service.remember([finding()], key)
    service.remember([finding()], other)
    assert len(ledger.rows) == 2
    assert service.recall("Remember?", "shared") == ([], "unavailable")
    assert service.remember([finding()], "shared") == "unavailable"
    assert provider.search.call_count == 0


def test_duplicate_low_score_and_expired_results_are_filtered(context):
    _, key, service, provider, _, _ = context
    valid = match(service, key)
    expired = match(service, key, finding(summary="Expired"), expires_at="2001-01-01T00:00:00+00:00")
    weak = match(service, key, finding(summary="Unrelated"))
    weak["score"] = .05
    provider.search.return_value = {"results": [valid, copy.deepcopy(valid), expired, weak]}
    records, status = service.recall("Recurring partner access issues?", key)
    assert status == "ok" and len(records) == 1


def test_stale_memory_never_replaces_current_status_or_metrics(context):
    data, key, service, provider, _, model = context
    provider.search.return_value = {"results": [match(
        service, key, finding(summary="SP-118 was blocked; completion was 10%.",
                            observed_at="2000-01-01T00:00:00+00:00"),
    )]}
    updated = {name: frame.copy(deep=True) for name, frame in data.items()}
    updated["Sprint 26"].loc[updated["Sprint 26"]["ticket_id"] == "SP-118", "status"] = "Done"
    result = graph.invoke_sprint_graph("What is SP-118 status and completion now?", "Sprint 26", updated, key)
    facts = model.call_args.args[1]
    assert facts["sprint"]["completion_rate"] == 70.8
    assert facts["sprint"]["blocked_count"] == 1
    assert "completion was 10%" in facts["semantic_memory"][0]["summary"]
    assert facts["semantic_memory"][0]["current_status_authority"] is False
    assert result["tool_outputs"]["sprint"]["completion_rate"] == 70.8
    assert "semantic_memory" not in result["tool_outputs"]


def test_search_failure_clears_context_and_next_request_recovers(context):
    data, key, service, provider, _, model = context
    provider.search.side_effect = [TimeoutError("private diagnostic must not leak"), {"results": [match(service, key)]}]
    first = graph.invoke_sprint_graph("Show blocker history", "Sprint 26", data, key)
    assert first["error"] is None and first["error_count"] == 0
    assert "semantic_memory" not in model.call_args.args[1]
    second = graph.invoke_sprint_graph("Compare earlier risks", "Sprint 26", data, key)
    assert second["route"] == "compare" and second["errors"] == []
    assert second["semantic_memory_status"]["search"] == "ok"
    assert model.call_args.args[1]["semantic_memory"]


def test_success_then_failure_does_not_reuse_stale_semantic_results(context):
    data, key, service, provider, _, model = context
    provider.search.side_effect = [{"results": [match(service, key)]}, RuntimeError("offline")]
    graph.invoke_sprint_graph("Show blocker history", "Sprint 26", data, key)
    graph.invoke_sprint_graph("Show current completion metrics", "Sprint 26", data, key)
    assert "semantic_memory" not in model.call_args.args[1]


def test_ambiguous_write_is_not_retried_but_new_work_recovers(context, caplog):
    _, key, service, provider, ledger, _ = context
    provider.add.side_effect = TimeoutError("SENSITIVE-SYNTHETIC-DIAGNOSTIC")
    assert service.remember([finding()], key) == "unavailable"
    assert next(iter(ledger.rows.values()))["status"] == "unknown"
    provider.add.side_effect = None
    assert service.remember([finding()], key) == "unchanged"
    assert provider.add.call_count == 1
    assert service.remember([finding(summary="New sourced observation")], key) == "pending"
    assert provider.add.call_count == 2
    assert "SENSITIVE-SYNTHETIC-DIAGNOSTIC" not in caplog.text and key not in caplog.text


def test_ledger_unavailable_means_no_provider_access(context):
    _, key, service, provider, ledger, _ = context
    ledger.ready.side_effect = ConnectionError("unavailable")
    assert service.recall("Recurring issues?", key) == ([], "unavailable")
    assert service.remember([finding()], key) == "unavailable"
    provider.search.assert_not_called()
    provider.add.assert_not_called()


def test_missing_sdk_or_failed_initialization_never_claims_a_write(context):
    _, key, service, provider, ledger, _ = context
    provider.ready.side_effect = ImportError("Optional SDK missing")
    assert service.remember([finding()], key) == "unavailable"
    assert not ledger.rows
    provider.add.assert_not_called()
    provider.ready.side_effect = None
    assert service.remember([finding()], key) == "pending"


def test_failed_sprint_tools_do_not_create_memories_and_next_turn_recovers(context, monkeypatch):
    data, key, _, provider, ledger, _ = context
    original = graph.overdue_tasks
    monkeypatch.setattr(graph, "overdue_tasks", Mock(side_effect=RuntimeError("tool failure")))
    failed = graph.invoke_sprint_graph("Show blockers", "Sprint 26", data, key)
    assert failed["error"] and failed["semantic_memory_status"]["write"] == "skipped"
    assert not ledger.rows
    monkeypatch.setattr(graph, "overdue_tasks", original)
    recovered = graph.invoke_sprint_graph("Compare historical risks", "Sprint 26", data, key)
    assert recovered["route"] == "compare" and recovered["error"] is None
    assert recovered["error_count"] == 0 and recovered["errors"] == []
    assert ledger.rows and provider.add.called


def test_model_prompt_marks_semantic_records_as_historical_not_current(monkeypatch):
    client = Mock()
    client.invoke.return_value.content = "Grounded"
    monkeypatch.setattr(llm, "_client", lambda: client)
    llm.generate_grounded_text("Current status?", {
        "sprint": {"completion_rate": 70.8},
        "semantic_memory": [{"summary": "Old completion was 10%."}],
    })
    messages = client.invoke.call_args.args[0]
    current = messages[1][1].split("CURRENT tool outputs (JSON):\n")[1].split(
        "\n\nRELEVANT CHECKPOINT HISTORY"
    )[0]
    assert json.loads(current) == {"sprint": {"completion_rate": 70.8}}
    assert "historical observations only" in messages[1][1]
    assert "CURRENT tool outputs always take precedence" in messages[0][1]


def test_sdk_add_disables_inference_and_supplies_all_isolation_metadata(context):
    _, key, service, _, _, _ = context
    sdk = Mock()
    sdk.add.return_value = {"status": "PENDING", "event_id": "test-event"}
    adapter = HostedMem0("synthetic-not-a-real-key")
    adapter._client = sdk
    record = finding().envelope(service.project, service._owner(key), service.environment)
    adapter.add(record)
    assert sdk.add.call_args.kwargs["infer"] is False
    assert sdk.add.call_args.kwargs["user_id"] == record["owner_scope"]
    assert sdk.add.call_args.kwargs["app_id"] == service.project
    assert sdk.add.call_args.kwargs["metadata"] == record
    assert key not in json.dumps(sdk.add.call_args.kwargs)


@pytest.mark.parametrize("status", [None, "SUCCEEDED"])
def test_synchronous_acknowledgment_retains_duplicate_guard(context, status):
    _, key, service, provider, ledger, _ = context
    response = {"results": [{
        "id": "synthetic-remote-id", "event": "ADD",
        "data": {"memory": finding().summary},
    }]}
    if status:
        response["status"] = status
    provider.add.return_value = response
    assert service.remember([finding()], key) == "pending"
    row = next(iter(ledger.rows.values()))
    assert row["status"] == "pending" and row["event_id"] is None
    assert service.remember([finding()], key) == "unchanged"
    provider.add.assert_called_once()


def test_async_acknowledgment_records_event_id(context):
    _, key, service, _, ledger, _ = context
    assert service.remember([finding()], key) == "pending"
    assert next(iter(ledger.rows.values()))["event_id"] == "test-event"


@pytest.mark.parametrize("response", [
    None, [], "success", {}, {"message": "saved"},
    {"status": "PENDING"}, {"status": "PENDING", "event_id": " "},
    {"status": "SUCCEEDED"}, {"results": []}, {"results": [None]},
    {"results": [{"id": "remote", "event": "ADD"}]},
    {"results": [{"id": "", "event": "ADD", "data": {"memory": "other"}}]},
    {"status": "FAILED", "results": [{"id": "remote", "event": "ADD"}]},
    {"results": [{"id": "remote", "event": "DELETE", "data": {"memory": finding().summary}}]},
    {"results": [{"id": "remote", "event": "ADD", "data": {"memory": "Unrelated finding"}}]},
])
def test_unrecognized_acknowledgment_is_unknown_and_never_resubmitted(context, response):
    _, key, service, provider, ledger, _ = context
    provider.add.return_value = response
    assert service.remember([finding()], key) == "unavailable"
    assert next(iter(ledger.rows.values()))["status"] == "unknown"
    assert service.remember([finding()], key) == "unchanged"
    provider.add.assert_called_once()


@pytest.mark.parametrize("committed", [False, True])
def test_finalization_failure_does_not_repeat_remote_write(context, committed):
    _, key, service, provider, ledger, _ = context
    original = ledger.finish

    def failing_finish(identity, status, event_id=None):
        row = ledger.rows[identity]
        if row["status"] != "reserved":
            raise ValueError("Already finalized")
        if status == "pending":
            if committed:
                original(identity, status, event_id)
            raise ConnectionError("Uncertain commit")
        original(identity, status, event_id)

    ledger.finish = failing_finish
    assert service.remember([finding()], key) == "unavailable"
    row = next(iter(ledger.rows.values()))
    assert row["status"] == ("pending" if committed else "unknown")
    assert row["event_id"] == ("test-event" if committed else None)
    assert service.remember([finding()], key) == "unchanged"
    provider.add.assert_called_once()


def test_entire_ledger_outage_after_add_leaves_reserved_no_retry(context):
    _, key, service, provider, ledger, _ = context
    ledger.finish = Mock(side_effect=ConnectionError("offline"))
    assert service.remember([finding()], key) == "unavailable"
    assert next(iter(ledger.rows.values()))["status"] == "reserved"
    assert service.remember([finding()], key) == "unchanged"
    provider.add.assert_called_once()


def test_project_switch_does_not_leak_via_checkpoint_answers(context, monkeypatch):
    data, key, _, _, ledger, model = context
    model.return_value = ("ALPHA-PRIVATE-HISTORICAL-ANSWER", "test")
    graph.invoke_sprint_graph("Show SP-118 blockers", "Sprint 26", data, key)
    provider = Mock()
    provider.search.return_value = {"results": []}
    provider.add.return_value = {"status": "PENDING", "event_id": "test"}
    beta = SemanticMemory("project_beta", "development", provider, ledger)
    monkeypatch.setattr(graph, "configured_semantic_memory", lambda: beta)
    monkeypatch.setenv("MEM0_PROJECT_ID", "project_beta")
    with pytest.raises(ValueError, match="Conversation unavailable"):
        graph.restore_conversation(key)
    graph.invoke_sprint_graph("Explain those SP-118 blockers", "Sprint 26", data, key)
    assert "ALPHA-PRIVATE" not in json.dumps(model.call_args.args)
    assert "conversation_history" not in model.call_args.args[1]
