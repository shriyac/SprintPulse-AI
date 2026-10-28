from pathlib import Path

from agents.graph import build_sprint_graph, classify_route
from reports.publisher import save_approved_report
from tools.sprint_data import load_sprint_data


def test_question_routing_is_conditional_by_intent():
    assert classify_route("Compare completion history") == "compare"
    assert classify_route("What risks and blockers are open?") == "risk"
    assert classify_route("Write the weekly report") == "report"
    assert classify_route("How many tickets are completed?") == "metrics"


def test_graph_builds_with_checkpoint_optional_and_completes_fallback(tmp_path, monkeypatch):
    import agents.graph as graph_module

    sprints = load_sprint_data(Path(__file__).parents[1] / "data")
    monkeypatch.setattr(graph_module, "CHECKPOINT_PATH", tmp_path / "checkpoints.sqlite")
    monkeypatch.setattr(graph_module, "generate_grounded_text", lambda task, facts: (None, "test fallback"))
    result = graph_module.invoke_sprint_graph(
        "Show completion metrics",
        "Sprint 26",
        sprints,
        thread_id="pytest-metrics",
    )
    assert result["route"] == "metrics"
    assert result["tool_outputs"]["sprint"]["completion_rate"] == 66.7
    assert "66.7%" in result["response"]
    assert (tmp_path / "checkpoints.sqlite").exists()


def test_report_is_saved_only_when_explicit_save_function_is_called(tmp_path):
    destination = tmp_path / "approved"
    assert list(destination.glob("*.md")) == []
    saved = save_approved_report("# Sprint 26\n\nApproved.", "Sprint 26", destination)
    assert saved.exists()
    assert saved.read_text(encoding="utf-8").startswith("# Sprint 26")
