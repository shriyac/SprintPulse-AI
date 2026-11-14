"""Replay the two unchanged, reviewed datasets; not an unseen evaluation.

Run: uv run --frozen --no-sync python -m evaluation.remediation
No qualitative judgments are automatically assigned by this runner.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    run = ROOT / ".local/evaluations" / ("post-holdout-remediation-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    run.mkdir(parents=True, exist_ok=False)
    source = run / "source-snapshot"
    for folder in ("agents", "tools", "reports", "data", "evaluation"):
        shutil.copytree(ROOT / folder, source / folder, ignore=shutil.ignore_patterns("__pycache__"))
    for filename in ("pyproject.toml", "uv.lock"):
        shutil.copy2(ROOT / filename, source / filename)
    manifest = {str(p.relative_to(source)): digest(p) for p in source.rglob("*") if p.is_file()}
    (run / "source-snapshot-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    protected = json.loads((ROOT / ".local/remediation-before.json").read_text())
    assert all(digest(ROOT / p) == sha for p, sha in protected.items())
    metadata = {
        "run_id": run.name, "classification": "post-holdout remediation / known-case regression replay, NOT independent unseen evaluation",
        "mode": "deterministic graph execution; stubbed LLM; DisabledMemory; network denied",
        "source_sha256": manifest, "datasets": {}, "paid_calls": 0,
        "human_qualitative_review": "PENDING; separate agent-assisted review may be prepared",
    }
    env = {
        "PATH": os.defpath, "HOME": str(run), "LANG": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1", "LANGSMITH_TRACING": "false",
        "LANGCHAIN_TRACING_V2": "false", "LANGCHAIN_TRACING": "false",
        "LANGSMITH_OTEL_ENABLED": "false", "SPRINTPULSE_RUN_MEM0_LIVE_TESTS": "false",
    }
    for label, worker in (("golden", "remediation_worker.py"), ("holdout", "holdout_worker.py")):
        dataset_path = source / "evaluation" / label / "v1.json"
        dataset = json.loads(dataset_path.read_text())
        expected = dataset_path.with_suffix(".sha256").read_text().split()[0]
        assert digest(dataset_path) == expected
        metadata["datasets"][label] = expected
        folder = run / label
        folder.mkdir()
        records = []
        for case in dataset["cases"]:
            output = folder / (case["id"] + ".json")
            proc = subprocess.run([
                sys.executable, str(source / "evaluation" / worker),
                "--source", str(source), "--dataset", str(dataset_path),
                "--case-id", case["id"], "--output", str(output),
            ], cwd=source, env=env, text=True, capture_output=True, timeout=90)
            (folder / (case["id"] + ".stderr.log")).write_text(proc.stderr)
            if proc.returncode:
                raise RuntimeError(f"Worker failed: {label}/{case['id']}; inspect retained stderr; no automatic retry")
            row = json.loads(output.read_text())
            records.append(row)
            print(f"{label}/{case['id']}: {row['actual_route']} ({row['trace']['latency_ms']} ms)", flush=True)
        (folder / "records.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records))
        (folder / "human-review-template.json").write_text(json.dumps({
            "dataset_sha256": expected, "records_sha256": digest(folder / "records.jsonl"),
            "reviewer_alias": "", "status": "PENDING independent human review",
            "cases": {r["case_id"]: {m: {"value": None, "reason": ""}
                      for m in ("task_completion", "answer_correctness", "memory_context_accuracy")
                      if r["scores"][m]["status"] != "N/A"} for r in records},
        }, indent=2) + "\n")
        metadata[label + "_final_requests"] = len(records)
        metadata[label + "_setup_requests"] = sum(
            len(r.get("setup_requests", [])) if label == "holdout"
            else int(r["trace"]["memory_observations"].get("setup_response_present", False))
            for r in records
        )
    assert all(digest(ROOT / p) == sha for p, sha in protected.items())
    assert all(digest(source / p) == sha for p, sha in manifest.items())
    metadata["previous_artifacts_unchanged"] = True
    (run / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print("RUN_DIR=" + str(run.relative_to(ROOT)))


if __name__ == "__main__":
    main()
