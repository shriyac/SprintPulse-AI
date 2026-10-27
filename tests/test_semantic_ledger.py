from unittest.mock import MagicMock
import json
import pytest

from agents.semantic_ledger import PostgresLedger


def ledger(monkeypatch):
    connection = MagicMock()
    connection.__enter__.return_value = connection
    store = PostgresLedger("synthetic-not-a-real-connection")
    monkeypatch.setattr(store, "_connection", lambda: connection)
    return store, connection


def test_readiness_never_creates_or_migrates_tables(monkeypatch):
    store, connection = ledger(monkeypatch)
    store.ready()
    query = connection.execute.call_args.args[0]
    assert query.startswith("SELECT")
    assert "CREATE" not in query and "ALTER" not in query


def test_enqueue_uses_unique_fingerprint_and_parameterized_payload(monkeypatch):
    store, connection = ledger(monkeypatch)
    record = {
        "finding_id": "fingerprint", "project_id": "project_a", "owner_scope": "owner_a",
        "environment": "development", "summary": "A quote '; DROP TABLE x; -- is data.",
    }
    store.enqueue([record])
    query, params = connection.execute.call_args.args
    assert "ON CONFLICT (finding_id) DO NOTHING" in query
    assert "DROP TABLE" not in query and json.loads(params[-1]) == record


def test_claim_is_atomic_and_scoped_to_project_owner_environment(monkeypatch):
    store, connection = ledger(monkeypatch)
    connection.execute.return_value.fetchone.return_value = ({"finding_id": "fingerprint"},)
    assert store.claim("project_a", "owner_a", "development") == {"finding_id": "fingerprint"}
    query, params = connection.execute.call_args.args
    assert "FOR UPDATE SKIP LOCKED" in query
    assert "status='reserved'" in query and "status='queued'" in query
    assert params == ("project_a", "owner_a", "development")


@pytest.mark.parametrize("status,event_id", [("pending", "synthetic-event"), ("pending", None), ("unknown", None)])
def test_finalization_only_transitions_reserved_claim(monkeypatch, status, event_id):
    store, connection = ledger(monkeypatch)
    connection.execute.return_value.rowcount = 1
    store.finish("synthetic-finding", status, event_id)
    sql, params = connection.execute.call_args.args
    assert "WHERE finding_id=%s AND status='reserved'" in sql
    assert params == (status, event_id, "synthetic-finding")
    connection.__exit__.assert_called_once_with(None, None, None)


def test_finalization_refuses_to_overwrite_already_committed_row(monkeypatch):
    store, connection = ledger(monkeypatch)
    connection.execute.return_value.rowcount = 0
    with pytest.raises(ValueError, match="not reserved"):
        store.finish("synthetic-finding", "unknown")
    assert connection.__exit__.call_args.args[0] is ValueError


@pytest.mark.parametrize("status,event_id", [("queued", None), ("reserved", None), ("unknown", "event")])
def test_invalid_finalization_never_opens_transaction(monkeypatch, status, event_id):
    store, connection = ledger(monkeypatch)
    with pytest.raises(ValueError):
        store.finish("synthetic-finding", status, event_id)
    connection.execute.assert_not_called()


def test_canonical_lookup_is_read_only_and_fully_scoped(monkeypatch):
    store, connection = ledger(monkeypatch)
    payload = {"finding_id": "synthetic"}
    connection.execute.return_value.fetchone.return_value = (payload,)
    assert store.get_finding("synthetic", "project", "owner", "development") == payload
    sql, params = connection.execute.call_args.args
    assert sql.strip().startswith("SELECT payload")
    assert "finding_id=%s AND project_id=%s AND owner_scope=%s" in sql
    assert "environment=%s" in sql and "'queued'" not in sql
    assert params == ("synthetic", "project", "owner", "development")


def test_canonical_lookup_does_not_invent_missing_provenance(monkeypatch):
    store, connection = ledger(monkeypatch)
    connection.execute.return_value.fetchone.return_value = None
    assert store.get_finding("synthetic", "project", "owner", "development") is None
