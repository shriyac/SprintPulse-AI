"""Approved one-write live retrieval test; retains its record for reconciliation.

python -m scripts.validate_mem0_retrieval --live
Never enables the application, deletes memories, or uses existing checkpoints.
"""
from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
import copy
from importlib.metadata import version
import io
import json
import logging
import os
from pathlib import Path
import tempfile
import time
from unittest.mock import patch
import uuid

from langchain_core.callbacks import BaseCallbackHandler

from agents import graph, llm
from agents.findings import Finding
from agents.memory import new_conversation_key
from agents.semantic_memory import SemanticMemory
from scripts.validate_mem0_ack import filters_for, ledger_rows, owned
from scripts.validate_mem0_sandbox import (
    BoundedProvider, DiagnosticLedger, ReadOnlyGraphMemory, safe_error,
)
from tools.sprint_data import load_sprint_data

ROOT = Path(__file__).resolve().parents[1]


class RetrievalProvider(BoundedProvider):
    def __init__(self, key, deadline):
        super().__init__(key)
        self.deadline = deadline
        self.search_schemas = []

    def check_deadline(self):
        if time.monotonic() >= self.deadline:
            raise TimeoutError("Validation deadline reached")

    def add(self, record):
        self.check_deadline()
        return super().add(record)

    def search(self, question, filters):
        self.check_deadline()
        response = super().search(question, filters)
        rows = response.get("results") if isinstance(response, dict) else None
        self.search_schemas.append({
            "response_type": "object" if isinstance(response, dict) else "other",
            "result_count": len(rows) if isinstance(rows, list) else None,
            "rows": [{
                "score": row.get("score") if isinstance(row.get("score"), (float, int)) else None,
                "has_user_id": isinstance(row.get("user_id"), str),
                "metadata_types": {
                    key: type(row.get("metadata", {}).get(key)).__name__
                    for key in ("source_ticket_ids", "evidence", "summary", "finding_id")
                } if isinstance(row.get("metadata"), dict) else {},
            } for row in (rows or [])[:3] if isinstance(row, dict)],
        })
        return response

    def listed(self, filters):
        self.check_deadline()
        return super().listed(filters)

    def delete_exact(self, memory_id):
        raise RuntimeError("Deletion is not approved for this validation.")


class NodeTrace(BaseCallbackHandler):
    def __init__(self):
        self.nodes = []

    def on_chain_start(self, serialized, inputs, **kwargs):
        node = (kwargs.get("metadata") or {}).get("langgraph_node")
        allowed = {
            "recall_conversation", "route_request", "retrieve_sprint_health", "detect_risk",
            "compare_sprint_history", "gather_report_evidence", "retrieve_question_context",
            "remember_findings", "answer", "report",
        }
        if node in allowed and (not self.nodes or self.nodes[-1] != node):
            self.nodes.append(node)


