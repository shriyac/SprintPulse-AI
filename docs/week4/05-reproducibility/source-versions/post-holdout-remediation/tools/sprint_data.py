from __future__ import annotations

from pathlib import Path

import pandas as pd

REQUIRED_COLUMNS = {
    "sprint_name",
    "sprint_start",
    "sprint_end",
    "ticket_id",
    "summary",
    "assignee",
    "status",
    "priority",
    "story_points",
    "due_date",
    "completed_date",
    "is_blocker",
    "blocker_reason",
    "blocked_since",
}


def load_sprint_data(data_dir: Path) -> dict[str, pd.DataFrame]:
    files = sorted(data_dir.glob("sprint_*.csv"))
    if len(files) < 2:
        raise FileNotFoundError(f"Expected at least two sprint_*.csv snapshots in {data_dir}.")

    snapshots: dict[str, pd.DataFrame] = {}
    shared_ids: set[str] | None = None
    for file_path in files:
        frame = pd.read_csv(file_path)
        missing = REQUIRED_COLUMNS - set(frame.columns)
        if missing:
            raise ValueError(f"{file_path.name} is missing columns: {', '.join(sorted(missing))}")
        if frame["ticket_id"].duplicated().any():
            raise ValueError(f"{file_path.name} contains duplicate ticket IDs.")
        ids = set(frame["ticket_id"].astype(str))
        if shared_ids is None:
            shared_ids = ids
        elif ids != shared_ids:
            raise ValueError("Ticket IDs must be preserved across all sprint snapshots.")
        for date_column in ("sprint_start", "sprint_end", "due_date", "completed_date", "blocked_since"):
            frame[date_column] = pd.to_datetime(frame[date_column], errors="coerce")
        blocker_values = frame["is_blocker"].astype(str).str.strip().str.lower()
        if not blocker_values.isin({"true", "false"}).all():
            raise ValueError(f"{file_path.name} has invalid is_blocker values.")
        frame["is_blocker"] = blocker_values.map({"true": True, "false": False})
        frame["story_points"] = pd.to_numeric(frame["story_points"], errors="raise")
        sprint_names = frame["sprint_name"].dropna().unique()
        if len(sprint_names) != 1:
            raise ValueError(f"{file_path.name} must contain exactly one sprint name.")
        snapshots[str(sprint_names[0])] = frame.sort_values("ticket_id").reset_index(drop=True)

    return dict(sorted(snapshots.items(), key=lambda item: item[1]["sprint_start"].iloc[0]))


def available_sprints(sprints: dict[str, pd.DataFrame]) -> list[str]:
    return list(sprints.keys())
