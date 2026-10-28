"""Deterministic historical observations; never extract facts from LLM prose."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any

import pandas as pd


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


@dataclass(frozen=True)
class Finding:
    kind: str
    summary: str
    source_ticket_ids: tuple[str, ...]
    sprint_name: str
    observed_at: str
    evidence: dict[str, Any]

    def envelope(self, project: str, owner: str, environment: str) -> dict[str, Any]:
        value = asdict(self)
        value["source_ticket_ids"] = sorted(set(self.source_ticket_ids))
        value.update(project_id=project, owner_scope=owner, environment=environment)
        # Wall-clock timestamps do not make an otherwise identical fact new.
        identity = {key: item for key, item in value.items() if key != "observed_at"}
        value["finding_id"] = hashlib.sha256(canonical(identity).encode()).hexdigest()
        value["recorded_at"] = datetime.now(timezone.utc).isoformat()
        return value


def extract_findings(
    frame: pd.DataFrame, facts: dict[str, Any], question: str
) -> list[Finding]:
    if frame.empty or not facts:
        return []
    as_of = frame["sprint_end"].max()
    if pd.isna(as_of):
        return []
    observed = as_of.to_pydatetime().replace(tzinfo=timezone.utc).isoformat()
    sprint = str(frame["sprint_name"].iloc[0])
    known = set(frame["ticket_id"].astype(str))
    findings = []

    def add(kind, summary, ids, evidence, timestamp=observed):
        ids = tuple(sorted(set(ids)))
        if ids and set(ids) <= known:
            findings.append(Finding(
                kind, summary[:2000], ids, sprint, timestamp,
                {**evidence, "snapshot_as_of": observed},
            ))

    for row in facts.get("recurring_blockers", []):
        add(
            "recurring_blocker",
            f"{row['ticket_id']} was blocked in {row['appearances']} sprint snapshots: "
            f"{row['blocker_reason']}.",
            [row["ticket_id"]], row,
        )
    for row in facts.get("risk_flags", []):
        category = row["category"]
        if category == "Open blockers":
            ids = frame.loc[frame["status"].str.lower() == "blocked", "ticket_id"]
        elif category == "Overdue work":
            ids = [item["ticket_id"] for item in facts.get("overdue_tasks", [])]
        else:
            ids = sorted(known)
        add("risk", f"{category}: {row['detail']}", ids, row)

    for row in frame.itertuples():
        reason = str(row.blocker_reason)
        if row.status.lower() == "blocked" and re.search(
            r"\b(waiting (?:on|for)|depends? on|requires?|awaiting|"
            r"(?:access|approval|permissions?|sign.off)\s+pending)\b", reason, re.I
        ):
            add(
                "dependency", f"{row.ticket_id} dependency statement: {reason}",
                [str(row.ticket_id)], {"source_field": "blocker_reason", "statement": reason},
            )

    # Explicit declarations through the existing Assistant, not model suggestions.
    declaration = re.fullmatch(
        r"\s*(Decision|Dependency)\s+(?:for\s+)?"
        r"([A-Z][A-Z0-9_]*-\d+(?:\s*,\s*[A-Z][A-Z0-9_]*-\d+)*)"
        r"\s*:\s*(.{1,1500})\s*", question, re.I | re.S,
    )
    if declaration:
        kind, ids, statement = declaration.groups()
        add(
            kind.lower(), " ".join(statement.split()),
            [ticket.strip().upper() for ticket in ids.split(",")],
            {"source": "explicit_user_statement", "statement": " ".join(statement.split())},
            datetime.now(timezone.utc).isoformat(),
        )
    return findings