def run_validation():
    report = {"status": "PARTIAL", "environment": "development", "checks": {},
              "retention": "Remote record and ledger retained; no cleanup authorized.",
              "llm_calls": 0, "poll_diagnostics": []}
    if os.getenv("REPLIT_DEPLOYMENT") == "1" or not os.getenv("REPLIT_DEV_DOMAIN", "").endswith(".replit.dev"):
        return {**report, "status": "BLOCKED", "reason": "Development editor required."}
    if not os.getenv("MEM0_TEST_API_KEY") or not os.getenv("DATABASE_URL"):
        return {**report, "status": "BLOCKED", "reason": "Dedicated test credentials/backend missing."}
    if not (os.getenv("AI_INTEGRATIONS_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")):
        return {**report, "status": "BLOCKED", "reason": "Existing LLM configuration missing."}
    if version("mem0ai") != "2.2.1":
        return {**report, "status": "BLOCKED", "reason": "Unexpected SDK version."}
    started = time.monotonic()
    provider = RetrievalProvider(os.environ["MEM0_TEST_API_KEY"], started + 90)
    ledger = DiagnosticLedger(os.environ["DATABASE_URL"])
    project = "sp_validate_" + uuid.uuid4().hex[:12] + "_test"
    capability = new_conversation_key()
    service = SemanticMemory(project, "development", provider, ledger)
    finding = Finding(
        "recurring_blocker",
        "Synthetic historical blocker: SP-124 repeatedly waited for ORBITGLASS partner sandbox "
        "access approval in two prior sprints. Historical completion was 10%.",
        ("SP-124",), "Synthetic historical sprint", "2000-01-01T00:00:00+00:00",
        {"source": "isolated_synthetic_retrieval_validation", "appearances": 2, "historical_completion_rate": 10},
    )
    record = finding.envelope(project, service._owner(capability), "development")
    report["synthetic_reference"] = {"project_id": project, "finding_id": record["finding_id"]}
    stage = "preflight"
    previous_logging = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        with patch.dict(os.environ, {"MEM0_TELEMETRY": "false"}), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            try:
                service._ensure_ready()
                assert ledger_rows(ledger, record) == []
                assert provider.listed(filters_for(record)) == []
                report["checks"][stage] = "PASS"
                stage = "live_write_acknowledgment"
                assert service.remember([finding], capability) == "pending"
                report["checks"][stage] = "PASS"
                stage = "ledger_and_duplicates"
                rows = ledger_rows(ledger, record)
                assert len(rows) == 1 and rows[0][0] == "pending"
                assert service.remember([finding], capability) == "unchanged"
                assert provider.counts["add_attempts"] == 1
                report["checks"][stage] = "PASS"
                stage = "exact_retrieval"
                rows = provider.listed(filters_for(record))
                assert len(rows) == 1 and owned(rows[0], record)
                assert rows[0].get("memory") == record["summary"]
                report["synthetic_reference"]["provider_memory_id"] = rows[0]["id"]
                report["checks"][stage] = "PASS"
                stage = "paraphrased_retrieval"
                question = "Which work repeatedly stalled awaiting access approval for a partner testing environment?"
                for attempt in range(8):
                    matches, status = service.recall(question, capability)
                    report["poll_diagnostics"].append(copy.deepcopy(service.last_recall_diagnostics))
                    if status != "ok":
                        raise RuntimeError("Memory search unavailable")
                    if any(item["finding_id"] == record["finding_id"] for item in matches):
                        break
                    provider.check_deadline()
                    if attempt < 7:
                        time.sleep(2)
                assert any(item["finding_id"] == record["finding_id"] for item in matches)
                assert matches[0]["source_ticket_ids"] == ["SP-124"]
                assert matches[0]["observed_at"] == finding.observed_at
                report["checks"][stage] = "PASS"
                stage = "project_isolation"
                other = SemanticMemory(project + "_other", "development", provider, ledger)
                assert other.recall(question, capability) == ([], "ok")
                report["checks"][stage] = "PASS"
                stage = "conversation_isolation"
                assert service.recall(question, new_conversation_key()) == ([], "ok")
                report["checks"][stage] = "PASS"
                stage = "live_graph_and_llm"
                captured = {}
                trace = NodeTrace()
                original_builder = graph.build_sprint_graph

                def traced_builder(*args, **kwargs):
                    compiled = original_builder(*args, **kwargs)

                    class TracedGraph:
                        def invoke(self, state, config):
                            return compiled.invoke(state, config={**config, "callbacks": [trace]})

                    return TracedGraph()

                def capture_answer(task, facts):
                    provider.check_deadline()
                    if report["llm_calls"] >= 1:
                        raise RuntimeError("Only one LLM call is approved.")
                    report["llm_calls"] += 1
                    captured.update(copy.deepcopy(facts))
                    return llm.generate_grounded_text(task, facts)

                data = load_sprint_data(ROOT / "data")
                with tempfile.TemporaryDirectory(prefix="sp-live-retrieval-") as temporary:
                    with patch.object(graph, "CHECKPOINT_PATH", Path(temporary) / "checkpoints.sqlite"), patch.object(
                        graph, "configured_semantic_memory", lambda: ReadOnlyGraphMemory(service)
                    ), patch.object(graph, "build_sprint_graph", traced_builder):
                        with patch.object(graph, "generate_grounded_text", capture_answer):
                            result = graph.invoke_sprint_graph(
                                "Explain the historical ORBITGLASS partner sandbox access blocker for SP-124. "
                                "Give CURRENT sprint completion as an exact percentage from fresh tools, "
                                "not the historical 10%. Label historical evidence separately.",
                                "Sprint 26", data, capability,
                            )
                        insights = captured.get("semantic_memory", [])
                        assert any(item["finding_id"] == record["finding_id"] for item in insights)
                        assert all(item["current_status_authority"] is False for item in insights)
                        fresh = result["tool_outputs"]["sprint"]["completion_rate"]
                        assert fresh == 66.7 and captured["sprint"]["completion_rate"] == fresh
                        assert result["generation_mode"] == "LangChain LLM grounded in tool outputs"
                        answer = result["response"]
                        assert "66.7%" in answer.replace(" ", "")
                        assert "SP-124" in answer and "ORBITGLASS" in answer
                        assert "histor" in answer.lower() and "access" in answer.lower()
                        assert result["semantic_memory_status"]["write"] == "validation_read_only"
                        report["graph_evidence"] = {
                            "nodes": list(trace.nodes), "route": result["route"],
                            "tool_output_keys": list(result["tool_outputs"]),
                            "historical_finding_reached_llm": True, "source_ticket_ids": ["SP-124"],
                            "historical_timestamp_preserved": True, "current_completion_rate": fresh,
                            "historical_completion_rate": 10, "answer_checks_passed": True,
                        }
                        report["checks"][stage] = "PASS"
                        stage = "simulated_outage"
                        with patch.object(provider, "search", side_effect=TimeoutError("synthetic outage")), patch.object(
                            graph, "generate_grounded_text", lambda *args: (None, "validation deterministic fallback")
                        ):
                            failed = graph.invoke_sprint_graph("Current completion metrics?", "Sprint 26", data, capability)
                        assert not failed["error"] and failed["semantic_memory_status"]["search"] == "unavailable"
                        assert failed["tool_outputs"]["sprint"]["completion_rate"] == fresh
                        report["checks"][stage] = "PASS (simulated timeout; real graph/tools; no live LLM)"
                stage = "live_recovery"
                recovered, status = service.recall(question, capability)
                assert status == "ok" and any(item["finding_id"] == record["finding_id"] for item in recovered)
                report["checks"][stage] = "PASS"
                report["status"] = "PASS"
            except Exception as exc:
                report["checks"][stage] = "FAIL"
                report["failure"] = {"stage": stage, **safe_error(exc)}
                report["stopped_without_write_retry"] = True
    finally:
        provider.close()
        logging.disable(previous_logging)
    report["provider_acknowledgment_shape"] = provider.write_acknowledgment
    report["provider_search_schemas"] = provider.search_schemas
    report["ledger_finalizations"] = ledger.finalizations
    report["live_operations"] = provider.counts
    report["elapsed_seconds"] = round(time.monotonic() - started, 2)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    if not parser.parse_args().live:
        parser.error("--live requires separate approval for one synthetic add.")
    try:
        report = run_validation()
    except Exception as exc:
        report = {"status": "FAIL", "sanitized_error": safe_error(exc)}
    destination = ROOT / ".local/validation/mem0-retrieval-live-result.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
