"""Offline subprocess worker; imports application code only from a verified copy."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import socket
import sqlite3
import sys
import tempfile
import time
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = args.source.resolve()
    sys.path.insert(0, str(source))
    outbound = []

    def deny_network(*unused, **kwargs):
        outbound.append("network operation blocked")
        raise RuntimeError("Network forbidden during offline holdout")

    socket.socket.connect = deny_network
    socket.socket.connect_ex = deny_network
    socket.create_connection = deny_network
    socket.getaddrinfo = deny_network

    import pandas as pd
    from langsmith import tracing_context
    from langgraph.checkpoint.sqlite import SqliteSaver
    from agents import graph, llm, memory as checkpoint_memory
    from agents.semantic_memory import DisabledMemory
    from reports import publisher
    from tools.sprint_data import load_sprint_data
    from evaluation.instrumentation import Capture, instrument, redact
    from evaluation.scoring import evidence_checks, score_case

    for module in (graph, llm, checkpoint_memory, publisher):
        assert Path(module.__file__).resolve().is_relative_to(source)
    dataset = json.loads(args.dataset.read_text())
    case = next(c for c in dataset["cases"] if c["id"] == args.case_id)
    snapshots = load_sprint_data(source / "data")
    if case["id"] == "G08":
        snapshots["Sprint 26"]["story_points"] = 0
    if case["id"] in {"G09", "G10"}:
        for frame in snapshots.values():
            frame["ticket_id"] = frame.ticket_id.str.replace("SP-", "TEST-", regex=False)
    if case["id"] == "G11":
        snapshots["Sprint 26"].loc[
            snapshots["Sprint 26"].ticket_id == "SP-122", "due_date"
        ] = pd.Timestamp("2026-07-20")

    fixture_digest = hashlib.sha256("".join(
        name + frame.to_json(orient="split", date_format="iso")
        for name, frame in snapshots.items()
    ).encode()).hexdigest()
    capture = Capture()
    disabled = DisabledMemory()
    disabled.project_scope = "development:holdout-offline-synthetic"
    key = checkpoint_memory.new_conversation_key()
    observations, setups = {}, []
    with tempfile.TemporaryDirectory(prefix="holdout-checkpoints-", dir=args.output.parent) as tmp:
        checkpoint_path = Path(tmp) / "checkpoints.sqlite"
        with ExitStack() as stack:
            stack.enter_context(tracing_context(enabled=False))
            stack.enter_context(patch.object(graph, "CHECKPOINT_PATH", checkpoint_path))
            stack.enter_context(patch.object(graph, "configured_semantic_memory", lambda: disabled))
            stack.enter_context(patch.object(graph, "configured_project_scope", lambda: disabled.project_scope))
            stack.enter_context(patch.object(
                publisher, "save_approved_report",
                side_effect=RuntimeError("Report saving forbidden during holdout"),
            ))
            stack.enter_context(patch.object(
                llm, "_client", side_effect=RuntimeError("Live LLM forbidden during holdout"),
            ))
            instrument(stack, capture, "deterministic")

            def ask(question, phase, sprint="Sprint 26"):
                capture.phase = phase
                start = time.perf_counter()
                try:
                    result = graph.invoke_sprint_graph(question, sprint, snapshots, key)
                    exception = None
                except Exception as exc:
                    exception = type(exc).__name__
                    result = {"response": "", "error": "Graph exception: " + exception, "errors": [exception]}
                return result, round((time.perf_counter() - start) * 1000, 3), exception

            def history():
                with sqlite3.connect(checkpoint_path) as connection:
                    saver = SqliteSaver(connection)
                    turns = checkpoint_memory.completed_turns(saver, key)
                    ids = {row[0] for row in connection.execute("SELECT checkpoint_id FROM checkpoints")}
                    safe_turns = [
                        {"question": t["question"], "answer": t["response"], "findings": t["tool_outputs"]}
                        for t in turns
                    ]
                    return safe_turns, ids

            old_ids, success_digest, failed_prompt = set(), None, None
            if case["id"] in {"G12", "G13"}:
                setup, latency, exception = ask(
                    "What blockers are open for SP-118?", "setup-success"
                )
                setups.append({"phase": "setup-success", "result": setup, "latency_ms": latency, "exception": exception})
            if case["id"] == "G12":
                turns, old_ids = history()
                assert turns, "Successful setup must produce completed history"
                success_digest = hashlib.sha256(json.dumps(turns[0], sort_keys=True).encode()).hexdigest()
                failed_prompt = "Show completion metrics during the controlled outage."
                capture.fail_overdue = True
                setup, latency, exception = ask(failed_prompt, "setup-failure")
                setups.append({"phase": "setup-failure", "result": setup, "latency_ms": latency, "exception": exception})
                observations["setup_error"] = bool(setup.get("error"))
                observations["setup_error_count"] = setup.get("error_count")
            if case["id"] == "G13":
                key = checkpoint_memory.new_conversation_key()
            capture.fail_overdue = False
            result, latency, exception = ask(case["prompt"], "evaluation", case["sprint"])
            turns, final_ids = history()
            if case["id"] == "G12":
                preserved = any(
                    hashlib.sha256(json.dumps(t, sort_keys=True).encode()).hexdigest() == success_digest
                    for t in turns
                )
                observations.update({
                    "request_reset": (
                        not result.get("error") and not result.get("errors")
                        and result.get("error_count") == 0 and result.get("report") == ""
                    ),
                    "successful_history_preserved": preserved,
                    "failed_turn_excluded": not any(t["question"] == failed_prompt for t in turns),
                    "old_checkpoint_ids_preserved": bool(old_ids) and old_ids <= final_ids,
                })
            if case["id"] == "G13":
                observations["different_key_recalled_zero"] = result.get("recalled_turns") == 0
            observations["completed_history_questions"] = [t["question"] for t in turns]

    trace = {
        "nodes": capture.nodes, "tools": capture.tools, "model_calls": capture.model_calls,
        "latency_ms": latency, "exception": exception, "memory_observations": observations,
        "live_llm_executed": False, "mem0_backend": "DisabledMemory",
        "network_attempts_blocked": len(outbound),
    }
    assert not outbound
    assert not any(c["live_llm_executed"] for c in capture.model_calls)
    row = redact({
        "case_id": case["id"], "category": case["category"], "prompt": case["prompt"],
        "expected_behavior": case["expected_behavior"], "sprint": case["sprint"],
        "expected_route": case["route"], "actual_route": result.get("route"),
        "final_answer": result.get("response", ""), "result": result, "trace": trace,
        "setup_requests": setups, "fixture_sha256": fixture_digest,
        "application_graph_file": str(Path(graph.__file__).relative_to(source)),
        "tool_evidence_checks": evidence_checks(case, result.get("tool_outputs", {})),
        "scores": score_case(case, result, trace, dataset, "deterministic"),
        "temporary_checkpoint_removed": not checkpoint_path.exists(),
    })
    args.output.write_text(json.dumps(row, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
