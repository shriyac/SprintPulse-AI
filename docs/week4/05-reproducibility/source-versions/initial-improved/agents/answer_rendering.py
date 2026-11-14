"""Deterministic presentation of existing tool evidence, without extra retrieval.

Snapshot status is authoritative; historical blocker observations never establish
current status or prove a fix. Missing fields are reported, not filled with zero.
"""
from __future__ import annotations

from datetime import date, timedelta
import re
from typing import Any


def _value(record: dict, key: str) -> Any:
    return record.get(key) if record.get(key) is not None else "unavailable"


def _percent(value: Any) -> str:
    return f"{value:.1f}%" if isinstance(value, (int, float)) else "unavailable"


def _reference(sprint: dict) -> str:
    return f"{_value(sprint, 'sprint_name')} at sprint end {_value(sprint, 'sprint_end')} (snapshot, not live Jira)"


def _tickets(question: str) -> set[str]:
    return {ticket.upper() for ticket in re.findall(r"\bSP-\d+\b", question, re.I)}


def _select(rows: list[dict], tickets: set[str]) -> list[dict]:
    return [row for row in rows if not tickets or row.get("ticket_id", "").upper() in tickets]


def _metrics(sprint: dict, question: str) -> str:
    text = (
        f"{_reference(sprint)}: {_value(sprint, 'done_count')} of "
        f"{_value(sprint, 'total_tickets')} tickets complete "
        f"({_percent(sprint.get('completion_rate'))}). "
        f"{_value(sprint, 'story_points_completed')} of {_value(sprint, 'story_points_scope')} "
        f"story points completed; {_value(sprint, 'remaining_points')} remaining. "
        f"{_value(sprint, 'overdue_count')} open tickets are overdue."
    )
    if re.search(r"\bdelivery\b.*\b(percent(?:age)?|rate)\b", question, re.I):
        numerator, denominator = sprint.get("story_points_completed"), sprint.get("story_points_scope")
        points = (
            _percent(round(100 * numerator / denominator, 1))
            if isinstance(numerator, (int, float)) and isinstance(denominator, (int, float)) and denominator > 0
            else "unavailable (zero or missing story-point scope)"
        )
        text += (
            f"\nTicket completion: {_percent(sprint.get('completion_rate'))} "
            f"({_value(sprint, 'done_count')}/{_value(sprint, 'total_tickets')}). "
            f"Story-point completion: {points} "
            f"({_value(sprint, 'story_points_completed')}/{_value(sprint, 'story_points_scope')}); "
            "percentage derived from the tool's completed points and scope."
        )
    return text


def _risk_flags(facts: dict) -> str:
    if "risk_flags" not in facts:
        return "Risk flags are unavailable in the tool evidence."
    return "\n".join(
        f"- **{item['level']} · {item['category']}**: {item['detail']}"
        for item in facts["risk_flags"]
    ) or "No deterministic risk rules were triggered for this sprint."


def _overdue(facts: dict, tickets: set[str]) -> str:
    rows = _select(facts.get("overdue_tasks", []), tickets)
    if not rows:
        return "No matching overdue task evidence is available; this does not establish a ticket's current status."
    return "\n".join(
        f"- {row['ticket_id']}: {row['days_overdue']} days overdue; "
        f"status {row['status']}; due {row['due_date']} — {row['summary']}"
        for row in rows
    )


def _current_status(facts: dict, ticket: str) -> str:
    row = next((r for r in facts.get("overdue_tasks", []) if r["ticket_id"].upper() == ticket.upper()), None)
    if row is None:
        return f"{ticket}: current status is unavailable in the supplied ticket-level evidence."
    status = row["status"]
    qualifier = "; not currently blocked" if status.lower() != "blocked" else ""
    return (
        f"{ticket}: selected-snapshot status {status}{qualifier}; "
        f"{row['days_overdue']} days overdue at {_value(facts.get('sprint', {}), 'sprint_end')}."
    )


def _recurrence(facts: dict, tickets: set[str]) -> str:
    rows = _select(facts.get("recurring_blockers", []), tickets)
    if not rows:
        return "No matching recurring blocker evidence is available."
    lines = [
        f"- {row['ticket_id']}: historically Blocked in {', '.join(row['sprints'])} "
        f"({row['appearances']} snapshots) — {row['blocker_reason']}."
        for row in rows
    ]
    lines.append("Historical recurrence is not proof of current blocked status or confirmed resolution.")
    return "\n".join(lines)


def _durations(facts: dict, question: str, tickets: set[str]) -> str:
    rows = _select(facts.get("blocker_durations", []), tickets)
    if not rows:
        return "No matching blocker-duration evidence is available."
    if re.search(r"\b(longest|longest-running|maximum)\b", question, re.I):
        maximum = max(row["duration_days"] for row in rows)
        rows = [row for row in rows if row["duration_days"] == maximum]
    sprint = facts.get("sprint", {})
    lines = []
    for row in rows:
        line = (
            f"- {row['ticket_id']} — {row['summary']}: maximum observed duration "
            f"{row['duration_days']} days; observed in {row['observed_in']}; "
            f"recorded blocker reason: {row['blocker_reason']}."
        )
        if row["observed_in"] == sprint.get("sprint_name"):
            try:
                since = date.fromisoformat(sprint["sprint_end"]) - timedelta(days=row["duration_days"])
                line += f" Observed blocked-since date {since.isoformat()} (derived from sprint end minus duration)."
            except (KeyError, TypeError, ValueError, OverflowError):
                line += " Observation date is unavailable."
        lines.append(line)
        lines.append(_current_status(facts, row["ticket_id"]))
    lines.append("These are snapshot observations, not days elapsed as of today's date.")
    return "\n".join(lines)


