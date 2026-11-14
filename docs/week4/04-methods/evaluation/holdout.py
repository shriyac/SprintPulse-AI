"""Freeze an approved separate holdout and run exact source copies, offline only."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / ".local/evaluations/20261110T034016Z-1d9ab6bc"
NEW = ROOT / ".local/evaluations/20261110T035032Z-765dcbc8"
DATASET = ROOT / "evaluation/holdout/v1.json"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def protected():
    paths = set()
    for directory in ("agents", "tools", "reports", "data"):
        paths.update(p for p in (ROOT / directory).rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    paths.update(p for p in (ROOT / "evaluation").rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    for folder in (OLD, NEW, ROOT / ".local/evaluations/20261110T033345Z-e8181434"):
        paths.update(p for p in folder.rglob("*") if p.is_file())
    paths.update(ROOT / f for f in ("app.py", ".replit", "pyproject.toml", "uv.lock", ".env.example"))
    return {str(p.relative_to(ROOT)): digest(p) for p in sorted(paths) if p.exists()}


def freeze():
    if DATASET.exists():
        raise ValueError("Refusing to replace an existing frozen holdout")
    truth_path = ROOT / ".local/tasks/week4-generalization-ground-truth.json"
    truth = json.loads(truth_path.read_text())
    golden = json.loads((ROOT / "evaluation/golden/v1.json").read_text())
    cases = truth["cases"]
    checks = {
        "G01": [["sprint.done_count", 16], ["sprint.total_tickets", 24], ["sprint.completion_rate", 66.7]],
        "G02": [["sprint.story_points_completed", 59], ["sprint.story_points_scope", 83]],
        "G03": [["sprint.done_count", 16], ["sprint.blocked_count", 2], ["sprint.overdue_count", 8]],
        "G04": [["historical_comparison.1.blocked_count", 3], ["historical_comparison.2.blocked_count", 2]],
        "G05": [["sprint.sprint_name", "Sprint 25"], ["overdue_tasks.SP-123.days_overdue", 1]],
        "G06": [["sprint.sprint_name", "Sprint 24"], ["sprint.completion_rate", 41.7]],
        "G07": [["overdue_tasks.SP-121.days_overdue", 3], ["overdue_tasks.SP-121.status", "To Do"]],
        "G08": [["sprint.story_points_scope", 0], ["sprint.story_points_completed", 0], ["sprint.completion_rate", 66.7]],
        "G09": [["sprint.blocked_count", 2], ["overdue_tasks.TEST-118.status", "Blocked"], ["overdue_tasks.TEST-122.status", "Blocked"]],
        "G10": [["blocker_durations.TEST-122.duration_days", 32], ["blocker_durations.TEST-122.observed_in", "Sprint 26"]],
        "G11": [["sprint.blocked_count", 2], ["sprint.overdue_count", 7], ["overdue_tasks.$length", 7]],
        "G12": [["sprint.story_points_completed", 59], ["sprint.remaining_points", 24]],
        "G13": [["sprint.completion_rate", 66.7]],
        "G14": [["sprint.completion_rate", 66.7]],
    }
    for c in cases:
        c["route_label_status"] = "User-approved intended behavior; not an agent prediction."
        c["agent_execution"] = "NOT TESTED at freeze time; see separate run records for outcomes."
        c["route"] = c["intended_route"]
        c["sprint"] = {"G05": "Sprint 25", "G06": "Sprint 24"}.get(c["id"], "Sprint 26")
        c["category"] = "memory" if c["id"] in {"G12", "G13"} else "adversarial" if c["id"] == "G14" else "edge" if c["id"] in {"G06", "G08", "G09", "G10", "G11"} else "happy"
        c["checks"] = checks[c["id"]]
        c["na"] = [] if c["id"] in {"G12", "G13"} else ["memory_context_accuracy"]
        c["memory"] = {"recalled_min": 0, "recalled_max": 0 if c["id"] == "G13" else 3,
                       "request_reset": c["id"] == "G12"}
    payload = {
        "version": "holdout-v1.0.0", "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "authorization": "User explicitly approved Proposal B and all G01-G14; deterministic only; no application/label/production changes.",
        "provenance": {
            "reviewed_proposal": ".local/tasks/week4-generalization-evaluation.md",
            "reviewed_proposal_sha256": digest(ROOT / ".local/tasks/week4-generalization-evaluation.md"),
            "ground_truth_path": str(truth_path.relative_to(ROOT)),
            "ground_truth_sha256": digest(truth_path),
            "source_csv_sha256": truth["source_hashes"],
            "method": truth["verification_method"],
            "scope": truth["expected_behavior_scope"],
            "golden_v1_sha256": digest(ROOT / "evaluation/golden/v1.json"),
            "rubric_sha256": digest(ROOT / "evaluation/RUBRIC.md"),
            "baseline_snapshot": str(OLD.relative_to(ROOT)),
            "improved_snapshot": str(NEW.relative_to(ROOT)),
        },
        "route_contracts": golden["route_contracts"],
        "metric_na_reasons": {"memory_context_accuracy": "No conversation-memory assertion in this holdout case; excluded from memory denominator."},
        "targets": {"task_completion": .95, "answer_correctness": .95, "tool_routing_accuracy": .95, "memory_context_accuracy": 1, "p95_latency_ms": 2000},
        "review_policy": "Qualitative judgments require human acceptance. Agent-assisted review is separate and provisional; PENDING is not N/A.",
        "extra_runtime_gates": {"G12": ["successful_history_preserved", "failed_turn_excluded", "old_checkpoint_ids_preserved"],
                               "G13": ["different_key_recalled_zero"]},
        "planned_final_requests": 28, "planned_setup_requests": 6,
        "order_seed": 13017, "cases": cases,
    }
    DATASET.parent.mkdir(parents=True, exist_ok=False)
    DATASET.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    DATASET.with_suffix(".sha256").write_text(digest(DATASET) + "  evaluation/holdout/v1.json\n")
    DATASET.chmod(0o444)
    DATASET.with_suffix(".sha256").chmod(0o444)
    print(json.dumps({"dataset": str(DATASET.relative_to(ROOT)), "sha256": digest(DATASET), "cases": len(cases)}))


def execute():
    before = protected()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run = ROOT / ".local/evaluations" / ("holdout-v1-" + timestamp)
    run.mkdir()
    dataset = json.loads(DATASET.read_text())
    expected_digest = DATASET.with_suffix(".sha256").read_text().split()[0]
    assert digest(DATASET) == expected_digest
    verification = {}
    for label, archive in (("baseline", OLD), ("improved", NEW)):
        manifest = json.loads((archive / "source-snapshot-manifest.json").read_text())
        for filename, expected in manifest.items():
            assert digest(archive / "source-snapshot" / filename) == expected, filename
        destination = run / "sources" / label
        shutil.copytree(archive / "source-snapshot", destination)
        supplements = {}
        # The improved archive omitted this unchanged evaluation safety dependency.
        # Restore exact archived bytes only with independent pre-change provenance.
        before_improvement = json.loads((ROOT / ".local/evaluations/improvement-before.json").read_text())
        baseline_manifest = json.loads((OLD / "source-snapshot-manifest.json").read_text())
        for filename in ("reports/__init__.py", "reports/publisher.py"):
            if filename not in manifest:
                expected = baseline_manifest[filename]
                archived = OLD / "source-snapshot" / filename
                assert digest(archived) == before_improvement[filename] == digest(ROOT / filename) == expected
                target = destination / filename
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(archived, target)
                manifest[filename] = expected
                supplements[filename] = {
                    "sha256": expected, "source": str(archived.relative_to(ROOT)),
                    "proof": "Archived baseline bytes match pre-change fingerprint and unchanged current file.",
                }
        for filename in ("agents/graph.py", "agents/llm.py", "agents/memory.py",
                         "agents/semantic_memory.py", "agents/findings.py", "tools/sprint_data.py",
                         "tools/sprint_metrics.py", "evaluation/instrumentation.py",
                         "evaluation/scoring.py", "reports/publisher.py", "uv.lock"):
            assert filename in manifest
        verification[label] = {"snapshot": str(archive.relative_to(ROOT)), "source_sha256": manifest,
                               "supplemented_unchanged_dependencies": supplements}
    for filename in ("tools/sprint_data.py", "tools/sprint_metrics.py", "evaluation/instrumentation.py",
                     "evaluation/scoring.py", "agents/memory.py", "agents/llm.py", "uv.lock"):
        assert verification["baseline"]["source_sha256"][filename] == verification["improved"]["source_sha256"][filename]
    for filename, checksum in dataset["provenance"]["source_csv_sha256"].items():
        assert verification["baseline"]["source_sha256"][filename] == verification["improved"]["source_sha256"][filename] == checksum
    shutil.copy2(DATASET, run / "dataset.json")
    worker = ROOT / "evaluation/holdout_worker.py"
    shutil.copy2(worker, run / "worker.py")
    shutil.copy2(Path(__file__), run / "runner.py")
    cases = [c["id"] for c in dataset["cases"]]
    random.Random(dataset["order_seed"]).shuffle(cases)
    order = []
    for index, cid in enumerate(cases):
        order.extend((cid, version) for version in (("baseline", "improved") if index % 2 == 0 else ("improved", "baseline")))
    metadata = {
        "run_id": run.name, "mode": "offline deterministic; generation stubbed, not live",
        "dataset_sha256": expected_digest, "versions": verification,
        "python": sys.version, "executable": sys.executable,
        "worker_sha256": digest(worker), "runner_sha256": digest(Path(__file__)),
        "order": order, "protected_before": before,
        "safety": "Environment constructed without inherited credentials; socket networking denied; mem0 disabled; temporary SQLite per case/version; no report writes.",
    }
    (run / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    rows = []
    for cid, version in order:
        output = run / (version + "-" + cid + ".json")
        env = {
            "PATH": os.defpath, "HOME": str(run), "LANG": "C.UTF-8",
            "PYTHONDONTWRITEBYTECODE": "1", "LANGSMITH_TRACING": "false",
            "LANGCHAIN_TRACING_V2": "false", "LANGCHAIN_TRACING": "false",
            "LANGSMITH_OTEL_ENABLED": "false", "SPRINTPULSE_RUN_MEM0_LIVE_TESTS": "false",
        }
        process = subprocess.run(
            [sys.executable, str(worker), "--source", str(run / "sources" / version),
             "--dataset", str(DATASET), "--case-id", cid, "--output", str(output)],
            cwd=run / "sources" / version, env=env, text=True, capture_output=True, timeout=60,
        )
        (run / (version + "-" + cid + ".stderr.log")).write_text(process.stderr)
        if process.returncode:
            raise RuntimeError(f"Worker failed for {version}/{cid}; preserve this run and inspect its stderr before retrying")
        row = json.loads(output.read_text())
        row["version"] = version
        rows.append(row)
        print(f"{cid} {version}: actual route {row['actual_route']}; {row['trace']['latency_ms']} ms", flush=True)
    assert len(rows) == 28
    assert sum(len(r["setup_requests"]) for r in rows) == 6
    assert all(r["temporary_checkpoint_removed"] for r in rows)
    assert all(r["trace"]["network_attempts_blocked"] == 0 for r in rows)
    for cid in cases:
        pair = [r for r in rows if r["case_id"] == cid]
        assert pair[0]["fixture_sha256"] == pair[1]["fixture_sha256"]
    assert all(digest(ROOT / p) == expected for p, expected in before.items())
    metadata["protected_after_matches"] = True
    metadata["actual_final_requests"] = len(rows)
    metadata["actual_setup_requests"] = sum(len(r["setup_requests"]) for r in rows)
    metadata["paid_calls"] = metadata["network_attempts"] = 0
    (run / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    (run / "records.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    review = {
        "dataset_sha256": expected_digest, "records_sha256": digest(run / "records.jsonl"),
        "reviewer": "", "review_status": "PENDING independent human review",
        "cases": {
            version + "/" + c["id"]: {
                metric: {"value": None, "reason": ""}
                for metric in ("task_completion", "answer_correctness", "memory_context_accuracy") if metric not in c["na"]
            } for version in ("baseline", "improved") for c in dataset["cases"]
        },
    }
    (run / "human-review-template.json").write_text(json.dumps(review, indent=2) + "\n")
    print("RUN_DIR=" + str(run.relative_to(ROOT)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["freeze", "run"])
    args = parser.parse_args()
    freeze() if args.command == "freeze" else execute()
