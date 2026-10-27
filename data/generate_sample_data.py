from __future__ import annotations

import csv
from datetime import date, timedelta
from pathlib import Path

OUT_DIR = Path(__file__).parent

TICKETS = [
    ("Platform authentication refresh", "Maya Chen", "High", 5),
    ("Audit token rotation flow", "Ravi Patel", "High", 3),
    ("Partner API sandbox access", "Elena Garcia", "High", 5),
    ("Add sprint export endpoint", "Jordan Lee", "Medium", 5),
    ("Improve dashboard loading state", "Maya Chen", "Medium", 3),
    ("Document webhook retry policy", "Ravi Patel", "Low", 2),
    ("Add service health panel", "Elena Garcia", "Medium", 3),
    ("Resolve vendor rate limit", "Jordan Lee", "High", 5),
    ("Refactor event ingestion worker", "Maya Chen", "Medium", 5),
    ("Expand integration test coverage", "Ravi Patel", "Medium", 3),
    ("Add audit trail filters", "Elena Garcia", "Medium", 3),
    ("Clean up notification preferences", "Jordan Lee", "Low", 2),
    ("Create usage summary endpoint", "Maya Chen", "Medium", 5),
    ("Repair CSV import validation", "Ravi Patel", "High", 3),
    ("Update account settings page", "Elena Garcia", "Low", 2),
    ("Complete analytics event mapping", "Jordan Lee", "Medium", 5),
    ("Review accessibility labels", "Maya Chen", "Low", 2),
    ("Configure staging data access", "Ravi Patel", "High", 3),
    ("Add organization-level roles", "Elena Garcia", "High", 5),
    ("Improve search relevance", "Jordan Lee", "Medium", 5),
    ("Add CSV download to reports", "Maya Chen", "Low", 2),
    ("Investigate intermittent timeout", "Ravi Patel", "High", 3),
    ("Add sprint handoff checklist", "Elena Garcia", "Low", 2),
    ("Update dependency inventory", "Jordan Lee", "Low", 2),
]

SPRINTS = [
    {
        "name": "Sprint 24",
        "start": date(2026, 6, 1),
        "end": date(2026, 6, 12),
        "done": set(range(1, 11)),
        "blocked": {18, 22, 24},
        "blocked_since": {18: date(2026, 6, 3), 22: date(2026, 6, 8), 24: date(2026, 6, 10)},
    },
    {
        "name": "Sprint 25",
        "start": date(2026, 6, 15),
        "end": date(2026, 6, 26),
        "done": set(range(1, 14)),
        "blocked": {18, 22, 24},
        "blocked_since": {18: date(2026, 6, 3), 22: date(2026, 6, 8), 24: date(2026, 6, 24)},
    },
    {
        "name": "Sprint 26",
        "start": date(2026, 6, 29),
        "end": date(2026, 7, 10),
        "done": set(range(1, 17)),
        "blocked": {18, 22},
        "blocked_since": {18: date(2026, 6, 3), 22: date(2026, 6, 8)},
    },
]

FIELDS = [
    "sprint_name",
    "sprint_start",
    "sprint_end",
    "ticket_id",
    "summary",
    "assignee",
    "status",
    "priority",
    "story_points",
    "created_date",
    "due_date",
    "completed_date",
    "is_blocker",
    "blocker_reason",
    "blocked_since",
]


def build_rows(sprint: dict) -> list[dict[str, object]]:
    rows = []
    for index, (summary, assignee, priority, points) in enumerate(TICKETS, start=1):
        if index in sprint["done"]:
            status = "Done"
        elif index in sprint["blocked"]:
            status = "Blocked"
        elif index <= 20:
            status = "In Progress"
        else:
            status = "To Do"

        due_date = sprint["start"] + timedelta(days=3 + (index % 8))
        complete_date = (
            min(due_date, sprint["end"] - timedelta(days=1))
            if status == "Done"
            else ""
        )
        reasons = {
            18: "Staging access approval pending",
            22: "Intermittent service timeout investigation",
            24: "Dependency inventory review pending",
        }
        blocked_since = sprint["blocked_since"].get(index, "")
        rows.append(
            {
                "sprint_name": sprint["name"],
                "sprint_start": sprint["start"].isoformat(),
                "sprint_end": sprint["end"].isoformat(),
                "ticket_id": f"SP-{100 + index}",
                "summary": summary,
                "assignee": assignee,
                "status": status,
                "priority": priority,
                "story_points": points,
                "created_date": (sprint["start"] - timedelta(days=2)).isoformat(),
                "due_date": due_date.isoformat(),
                "completed_date": complete_date,
                "is_blocker": status == "Blocked",
                "blocker_reason": reasons.get(index, "") if status == "Blocked" else "",
                "blocked_since": blocked_since.isoformat() if blocked_since else "",
            }
        )
    return rows


def generate() -> None:
    for number, sprint in enumerate(SPRINTS, start=1):
        destination = OUT_DIR / f"sprint_{number:02d}.csv"
        with destination.open("w", newline="", encoding="utf-8") as output:
            writer = csv.DictWriter(output, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(build_rows(sprint))


if __name__ == "__main__":
    generate()
