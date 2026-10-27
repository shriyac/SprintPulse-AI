from unittest.mock import Mock

import pytest

from scripts import validate_mem0_ack as validation


def test_ack_runner_refuses_production_before_client_creation(monkeypatch):
    monkeypatch.setenv("REPLIT_DEPLOYMENT", "1")
    client = Mock(side_effect=AssertionError("Network forbidden"))
    monkeypatch.setattr(validation, "OneWriteProvider", client)
    assert validation.run_validation()["status"] == "BLOCKED"
    client.assert_not_called()


def test_ack_runner_search_budget_is_one(monkeypatch):
    search = Mock(return_value={"results": []})
    monkeypatch.setattr(validation.BoundedProvider.__bases__[0], "search", search)
    provider = validation.OneWriteProvider("synthetic-key")
    provider.search("synthetic", {})
    with pytest.raises(RuntimeError, match="One semantic"):
        provider.search("synthetic", {})
    search.assert_called_once()


def test_ack_runner_add_budget_is_one(monkeypatch):
    add = Mock(return_value={"results": []})
    monkeypatch.setattr(validation.BoundedProvider.__bases__[0], "add", add)
    provider = validation.OneWriteProvider("synthetic-key")
    provider.add({})
    with pytest.raises(RuntimeError, match="exactly one"):
        provider.add({})
    add.assert_called_once()


def test_ack_runner_list_budget_is_four():
    provider = validation.OneWriteProvider("synthetic-key")
    provider._client = Mock()
    provider._client.get_all.return_value = {"results": []}
    for _ in range(4):
        assert provider.listed({}) == []
    with pytest.raises(RuntimeError, match="Four scoped"):
        provider.listed({})
    assert provider._client.get_all.call_count == 4


def test_cleanup_ownership_requires_every_scope_component():
    record = dict(project_id="synthetic", owner_scope="owner", environment="development", finding_id="finding")
    row = {"id": "synthetic-id", "user_id": "owner", "metadata": record}
    assert validation.owned(row, record)
    for key in record:
        assert not validation.owned({**row, "metadata": {**record, key: "different"}}, record)
    assert not validation.owned({**row, "user_id": "different"}, record)
