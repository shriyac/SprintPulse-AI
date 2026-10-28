"""Bounded, thread-scoped views over existing LangGraph checkpoints.

No separate memory database or growing conversation-state accumulator is used.
"""
from __future__ import annotations

import json
import re
import secrets
import uuid
from typing import Any

from langgraph.checkpoint.sqlite import SqliteSaver

MAX_CHECKPOINTS = 128
MAX_TURNS = 16
MAX_RECALLED_TURNS = 3
_STOP_WORDS = set(
    "a an the this that those these it them we you i me my our your of for in on to "
    "and or is are was were be been have has had do did does can could would should "
    "what which why how when who with as about please tell explain more again "
    "earlier previous previously last above same answer answers question questions "
    "request finding findings discussed said learn learned remember recall follow up "
    "now current sprint project".split()
)
_ALIASES = {
    "blocked": "blocker", "blockers": "blocker", "blocking": "blocker",
    "risks": "risk", "completed": "completion", "complete": "completion",
    "done": "completion", "metrics": "completion", "points": "completion",
    "longest": "duration", "durations": "duration", "long": "duration",
    "compare": "history", "comparison": "history", "historical": "history",
    "trend": "history", "changed": "history",
}
_FOLLOW_UP = re.compile(
    r"\b(that|those|these|them|it|earlier|previous|previously|above|again|"
    r"remember|recall|last answer|last question|finding|findings)\b", re.I
)
_TICKET = re.compile(r"\bsp-\d+\b", re.I)
_FALLBACK_HISTORY_HEADING = "\n\n### Relevant earlier conversation (historical, not current)\n"


def new_conversation_key() -> str:
    """A bearer capability; never publish this in URLs, logs or a thread list."""
    return "sp_" + secrets.token_urlsafe(32)


def valid_conversation_key(key: str) -> bool:
    if re.fullmatch(r"sp_[A-Za-z0-9_-]{43}", key):
        return True
    # Existing UI-generated UUID4 threads remain resumable without migration.
    try:
        identifier = uuid.UUID(key)
        return str(identifier) == key and identifier.version == 4 and identifier.variant == uuid.RFC_4122
    except (ValueError, AttributeError):
        return False


def completed_turns(saver: SqliteSaver | None, thread_id: str) -> list[dict[str, Any]]:
    """Newest successful completed turns, not intermediate or failed checkpoints."""
    if saver is None:
        return []
    config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
    turns = []
    for saved in saver.list(config, limit=MAX_CHECKPOINTS):
        values = saved.checkpoint.get("channel_values", {})
        # With the locked LangGraph graph, scheduled nodes have branch channels.
        # Input checkpoints can otherwise carry the preceding turn's response.
        if saved.metadata.get("source") != "loop" or any(
            name.startswith("branch:") for name in values
        ):
            continue
        if (
            not values.get("question") or not values.get("response")
            or not values.get("tool_outputs") or values.get("error")
        ):
            continue
        turns.append(values)
        if len(turns) >= MAX_TURNS:
            break
    return turns


def project_turns(turns: list[dict], scope: str | None) -> list[dict]:
    """Do not leak semantic answers back through checkpoint conversation recall.

    Legacy unscoped history is usable on first namespace adoption, but not when
    the retained window shows evidence that the key has crossed namespaces.
    """
    scopes = {turn.get("memory_project_scope") for turn in turns if turn.get("memory_project_scope")}
    legacy_allowed = not scopes or (scope is not None and scopes == {scope})
    return [
        turn for turn in turns
        if (scope is not None and turn.get("memory_project_scope") == scope)
        or (not turn.get("memory_project_scope") and legacy_allowed)
    ]


def _terms(text: str) -> set[str]:
    return {
        _ALIASES.get(word, word)
        for word in re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", text.lower())
        if word not in _STOP_WORDS
    }


def _historical_findings(facts: dict[str, Any]) -> dict[str, Any]:
    """Keep bounded factual fields, never recursively copy recalled context."""
    result = {}
    for name in (
        "sprint", "recurring_blockers", "blocker_durations",
        "risk_flags", "historical_comparison", "overdue_tasks",
    ):
        value = facts.get(name)
        if value is None:
            continue
        if isinstance(value, list):
            value = value[:8]
        # Skip oversized fields rather than serializing an unbounded old prompt.
        if len(json.dumps(value, default=str)) <= 6000:
            result[name] = value
    return result


def relevant_turns(
    saver: SqliteSaver | None, thread_id: str, question: str, sprint_name: str,
    project_scope: str | None = None,
) -> list[dict[str, Any]]:
    candidates = project_turns(completed_turns(saver, thread_id), project_scope)
    terms = _terms(question)
    tickets = {ticket.lower() for ticket in _TICKET.findall(question)}
    ranked = []
    for index, turn in enumerate(candidates):
        answer = turn["response"].split(_FALLBACK_HISTORY_HEADING, 1)[0]
        focus = f"{turn['question']} {answer}"
        previous_tickets = {
            ticket.lower() for ticket in _TICKET.findall(
                focus + json.dumps(turn["tool_outputs"], default=str)
            )
        }
        overlap = terms & _terms(focus)
        if tickets:
            if not tickets & previous_tickets:
                continue
            score = 10 + len(overlap)
        elif overlap:
            score = len(overlap)
        elif not terms and _FOLLOW_UP.search(question) and index == 0:
            score = 1
        else:
            continue
        ranked.append((score, turn.get("sprint_name") == sprint_name, -index, turn))
    ranked.sort(key=lambda item: item[:3], reverse=True)
    return [
        {
            "sprint_name": turn.get("sprint_name", ""),
            "question": turn["question"][:1000],
            "answer": turn["response"].split(_FALLBACK_HISTORY_HEADING, 1)[0][:2500],
            "findings": _historical_findings(turn["tool_outputs"]),
        }
        for *_, turn in ranked[:MAX_RECALLED_TURNS]
    ]


def fallback_recall(context: list[dict[str, Any]]) -> str:
    if not context:
        return ""
    return _FALLBACK_HISTORY_HEADING + "\n\n".join(
        f"**{turn['sprint_name']} — Earlier question:** {turn['question']}\n\n"
        f"**Earlier answer:** {turn['answer']}\n\n"
        f"Historical tool findings:\n```json\n{json.dumps(turn['findings'], default=str)}\n```"
        for turn in context
    )
