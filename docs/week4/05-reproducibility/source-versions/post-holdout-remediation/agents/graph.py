from __future__ import annotations

import os
import re
import sqlite3
import uuid
from contextlib import suppress
from pathlib import Path
from typing import Any, Literal, TypedDict

import pandas as pd
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langchain_core.runnables import RunnableConfig

from agents.llm import generate_grounded_text
from agents.answer_rendering import render_answer
from agents.memory import (
    completed_turns, fallback_recall, project_turns, relevant_turns, valid_conversation_key,
)
from agents.findings import extract_findings
from agents.semantic_memory import (
    DisabledMemory, configured_project_scope, configured_semantic_memory, historical_semantic_excerpt,
)
from tools.sprint_metrics import (
    blocker_durations,
    historical_comparison,
    overdue_tasks,
    recurring_blockers,
    risk_flags,
    sprint_metrics,
)

Route = Literal["metrics", "risk", "compare", "report", "question"]
MAX_ERRORS = 2
ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT_PATH = Path(os.getenv("SPRINTPULSE_CHECKPOINT_DB", str(ROOT / "data" / "checkpoints.sqlite")))


class SprintState(TypedDict, total=False):
    question: str
    sprint_name: str
    route: Route
    tool_outputs: dict[str, Any]
    response: str
    report: str
    generation_mode: str
    error_count: int
    errors: list[str]
    error: str | None
    thread_id: str
    conversation_context: list[dict[str, Any]]
    semantic_context: list[dict[str, Any]]
    semantic_memory_status: dict[str, str]
    memory_project_scope: str | None


def classify_route(question: str) -> Route:
    text = re.sub(r"\s+", " ", question.lower().replace("-", " "))
    if (
        any(word in text for word in ("report", "weekly update", "status update"))
        or re.search(r"\bweekly\s+(?:project\s+)?(?:status\s+)?(?:summary|digest)\b", text)
    ):
        return "report"
    historical_change = (
        re.search(r"\b(risks?|blockers?|impediments?|delivery|completion)\b", text)
        and re.search(r"\b(since|versus|vs|from)\b.*\b(last|previous|prior)\b.*\b(sprint|iteration)\b", text)
    )
    if (
        any(word in text for word in ("compare", "comparison", "trend", "changed", "history", "historical"))
        or (re.search(r"\bsprints?\b", text) and re.search(r"\bside\s+by\s+side\b", text))
        or historical_change
    ):
        return "compare"
    if (
        any(word in text for word in ("risk", "risks", "blocker", "blocked", "overdue", "flag"))
        or re.search(r"\bimpediments?\b", text)
    ):
        return "risk"
    if (
        any(word in text for word in ("completion", "complete", "velocity", "points", "metrics", "tickets"))
        or re.search(r"\bdelivery\b.*\b(percent(?:age)?|rate)\b", text)
        or (
            re.search(r"\b(items?|tasks?|work)\b", text)
            and re.search(r"\b(finished|done)\b", text)
        )
    ):
        return "metrics"
    return "question"


def _facts_for_route(
    route: Route, sprint_name: str, sprints: dict[str, pd.DataFrame]
) -> dict[str, Any]:
    current = sprints[sprint_name]
    facts: dict[str, Any] = {
        "sprint": sprint_metrics(current),
        "overdue_tasks": overdue_tasks(current),
        "risk_flags": risk_flags(current),
        "blocker_durations": blocker_durations(sprints),
        "recurring_blockers": recurring_blockers(sprints),
    }
    if route in ("compare", "report", "question"):
        facts["historical_comparison"] = historical_comparison(sprints)
    if route == "metrics":
        facts = {"sprint": facts["sprint"], "overdue_tasks": facts["overdue_tasks"]}
    elif route == "risk":
        facts = {
            "sprint": facts["sprint"],
            "overdue_tasks": facts["overdue_tasks"],
            "risk_flags": facts["risk_flags"],
            "blocker_durations": facts["blocker_durations"],
            "recurring_blockers": facts["recurring_blockers"],
        }
    return facts


def _fallback_answer(
    route: Route, facts: dict[str, Any], question: str = "", *,
    current_ticket_ids=None,
) -> str:
    return render_answer(route, facts, question, current_ticket_ids=current_ticket_ids)


