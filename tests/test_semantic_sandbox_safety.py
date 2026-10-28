from unittest.mock import MagicMock, Mock

import pytest

from scripts import validate_mem0_sandbox as sandbox


def scope_record():
    return {
        "finding_id": "synthetic-fingerprint", "project_id": "synthetic_project_test",
        "owner_scope": "synthetic_owner", "environment": "development",
    }


def test_live_runner_refuses_published_environment(monkeypatch):
    monkeypatch.setenv("REPLIT_DEPLOYMENT", "1")
    monkeypatch.setattr(sandbox, "BoundedProvider", Mock(side_effect=AssertionError("Network forbidden")))
    assert sandbox.run_validation()["status"] == "BLOCKED"


def test_live_runner_requires_editor_domain(monkeypatch):
    monkeypatch.delenv("REPLIT_DEPLOYMENT", raising=False)
    monkeypatch.delenv("REPLIT_DEV_DOMAIN", raising=False)
    assert sandbox.run_validation()["reason"] == "Production execution refused."


def test_provider_enforces_single_add_without_exposing_key(monkeypatch):
    add = Mock(return_value={"status": "PENDING", "event_id": "synthetic"})
    monkeypatch.setattr(sandbox.HostedMem0, "add", add)
    provider = sandbox.BoundedProvider("SYNTHETIC-TEST-KEY")
    provider.add({})
    with pytest.raises(RuntimeError, match="exactly one"):
        provider.add({})
    assert add.call_count == 1
    assert "SYNTHETIC" not in str(provider.write_acknowledgment)


def test_cleanup_deletes_only_owned_record_and_parameterized_ledger_row():
    record = scope_record()
    owned = {"id": "synthetic-remote-id", "user_id": record["owner_scope"], "metadata": record}
    foreign = {"id": "foreign", "user_id": "another-owner", "metadata": record}
    provider = Mock()
    provider.listed.side_effect = [[foreign, owned], []]
    provider.counts = {"add_attempts": 1}
    provider.write_error = {}
    ledger = Mock()
    connection = MagicMock()
    connection.__enter__.return_value = connection
    ledger._connection.return_value = connection
    result = sandbox.cleanup(provider, ledger, record)
    assert result["status"] == "PASS"
    provider.delete_exact.assert_called_once_with("synthetic-remote-id")
    query, params = connection.execute.call_args.args
    assert "WHERE finding_id=%s AND project_id=%s AND owner_scope=%s AND environment=%s" in query
    assert params == tuple(record.values())


def test_uncertain_ingestion_without_visible_record_keeps_ledger():
    provider = Mock()
    provider.listed.return_value = []
    provider.counts = {"add_attempts": 1}
    provider.write_error = {}
    ledger = Mock()
    result = sandbox.cleanup(provider, ledger, scope_record())
    assert result["status"] == "PARTIAL" and result["uncertain_ingestion_retained"]
    ledger._connection.assert_not_called()
    provider.delete_exact.assert_not_called()


def test_sanitized_error_never_contains_connection_string_or_key():
    details = sandbox.safe_error(ValueError("SYNTHETIC-KEY postgres://private-connection"))
    assert details == {"type": "ValueError"}


def test_acknowledgment_diagnostics_discard_values_and_unknown_keys():
    private = "SENSITIVE-SYNTHETIC-PRIVATE"
    shape = sandbox.acknowledgment_shape({
        "status": "SUCCEEDED", "message": private, "event_id": private,
        private: private, "results": [{
            "id": private, "event": private, "data": {"memory": private},
            private: private,
        }],
    })
    assert shape == {
        "response_type": "object",
        "fields": {"status": "string", "event_id": "string", "message": "string", "results": "array"},
        "status_category": "SUCCEEDED", "result_count": 1,
        "result_fields": [{"id": "string", "event": "string", "data": "object"}],
    }
    assert private not in str(shape)
    assert sandbox.acknowledgment_shape({"status": private})["status_category"] == "absent_or_other"


def test_ledger_diagnostics_record_commit_failure_without_sensitive_values(monkeypatch):
    monkeypatch.setattr(sandbox.PostgresLedger, "finish", Mock(
        side_effect=ConnectionError("SENSITIVE-DSN-KEY"),
    ))
    ledger = sandbox.DiagnosticLedger("SENSITIVE-DSN-KEY")
    with pytest.raises(ConnectionError):
        ledger.finish("private-fingerprint", "pending", "private-event")
    assert ledger.finalizations == [{
        "target_status": "pending", "has_event_id": True,
        "outcome": "uncertain", "error": {"type": "ConnectionError"},
    }]
