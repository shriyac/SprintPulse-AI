from contextlib import closing
from pathlib import Path
import sqlite3
from unittest.mock import Mock

import pandas as pd
import pytest
from langgraph.checkpoint.sqlite import SqliteSaver

import agents.graph as graph_module
from tools.sprint_data import load_sprint_data

ROOT = Path(__file__).parents[1]


@pytest.fixture
def request_context(tmp_path, monkeypatch):
    snapshots = load_sprint_data(ROOT / "data")
    checkpoint_path = tmp_path / "checkpoints.sqlite"
    model = Mock(return_value=(None, "test fallback"))
    monkeypatch.setattr(graph_module, "CHECKPOINT_PATH", checkpoint_path)
    monkeypatch.setattr(graph_module, "generate_grounded_text", model)
    return snapshots, checkpoint_path, model


def checkpoint_history(snapshots, checkpoint_path, thread_id):
    with closing(sqlite3.connect(checkpoint_path, check_same_thread=False)) as connection:
        saver = SqliteSaver(connection)
        graph = graph_module.build_sprint_graph(snapshots, saver)
        return list(graph.get_state_history({"configurable": {"thread_id": thread_id}}))


def test_shared_thread_routes_each_latest_request(request_context, monkeypatch):
    snapshots, _, _ = request_context
    gather = Mock(wraps=graph_module._facts_for_route)
    monkeypatch.setattr(graph_module, "_facts_for_route", gather)
    questions = [
        ("What is the current sprint health?", "question"),
        ("Which tasks are blocked across multiple sprints?", "risk"),
        ("Generate the weekly project status report.", "report"),
        ("Show completion metrics", "metrics"),
    ]
    for question, expected_route in questions:
        result = graph_module.invoke_sprint_graph(
            question, "Sprint 26", snapshots, thread_id="shared-thread"
        )
        assert result["route"] == expected_route
        assert not result["error"]
        assert result["tool_outputs"]["sprint"]["completion_rate"] == 66.7
        assert bool(result["report"]) == (expected_route == "report")
    # These are the routes supplied by the evidence nodes actually executed,
    # not just labels returned in the final response.
    assert [call.args[0] for call in gather.call_args_list] == [
        "question", "risk", "report", "metrics"
    ]


def test_success_after_tool_failure_selects_new_tools(request_context, monkeypatch):
    snapshots, checkpoint_path, model = request_context
    original_overdue = graph_module.overdue_tasks
    overdue_calls = 0

    def fail_once(frame):
        nonlocal overdue_calls
        overdue_calls += 1
        if overdue_calls == 1:
            raise RuntimeError("Injected overdue tool failure")
        return original_overdue(frame)

    comparison = Mock(wraps=graph_module.historical_comparison)
    gather = Mock(wraps=graph_module._facts_for_route)
    monkeypatch.setattr(graph_module, "overdue_tasks", fail_once)
    monkeypatch.setattr(graph_module, "historical_comparison", comparison)
    monkeypatch.setattr(graph_module, "_facts_for_route", gather)
    failed = graph_module.invoke_sprint_graph(
        "Show completion metrics", "Sprint 26", snapshots, thread_id="recover-thread"
    )
    assert failed["error_count"] == 1
    assert failed["error"]
    assert failed["tool_outputs"] == {}
    model.assert_not_called()
    comparison.assert_not_called()
    before_recovery = checkpoint_history(snapshots, checkpoint_path, "recover-thread")

    recovered = graph_module.invoke_sprint_graph(
        "Compare sprint history", "Sprint 26", snapshots, thread_id="recover-thread"
    )
    assert recovered["route"] == "compare"
    assert recovered["error"] is None
    assert recovered["errors"] == []
    assert recovered["error_count"] == 0
    assert recovered["generation_mode"] == "test fallback"
    assert recovered["report"] == ""
    assert recovered["tool_outputs"]["historical_comparison"][-1]["completion_rate"] == 66.7
    assert [call.args[0] for call in gather.call_args_list] == ["metrics", "compare"]
    comparison.assert_called_once()
    model.assert_called_once()
    assert overdue_calls == 2
    after_recovery = checkpoint_history(snapshots, checkpoint_path, "recover-thread")
    assert {
        item.config["configurable"]["checkpoint_id"] for item in before_recovery
    }.issubset({
        item.config["configurable"]["checkpoint_id"] for item in after_recovery
    })
    assert any(
        item.values.get("error") == failed["error"] for item in after_recovery
    )


def test_conversation_turns_remain_in_existing_checkpoint_history(request_context):
    snapshots, checkpoint_path, _ = request_context
    first_question = "Show completion metrics"
    first = graph_module.invoke_sprint_graph(
        first_question, "Sprint 26", snapshots, thread_id="conversation"
    )
    first_history = checkpoint_history(snapshots, checkpoint_path, "conversation")
    first_checkpoint = first_history[0]
    second_question = "Which tasks are blocked across multiple sprints?"
    second = graph_module.invoke_sprint_graph(
        second_question, "Sprint 26", snapshots, thread_id="conversation"
    )
    history = checkpoint_history(snapshots, checkpoint_path, "conversation")
    first_ids = {item.config["configurable"]["checkpoint_id"] for item in first_history}
    later_ids = {item.config["configurable"]["checkpoint_id"] for item in history}
    assert first_ids.issubset(later_ids)
    preserved = next(
        item for item in history
        if item.config["configurable"]["checkpoint_id"]
        == first_checkpoint.config["configurable"]["checkpoint_id"]
    )
    assert preserved.values == first_checkpoint.values
    assert preserved.values["question"] == first_question
    assert preserved.values["response"] == first["response"]
    assert history[0].values["question"] == second_question
    assert history[0].values["response"] == second["response"]
    assert len(history) > len(first_history)