def build_sprint_graph(
    sprints: dict[str, pd.DataFrame], checkpointer: SqliteSaver | None = None,
    semantic_memory=None,
):
    builder = StateGraph(SprintState)
    semantic_memory = semantic_memory if semantic_memory is not None else DisabledMemory()

    def render_fallback(state, route=None):
        # Validation context is transient: do not add all ticket IDs to
        # checkpointed tool findings or change conversation relevance ranking.
        return _fallback_answer(
            route or state["route"], state.get("tool_outputs", {}),
            state.get("question", "") if route != "report" else "",
            current_ticket_ids=sprints[state["sprint_name"]]["ticket_id"].astype(str),
        )

    def recall_conversation(state: SprintState, config: RunnableConfig) -> dict[str, Any]:
        # This is a fresh view of retained history, not an accumulated state list.
        thread = config.get("configurable", {}).get("thread_id", "")
        insights, status = semantic_memory.recall(state.get("question", ""), thread)
        return {"conversation_context": relevant_turns(
            checkpointer, thread,
            state.get("question", ""), state.get("sprint_name", ""),
            semantic_memory.project_scope,
        ), "semantic_context": insights, "semantic_memory_status": {"search": status},
            "memory_project_scope": semantic_memory.project_scope}

    def remember_findings(state: SprintState, config: RunnableConfig) -> dict[str, Any]:
        status = "skipped"
        if isinstance(semantic_memory, DisabledMemory):
            status = semantic_memory.status
        elif not state.get("error") and state.get("tool_outputs"):
            try:
                findings = extract_findings(
                    sprints[state["sprint_name"]], state["tool_outputs"], state.get("question", ""),
                )
                status = semantic_memory.remember(
                    findings, config.get("configurable", {}).get("thread_id", ""),
                )
            except Exception:
                status = "unavailable"
        return {"semantic_memory_status": {
            **state.get("semantic_memory_status", {}), "write": status,
        }}

    def model_evidence(state, facts):
        evidence = dict(facts)
        if state.get("conversation_context"):
            evidence["conversation_history"] = state["conversation_context"]
        if state.get("semantic_context"):
            evidence["semantic_memory"] = state["semantic_context"]
        return evidence

    def select_route(state: SprintState) -> dict[str, Any]:
        return {"route": state.get("route") or classify_route(state.get("question", ""))}

    def make_tool_node(tool_route: Route):
        def run_tools(state: SprintState) -> dict[str, Any]:
            errors = list(state.get("errors", []))
            error_count = state.get("error_count", 0)
            try:
                facts = _facts_for_route(tool_route, state["sprint_name"], sprints)
                return {"tool_outputs": facts, "error_count": error_count, "errors": errors}
            except Exception as exc:  # bounded, surfaced failure instead of silent fabricated values
                errors.append(f"Tool execution failed: {type(exc).__name__}: {exc}")
                return {
                    "tool_outputs": {},
                    "error_count": min(error_count + 1, MAX_ERRORS),
                    "errors": errors[:MAX_ERRORS],
                    "error": "Sprint tools could not complete. Check the selected snapshot and input data.",
                }

        return run_tools

    def answer(state: SprintState) -> dict[str, Any]:
        facts = state.get("tool_outputs", {})
        if state.get("error") or not facts:
            return {
                "response": state.get("error")
                or "No deterministic tool outputs are available; no answer was generated.",
                "generation_mode": "tools unavailable",
            }
        context = state.get("conversation_context", [])
        model_facts = model_evidence(state, facts)
        fallback = (
            render_fallback(state) + fallback_recall(context)
            + historical_semantic_excerpt(state.get("semantic_context", []))
        )
        try:
            text, mode = generate_grounded_text(state.get("question", ""), model_facts)
            if text:
                return {"response": text, "generation_mode": mode}
        except Exception as exc:
            errors = list(state.get("errors", []))
            errors.append(f"LLM request failed: {type(exc).__name__}: {exc}")
            return {
                "response": fallback,
                "generation_mode": "deterministic fallback",
                "error_count": min(state.get("error_count", 0) + 1, MAX_ERRORS),
                "errors": errors[:MAX_ERRORS],
            }
        return {
            "response": fallback,
            "generation_mode": mode,
        }

    def report(state: SprintState) -> dict[str, Any]:
        facts = state.get("tool_outputs", {})
        if state.get("error") or not facts:
            message = state.get("error") or (
                "No deterministic tool outputs are available; no report was generated."
            )
            return {
                "report": message,
                "response": message,
                "generation_mode": "tools unavailable",
            }
        context = state.get("conversation_context", [])
        model_facts = model_evidence(state, facts)
        try:
            text, mode = generate_grounded_text(
                "Write a concise weekly sprint status report in Markdown. Include delivery, "
                "risks, recurring blocker history, and historical comparison when supplied. "
                "Use exact metrics and ticket IDs. Do not add recommendations that imply "
                "unsupported causes or promises.",
                model_facts,
            )
            if text:
                return {
                    "report": text,
                    "response": text,
                    "generation_mode": mode,
                }
        except Exception as exc:
            errors = list(state.get("errors", []))
            errors.append(f"LLM report request failed: {type(exc).__name__}: {exc}")
            return {
                "report": render_fallback(state, "report"),
                "response": render_fallback(state, "report"),
                "generation_mode": "deterministic fallback",
                "error_count": min(state.get("error_count", 0) + 1, MAX_ERRORS),
                "errors": errors[:MAX_ERRORS],
            }
        fallback = render_fallback(state, "report")
        return {
            "report": fallback,
            "response": fallback,
            "generation_mode": mode,
        }

    builder.add_node("recall_conversation", recall_conversation)
    builder.add_node("remember_findings", remember_findings)
    builder.add_node("route_request", select_route)
    tool_nodes = {
        "metrics": "retrieve_sprint_data",
        "risk": "detect_risk",
        "compare": "compare_sprint_history",
        "report": "gather_report_evidence",
        "question": "retrieve_question_context",
    }
    for route, node_name in tool_nodes.items():
        builder.add_node(node_name, make_tool_node(route))  # type: ignore[arg-type]
    builder.add_node("answer", answer)
    builder.add_node("report", report)
    builder.add_edge(START, "recall_conversation")
    builder.add_edge("recall_conversation", "route_request")
    builder.add_conditional_edges(
        "route_request",
        lambda state: state["route"],
        {
            **tool_nodes,
        },
    )
    for node_name in tool_nodes.values():
        builder.add_edge(node_name, "remember_findings")
    builder.add_conditional_edges(
        "remember_findings",
        lambda state: "answer" if state.get("route") != "report" else "report",
        {"answer": "answer", "report": "report"},
    )
    builder.add_edge("answer", END)
    builder.add_edge("report", END)
    return builder.compile(checkpointer=checkpointer)


