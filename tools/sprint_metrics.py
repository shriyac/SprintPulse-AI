from __future__ import annotations

from typing import Any

import pandas as pd

DONE_STATUSES = {"done", "closed", "resolved"}


def _is_done(status: Any) -> bool:
    return str(status).strip().lower() in DONE_STATUSES


def sprint_metrics(frame: pd.DataFrame) -> dict[str, Any]:
    total = len(frame)
    done = frame["status"].map(_is_done)
    open_frame = frame.loc[~done]
    as_of = frame["sprint_end"].max()
    overdue = open_frame.loc[open_frame["due_date"] < as_of]
    scope_points = int(frame["story_points"].sum())
    completed_points = int(frame.loc[done, "story_points"].sum())
    blocked_count = int(
        (frame["status"].astype(str).str.lower() == "blocked").sum()
    )
    status_counts = frame["status"].value_counts().to_dict()
    return {
        "sprint_name": str(frame["sprint_name"].iloc[0]),
        "sprint_start": frame["sprint_start"].min().date().isoformat(),
        "sprint_end": as_of.date().isoformat(),
        "total_tickets": total,
        "done_count": int(done.sum()),
        "completion_rate": round((int(done.sum()) / total * 100) if total else 0.0, 1),
        "story_points_scope": scope_points,
        "story_points_completed": completed_points,
        "remaining_points": scope_points - completed_points,
        "overdue_count": len(overdue),
        "blocked_count": blocked_count,
        "status_counts": {str(key): int(value) for key, value in status_counts.items()},
    }


def overdue_tasks(frame: pd.DataFrame) -> list[dict[str, Any]]:
    as_of = frame["sprint_end"].max()
    is_open = ~frame["status"].map(_is_done)
    overdue = frame.loc[is_open & (frame["due_date"] < as_of)]
    return [
        {
            "ticket_id": str(row.ticket_id),
            "summary": str(row.summary),
            "assignee": str(row.assignee),
            "status": str(row.status),
            "due_date": row.due_date.date().isoformat(),
            "days_overdue": int((as_of - row.due_date).days),
        }
        for row in overdue.itertuples()
    ]


def blocker_durations(sprints: dict[str, pd.DataFrame]) -> list[dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for name, frame in sprints.items():
        as_of = frame["sprint_end"].max()
        blocked = frame.loc[frame["status"].astype(str).str.lower() == "blocked"]
        for row in blocked.itertuples():
            if pd.isna(row.blocked_since):
                continue
            duration = max(0, int((as_of - row.blocked_since).days))
            ticket_id = str(row.ticket_id)
            existing = records.get(ticket_id)
            if existing is None or duration >= existing["duration_days"]:
                records[ticket_id] = {
                    "ticket_id": ticket_id,
                    "summary": str(row.summary),
                    "blocker_reason": str(row.blocker_reason),
                    "duration_days": duration,
                    "observed_in": name,
                }
    return sorted(records.values(), key=lambda item: (-item["duration_days"], item["ticket_id"]))


def recurring_blockers(sprints: dict[str, pd.DataFrame]) -> list[dict[str, Any]]:
    appearances: dict[str, dict[str, Any]] = {}
    for name, frame in sprints.items():
        blocked = frame.loc[frame["status"].astype(str).str.lower() == "blocked"]
        for row in blocked.itertuples():
            ticket_id = str(row.ticket_id)
            item = appearances.setdefault(
                ticket_id,
                {
                    "ticket_id": ticket_id,
                    "summary": str(row.summary),
                    "blocker_reason": str(row.blocker_reason),
                    "sprints": [],
                },
            )
            item["sprints"].append(name)
    result = []
    for item in appearances.values():
        if len(item["sprints"]) >= 2:
            result.append({**item, "appearances": len(item["sprints"])})
    return sorted(result, key=lambda item: (-item["appearances"], item["ticket_id"]))


def risk_flags(frame: pd.DataFrame) -> list[dict[str, str]]:
    metrics = sprint_metrics(frame)
    risks: list[dict[str, str]] = []
    if metrics["blocked_count"]:
        risks.append(
            {
                "level": "High",
                "category": "Open blockers",
                "detail": f"{metrics['blocked_count']} ticket(s) are in Blocked status at sprint end.",
            }
        )
    if metrics["overdue_count"]:
        risks.append(
            {
                "level": "High",
                "category": "Overdue work",
                "detail": f"{metrics['overdue_count']} open ticket(s) were past due at sprint end.",
            }
        )
    if metrics["completion_rate"] < 70:
        risks.append(
            {
                "level": "Medium",
                "category": "Completion below threshold",
                "detail": (
                    f"Completion was {metrics['completion_rate']:.1f}%, below the "
                    "configured 70% sprint-end threshold."
                ),
            }
        )
    return risks


def historical_comparison(sprints: dict[str, pd.DataFrame]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    previous_rate: float | None = None
    for name, frame in sprints.items():
        metrics = sprint_metrics(frame)
        rate = metrics["completion_rate"]
        rows.append(
            {
                "sprint_name": name,
                "completion_rate": rate,
                "done_count": metrics["done_count"],
                "total_tickets": metrics["total_tickets"],
                "blocked_count": metrics["blocked_count"],
                "change_pp": round(rate - previous_rate, 1) if previous_rate is not None else 0.0,
            }
        )
        previous_rate = rate
    return rows