def test_historical_sprint_data_is_unchanged_across_requests(request_context):
    snapshots, _, _ = request_context
    original_frames = {name: frame.copy(deep=True) for name, frame in snapshots.items()}
    original_files = {
        path: path.read_bytes() for path in (ROOT / "data").glob("sprint_*.csv")
    }
    graph_module.invoke_sprint_graph(
        "Show blockers", "Sprint 25", snapshots, thread_id="historical-data"
    )
    compared = graph_module.invoke_sprint_graph(
        "Compare sprint history", "Sprint 26", snapshots, thread_id="historical-data"
    )
    assert [row["sprint_name"] for row in compared["tool_outputs"]["historical_comparison"]] == [
        "Sprint 24", "Sprint 25", "Sprint 26"
    ]
    assert [row["completion_rate"] for row in compared["tool_outputs"]["historical_comparison"]] == [
        41.7, 54.2, 66.7
    ]
    assert {
        row["ticket_id"]: row["appearances"]
        for row in compared["tool_outputs"]["recurring_blockers"]
    } == {"SP-118": 3, "SP-122": 3, "SP-124": 2}
    reloaded = load_sprint_data(ROOT / "data")
    for name, original in original_frames.items():
        pd.testing.assert_frame_equal(snapshots[name], original)
        pd.testing.assert_frame_equal(reloaded[name], original)
    assert all(path.read_bytes() == content for path, content in original_files.items())


def test_every_request_scoped_field_is_replaced_before_execution(request_context, monkeypatch):
    snapshots, checkpoint_path, _ = request_context
    config = {"configurable": {"thread_id": "stale-fields"}}
    stale = {
        "question": "Old report",
        "sprint_name": "Sprint 25",
        "route": "report",
        "tool_outputs": {"stale": True},
        "response": "Old answer",
        "report": "Old report content",
        "generation_mode": "old mode",
        "error_count": 2,
        "errors": ["Old error"],
        "error": "Old blocking error",
        "thread_id": "persistent-thread-marker",
    }
    with closing(sqlite3.connect(checkpoint_path, check_same_thread=False)) as connection:
        saver = SqliteSaver(connection)
        saver.setup()
        graph = graph_module.build_sprint_graph(snapshots, saver)
        graph.update_state(config, stale, as_node="report")

    original_build = graph_module.build_sprint_graph
    inputs = []

    class InspectInput:
        def __init__(self, compiled):
            self.compiled = compiled

        def invoke(self, state, config):
            inputs.append(state.copy())
            return self.compiled.invoke(state, config=config)

    monkeypatch.setattr(
        graph_module, "build_sprint_graph",
        lambda *args, **kwargs: InspectInput(original_build(*args, **kwargs)),
    )
    result = graph_module.invoke_sprint_graph(
        "Show completion metrics", "Sprint 26", snapshots, thread_id="stale-fields"
    )
    assert inputs == [{
        "question": "Show completion metrics",
        "sprint_name": "Sprint 26",
        "route": "metrics",
        "tool_outputs": {},
        "response": "",
        "report": "",
        "generation_mode": "",
        "error_count": 0,
        "errors": [],
        "error": None,
    }]
    assert result["route"] == "metrics"
    assert result["report"] == ""
    assert result["error"] is None
    # Restore the unwrapped builder to inspect the real saved state.
    monkeypatch.setattr(graph_module, "build_sprint_graph", original_build)
    history = checkpoint_history(snapshots, checkpoint_path, "stale-fields")
    assert history[0].values["thread_id"] == "persistent-thread-marker"
    assert any(item.values.get("report") == "Old report content" for item in history)


def test_route_override_applies_only_to_its_request(request_context):
    snapshots, _, _ = request_context
    report = graph_module.invoke_sprint_graph(
        "Prepare an update", "Sprint 26", snapshots,
        thread_id="override-thread", route_override="report",
    )
    assert report["route"] == "report"
    assert report["report"]
    ordinary = graph_module.invoke_sprint_graph(
        "What is the current sprint health?", "Sprint 26", snapshots,
        thread_id="override-thread",
    )
    assert ordinary["route"] == "question"
    assert ordinary["report"] == ""


@pytest.mark.parametrize("question", ["Show completion metrics", "Write the weekly report"])
def test_empty_facts_still_get_explicit_unavailable_message(request_context, monkeypatch, question):
    snapshots, _, model = request_context
    monkeypatch.setattr(graph_module, "_facts_for_route", lambda *args: {})
    result = graph_module.invoke_sprint_graph(
        question, "Sprint 26", snapshots, thread_id="empty-facts"
    )
    assert result["response"].startswith("No deterministic tool outputs are available;")
    assert result["generation_mode"] == "tools unavailable"
    model.assert_not_called()
