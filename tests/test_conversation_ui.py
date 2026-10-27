from pathlib import Path
from unittest.mock import Mock

import pytest
from streamlit.testing.v1 import AppTest

import agents.graph as graph
import reports.publisher as publisher
from agents.memory import valid_conversation_key

ROOT = Path(__file__).parents[1]


def button(app, label):
    return next(item for item in app.button if item.label == label)


def text(app, label):
    return next(item for item in app.text_input if item.label == label)


def run(app):
    app.run(timeout=30)
    assert not app.exception
    return app


def ask(app, question):
    text(app, "Your question").set_value(question)
    button(app, "Ask SprintPulse").click()
    return run(app)


def resume(app, key):
    text(app, "Private resume key").set_value(key)
    button(app, "Resume conversation").click()
    return run(app)


@pytest.fixture
def ui(tmp_path, monkeypatch):
    model = Mock(return_value=("Synthetic SP-118 checkpoint finding.", "test model"))
    monkeypatch.setattr(graph, "CHECKPOINT_PATH", tmp_path / "ui.sqlite")
    monkeypatch.setattr(graph, "generate_grounded_text", model)
    return model


def test_fresh_session_can_resume_and_automatically_recall_previous_findings(ui):
    first = run(AppTest.from_file(str(ROOT / "app.py")))
    assert [tab.label for tab in first.tabs] == ["Sprint Dashboard", "AI Assistant", "Weekly Reports"]
    ask(first, "Show SP-118 blockers")
    key = first.session_state["thread_id"]
    assert valid_conversation_key(key)
    saved = first.session_state["last_answer"]

    fresh = run(AppTest.from_file(str(ROOT / "app.py")))
    assert fresh.session_state["thread_id"] != key
    resume(fresh, key)
    assert fresh.session_state["thread_id"] == key
    assert fresh.session_state["last_answer"] == saved
    assert fresh.session_state["conversation_restored"] is True
    ask(fresh, "Explain that finding")
    assert fresh.session_state["last_answer"]["recalled_turns"] == 1
    assert ui.call_args.args[1]["conversation_history"][0]["answer"] == saved["response"]
    assert fresh.session_state["conversation_restored"] is False


def test_resume_restores_sprint_context_and_rerun_keeps_the_same_thread(ui):
    first = run(AppTest.from_file(str(ROOT / "app.py")))
    next(item for item in first.selectbox if item.label == "Sprint context").select("Sprint 25")
    # Form values are submitted together; an intervening rerun discards edits.
    ask(first, "Show completion metrics")
    key = first.session_state["thread_id"]
    fresh = run(AppTest.from_file(str(ROOT / "app.py")))
    resume(fresh, key)
    assert fresh.session_state["assistant_sprint"] == "Sprint 25"
    run(fresh)
    assert fresh.session_state["thread_id"] == key
    ask(fresh, "Show completion metrics again")
    assert fresh.session_state["last_answer"]["tool_outputs"]["sprint"]["completion_rate"] == 54.2


def test_invalid_resume_does_not_switch_threads_or_discard_current_draft(ui):
    app = run(AppTest.from_file(str(ROOT / "app.py")))
    ask(app, "Show blockers")
    key = app.session_state["thread_id"]
    button(app, "Generate draft").click()
    run(app)
    pending = app.session_state["pending_report"]
    resume(app, "shared")
    assert app.error
    assert app.session_state["thread_id"] == key
    assert app.session_state["pending_report"] == pending


def test_new_conversation_is_isolated_and_old_history_can_be_resumed(ui):
    app = run(AppTest.from_file(str(ROOT / "app.py")))
    ask(app, "Show SP-118 blockers")
    key = app.session_state["thread_id"]
    button(app, "Generate draft").click()
    run(app)
    button(app, "New conversation").click()
    run(app)
    assert app.session_state["thread_id"] != key
    ask(app, "Explain that finding")
    assert app.session_state["last_answer"]["recalled_turns"] == 0
    resume(app, key)
    assert app.session_state["thread_id"] == key
    assert app.session_state["pending_report"] is None
    assert app.session_state["approved_report"] is None
    assert graph.restore_conversation(key)["report"]


def test_report_still_requires_approval_and_resuming_never_autoapproves(ui, tmp_path, monkeypatch):
    destination = tmp_path / "approved"
    save = publisher.save_approved_report
    monkeypatch.setattr(
        publisher, "save_approved_report",
        lambda report, report_sprint, reports_dir: save(report, report_sprint, destination),
    )
    app = run(AppTest.from_file(str(ROOT / "app.py")))
    key = app.session_state["thread_id"]
    button(app, "Generate draft").click()
    run(app)
    assert not list(destination.glob("*.md"))
    assert app.session_state["pending_report"]["route"] == "report"
    assert app.session_state["approved_report"] is None
    button(app, "Approve and save").click()
    run(app)
    saved = list(destination.glob("*.md"))
    assert len(saved) == 1
    assert app.session_state["pending_report"] is None
    fresh = run(AppTest.from_file(str(ROOT / "app.py")))
    resume(fresh, key)
    assert fresh.session_state["pending_report"] is None
    assert fresh.session_state["approved_report"] is None
    assert not any(item.label == "Approve and save" for item in fresh.button)
    assert saved[0].is_file()
