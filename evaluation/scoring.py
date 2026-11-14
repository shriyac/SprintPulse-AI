"""Transparent, human-reviewed scores; tool evidence is not answer correctness."""
from __future__ import annotations

import math

from evaluation.verify import METRICS, lookup

TARGETS = {
    "task_completion": 0.95, "answer_correctness": 0.95,
    "tool_routing_accuracy": 0.95, "memory_context_accuracy": 1.0,
    "p95_latency": {"deterministic": 2000, "live": 35000},
}


def scored(value=None, reason=None):
    if reason:
        return {"status": "N/A", "value": None, "reason": reason}
    return {"status": "PENDING" if value is None else "SCORED", "value": value, "reason": None}


def evidence_checks(case, outputs):
    checks = []
    for path, expected in case["checks"]:
        try:
            actual = lookup(outputs, path)
            matches = actual == expected
        except (KeyError, IndexError, TypeError, ValueError):
            actual, matches = None, False
        checks.append({"path": path, "expected": expected, "actual": actual, "passed": matches})
    return checks


def score_case(case, result, trace, dataset, mode, review=None):
    route = case["route"]
    contract = dataset["route_contracts"][route]
    expected_error = case.get("behavior", {}).get("error_expected", False)
    expected_tools = case.get("behavior", {}).get("expected_tools", contract["tools"])
    events = [event for event in trace["nodes"] if event["phase"] == "evaluation"]
    tools = [event for event in trace["tools"] if event["phase"] == "evaluation"]
    expected_nodes = [
        "recall_conversation", "route_request", contract["node"], "remember_findings",
        "report" if route == "report" else "answer",
    ]
    output_keys = [] if expected_error else contract["outputs"]
    routing = (
        result.get("route") == route
        and [e["node"] for e in events] == expected_nodes
        and {e["tool"] for e in tools} == set(expected_tools)
        and set(result.get("tool_outputs", {})) == set(output_keys)
    )
    scores = {metric: scored() for metric in METRICS}
    scores["tool_routing_accuracy"] = scored(int(routing))
    for metric in case["na"]:
        scores[metric] = scored(reason=dataset["metric_na_reasons"][metric])
    # Time every attempted final graph request, including failures/fallbacks;
    # excluding slow provider failures would bias the latency statistic.
    scores["p95_latency"] = scored(trace["latency_ms"])
    # Human judgements are required for meaning, completeness, unsupported claims,
    # and labeling historical context. Never infer these from correct tool JSON.
    review = review or {}
    for metric in ("task_completion", "answer_correctness", "memory_context_accuracy"):
        if scores[metric]["status"] == "N/A" or metric not in review:
            continue
        entry = review[metric]
        if entry.get("value") is None:
            continue
        if type(entry.get("value")) is not int or entry["value"] not in (0, 1) or not entry.get("reason"):
            raise ValueError(f"Review {case['id']}/{metric} needs value 0/1 and a reason.")
        value = entry["value"]
        runtime_ok = (
            bool(result.get("response", "").strip())
            and trace.get("exception") is None
            and bool(result.get("error")) == expected_error
            and result.get("error_count", 0) <= 2
        )
        if expected_error:
            runtime_ok = (
                runtime_ok and result.get("error_count") == 1
                and result.get("generation_mode") == "tools unavailable"
                and not result.get("tool_outputs")
                and not any(call["phase"] == "evaluation" for call in trace["model_calls"])
            )
        if metric == "task_completion":
            value = int(bool(value) and runtime_ok)
        if metric == "answer_correctness":
            value = int(
                bool(value) and runtime_ok
                and all(c["passed"] for c in evidence_checks(case, result.get("tool_outputs", {})))
            )
        if metric == "memory_context_accuracy":
            expected = case["memory"]
            observed = trace["memory_observations"]
            count = result.get("recalled_turns", 0)
            gates = expected["recalled_min"] <= count <= expected["recalled_max"]
            for gate in ("restore_matches", "request_reset"):
                if expected.get(gate):
                    gates = gates and observed.get(gate, False)
            value = int(bool(value) and gates)
        scores[metric] = scored(value)
        scores[metric]["review_reason"] = entry["reason"]
    return scores


def nearest_rank_p95(samples):
    if not samples:
        return None
    return sorted(samples)[math.ceil(0.95 * len(samples)) - 1]


def summarize(rows, mode):
    summary = {}
    for metric in METRICS:
        applicable = [row["scores"][metric] for row in rows if row["scores"][metric]["status"] != "N/A"]
        completed = [score for score in applicable if score["status"] == "SCORED"]
        pending = len(applicable) - len(completed)
        values = [score["value"] for score in completed]
        value = None
        if applicable and not pending:
            value = nearest_rank_p95(values) if metric == "p95_latency" else sum(values) / len(applicable)
        target = TARGETS[metric][mode] if metric == "p95_latency" else TARGETS[metric]
        summary[metric] = {
            "value": value, "target": target, "applicable_denominator": len(applicable),
            "scored": len(completed), "pending": pending,
            "not_applicable": len(rows) - len(applicable),
            "passed": None if value is None else value <= target if metric == "p95_latency" else value >= target,
        }
    return summary
