from pathlib import Path

from tools.sprint_data import load_sprint_data
from tools.sprint_metrics import (
    blocker_durations,
    historical_comparison,
    overdue_tasks,
    recurring_blockers,
    risk_flags,
    sprint_metrics,
)

DATA_DIR = Path(__file__).parents[1] / "data"


def test_three_snapshots_have_24_stable_ticket_ids():
    sprints = load_sprint_data(DATA_DIR)
    assert len(sprints) == 3
    ids = [set(frame.ticket_id) for frame in sprints.values()]
    assert all(len(snapshot) == 24 for snapshot in ids)
    assert ids[0] == ids[1] == ids[2]


def test_completion_rate_and_points_are_calculated_from_rows():
    sprints = load_sprint_data(DATA_DIR)
    metrics = sprint_metrics(sprints["Sprint 26"])
    assert metrics["total_tickets"] == 24
    assert metrics["done_count"] == 16
    assert metrics["completion_rate"] == 66.7
    assert metrics["story_points_completed"] < metrics["story_points_scope"]


def test_overdue_only_includes_open_tickets():
    sprints = load_sprint_data(DATA_DIR)
    tasks = overdue_tasks(sprints["Sprint 26"])
    assert tasks
    assert all(task["status"] != "Done" for task in tasks)
    assert all(task["days_overdue"] > 0 for task in tasks)


def test_recurring_blockers_and_duration_use_snapshot_history():
    sprints = load_sprint_data(DATA_DIR)
    recurring = recurring_blockers(sprints)
    assert {item["ticket_id"] for item in recurring} == {"SP-118", "SP-122", "SP-124"}
    durations = blocker_durations(sprints)
    assert next(item for item in durations if item["ticket_id"] == "SP-118")["duration_days"] > 0


def test_risk_flags_are_deterministic_and_include_threshold_reason():
    sprints = load_sprint_data(DATA_DIR)
    flags = risk_flags(sprints["Sprint 26"])
    categories = {item["category"] for item in flags}
    assert "Open blockers" in categories
    assert "Overdue work" in categories
    assert "Completion below threshold" in categories


def test_historical_comparison_reports_percentage_point_change():
    sprints = load_sprint_data(DATA_DIR)
    comparison = historical_comparison(sprints)
    assert len(comparison) == 3
    assert comparison[0]["change_pp"] == 0.0
    assert comparison[1]["change_pp"] > 0
    assert comparison[2]["change_pp"] > 0