def _public_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "sprint_name": result.get("sprint_name", ""),
        "route": result.get("route"),
        "tool_outputs": result.get("tool_outputs", {}),
        "response": result.get("response", ""),
        "report": result.get("report", ""),
        "generation_mode": result.get("generation_mode", ""),
        "error_count": result.get("error_count", 0),
        "errors": result.get("errors", []),
        "error": result.get("error"),
        "recalled_turns": len(result.get("conversation_context", [])),
        "semantic_memory_status": result.get("semantic_memory_status", {}),
    }


def restore_conversation(thread_id: str) -> dict[str, Any]:
    """Restore only an explicitly supplied private capability, never enumerate threads."""
    unavailable = "Conversation unavailable. Check the private key and retained storage."
    if not valid_conversation_key(thread_id) or not CHECKPOINT_PATH.is_file():
        raise ValueError(unavailable)
    connection = sqlite3.connect(str(CHECKPOINT_PATH), check_same_thread=False)
    try:
        turns = project_turns(
            completed_turns(SqliteSaver(connection), thread_id), configured_project_scope(),
        )
        if not turns:
            raise ValueError(unavailable)
        return _public_result(turns[0])
    except sqlite3.Error:
        raise ValueError(unavailable) from None
    finally:
        connection.close()


def invoke_sprint_graph(
    question: str,
    sprint_name: str,
    sprints: dict[str, pd.DataFrame],
    thread_id: str | None = None,
    route_override: Route | None = None,
) -> dict[str, Any]:
    """Execute a fresh request while retaining the thread's checkpoint history."""
    CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(CHECKPOINT_PATH), check_same_thread=False)
    saver = SqliteSaver(connection)
    saver.setup()
    semantic_memory = configured_semantic_memory()
    graph = build_sprint_graph(sprints, saver, semantic_memory)
    config = {"configurable": {"thread_id": thread_id or str(uuid.uuid4())}}
    # LangGraph merges inputs into the existing checkpoint. Omitted keys retain
    # their old values, so replace every request-scoped field explicitly. This
    # leaves earlier checkpoints and any unrelated persistent state untouched.
    state: SprintState = {
        "question": question,
        "sprint_name": sprint_name,
        "route": route_override or classify_route(question),
        "tool_outputs": {},
        "response": "",
        "report": "",
        "generation_mode": "",
        "error_count": 0,
        "errors": [],
        "error": None,
    }
    try:
        result = graph.invoke(state, config=config)
        return _public_result(result)
    finally:
        with suppress(Exception):
            semantic_memory.close()
        connection.close()
