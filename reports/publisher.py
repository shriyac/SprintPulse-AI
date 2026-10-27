from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path


def save_approved_report(report: str, report_sprint: str, reports_dir: Path) -> Path:
    """Persist a report only when called by the explicit approval action."""
    if not report.strip():
        raise ValueError("Cannot save an empty report.")
    reports_dir.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^a-z0-9]+", "-", report_sprint.lower()).strip("-") or "sprint"
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = reports_dir / f"{safe_name}-weekly-status-{timestamp}.md"
    path.write_text(report.rstrip() + "\n", encoding="utf-8")
    return path