def _impediments(facts: dict) -> str:
    rows = [r for r in facts.get("overdue_tasks", []) if r["status"].lower() == "blocked"]
    count = facts.get("sprint", {}).get("blocked_count")
    text = (
        "Operational definition for this answer: unresolved impediments means tickets "
        "currently marked Blocked in the selected snapshot, not all possible project impediments.\n"
    )
    text += "\n".join(f"- {r['ticket_id']}: Blocked — {r['summary']}" for r in rows)
    if count != len(rows):
        text += (
            "\nAvailable ticket-level evidence is incomplete: the sprint's blocked count is "
            f"{count if count is not None else 'unavailable'}, but only {len(rows)} blocked "
            "tickets are identified in the overdue evidence. Other blocked IDs are unavailable."
        )
    elif count == 0:
        text += "No tickets are marked Blocked according to the supplied sprint count."
    return text


def _comparison(facts: dict, question: str, tickets: set[str]) -> str:
    rows = facts.get("historical_comparison", [])
    if not rows:
        return "Historical comparison is unavailable in the tool evidence."
    lines = ["Completion history (supplied snapshots, chronological):"]
    for index, row in enumerate(rows):
        lines.append(
            f"- {row['sprint_name']}: {row['completion_rate']:.1f}% "
            f"({row['done_count']} of {row['total_tickets']} tickets; "
            f"{row['change_pp']:+.1f} percentage points); "
            f"{row['blocked_count']} tickets marked Blocked."
        )
        if index:
            previous = rows[index - 1]
            change = row["done_count"] - previous["done_count"]
            lines.append(
                f"  Completed-ticket change from {previous['sprint_name']} to {row['sprint_name']}: "
                f"{change:+d} ({abs(change)} {'more' if change >= 0 else 'fewer'} completed tickets)."
            )
    if re.search(r"\b(risks?|blockers?|blocked|impediments?|fix(?:ed|es)?|resolv\w*)\b", question, re.I):
        lines.extend(["\nSelected-snapshot risks:", _risk_flags(facts)])
        selected = next((i for i, row in enumerate(rows) if row["sprint_name"] == facts.get("sprint", {}).get("sprint_name")), None)
        if selected is not None and selected > 0:
            old, new = rows[selected - 1], rows[selected]
            lines.append(
                f"Observed blocked-ticket count: {old['sprint_name']} {old['blocked_count']} "
                f"→ {new['sprint_name']} {new['blocked_count']}."
            )
        lines.append(
            "Observed changes are not confirmed fixes. A lower count or a move to To Do "
            "does not establish resolution; ticket-level resolution evidence is not supplied."
        )
    for ticket in sorted(tickets):
        lines.extend(["\n" + _recurrence(facts, {ticket}), _current_status(facts, ticket)])
    if tickets:
        lines.append("A status change alone does not establish resolution of the historical dependency or blocker.")
    return "\n".join(lines)


def render_answer(route: str, facts: dict, question: str = "") -> str:
    """Render only available tool evidence; never inspect CSVs, memory or services."""
    sprint = facts.get("sprint", {})
    tickets = _tickets(question)
    text = question.lower()
    if route == "metrics":
        return _metrics(sprint, question)
    if route == "risk":
        sections = [_reference(sprint), _risk_flags(facts)]
        if re.search(r"\bimpediments?\b", text):
            sections.append(_impediments(facts))
        if "overdue" in text:
            sections.append("Overdue tasks at sprint end:\n" + _overdue(facts, tickets))
        if re.search(r"\b(duration|durations|longest|long|maximum)\b", text):
            sections.append(_durations(facts, question, tickets))
        if re.search(r"\b(multiple|across|recurr\w*|history|historical)\b", text):
            sections.append(_recurrence(facts, tickets))
        for ticket in sorted(tickets):
            sections.append(_current_status(facts, ticket))
            if not re.search(r"\b(duration|durations|longest|long|maximum)\b", text) and "overdue" not in text:
                sections.extend([_durations(facts, question, {ticket}), _recurrence(facts, {ticket})])
        return "\n\n".join(sections)
    if route == "compare":
        return _reference(sprint) + "\n\n" + _comparison(facts, question, tickets)
    if route == "report":
        return (
            f"# Weekly Sprint Status — {_value(sprint, 'sprint_name')}\n\n"
            "_Draft only. Human approval is required before saving or publishing._\n\n"
            f"## Delivery\n{_metrics(sprint, '')}\n\n"
            f"- Open blockers: {_value(sprint, 'blocked_count')}.\n\n"
            f"## Risk flags\n{_risk_flags(facts)}\n\n"
            f"## Blocker history\n{_recurrence(facts, set())}\n\n"
            f"## Historical comparison\n{_comparison(facts, '', set())}\n\n"
            "_All figures above are calculated from the provided sprint snapshots._"
        )
    return (
        f"From {_reference(sprint)}: completion is {_percent(sprint.get('completion_rate'))} "
        f"({_value(sprint, 'done_count')} of {_value(sprint, 'total_tickets')} tickets). "
        f"There are {_value(sprint, 'blocked_count')} open blockers and "
        f"{_value(sprint, 'overdue_count')} overdue open tickets. "
        "Ask about completion, risk, blockers, or history for more detail."
    )
