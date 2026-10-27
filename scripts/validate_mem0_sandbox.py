"""Explicit development-only live validation, with bounded calls and exact cleanup.

Run: python -m scripts.validate_mem0_sandbox --live
Requires MEM0_TEST_API_KEY and the existing development DATABASE_URL.
Never sets the app's MEM0_ENABLED flag or uses its MEM0_API_KEY.
"""
from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
import copy
import io
import json
import logging
import os
from pathlib import Path
import tempfile
import time
from unittest.mock import patch
import uuid

from agents import graph, llm
from agents.findings import Finding
from agents.memory import new_conversation_key
from agents.semantic_ledger import PostgresLedger
from agents.semantic_memory import HostedMem0, SemanticMemory
from tools.sprint_data import load_sprint_data

ROOT = Path(__file__).resolve().parents[1]


def safe_error(exc):
    """Only classify errors; never return messages, requests, headers or DSNs."""
    original = type(exc).__name__
    current = exc
    for _ in range(6):
        response = getattr(current, "response", None)
        status = getattr(response, "status_code", None)
        if isinstance(status, int):
            return {"type": original, "http_status": status}
        current = getattr(current, "__context__", None)
        if current is None:
            break
    return {"type": original}


def result_rows(response):
    rows = response if isinstance(response, list) else response.get("results", [])
    return rows if isinstance(rows, list) else []


def acknowledgment_shape(response):
    """Fixed field names/types only; never retain keys or values from the body."""
    def kind(value):
        for cls, label in ((dict, "object"), (list, "array"), (str, "string"),
                           (bool, "boolean"), (int, "number"), (float, "number")):
            if isinstance(value, cls):
                return label
        return "null" if value is None else "other"

    shape = {"response_type": kind(response)}
    if not isinstance(response, dict):
        return shape
    shape["fields"] = {
        name: kind(response[name]) for name in ("status", "event_id", "message", "results")
        if name in response
    }
    shape["status_category"] = (
        response["status"] if isinstance(response.get("status"), str)
        and response["status"] in {"PENDING", "SUCCEEDED", "FAILED"} else "absent_or_other"
    )
    results = response.get("results")
    if isinstance(results, list):
        shape["result_count"] = len(results)
        shape["result_fields"] = [
            {name: kind(row[name]) for name in ("id", "event", "data") if name in row}
            if isinstance(row, dict) else {"item_type": kind(row)}
            for row in results[:3]
        ]
    return shape


class BoundedProvider(HostedMem0):
    def __init__(self, api_key):
        super().__init__(api_key)
        self.counts = {"add_attempts": 0, "search_attempts": 0, "list_attempts": 0, "delete_attempts": 0}
        self.write_error = {}
        self.write_acknowledgment = {}

    def add(self, record):
        if self.counts["add_attempts"] >= 1:
            raise RuntimeError("Validation allows exactly one add attempt.")
        self.counts["add_attempts"] += 1
        try:
            result = super().add(record)
            # Schema diagnostics only. Never retain response bodies or credentials.
            self.write_acknowledgment = acknowledgment_shape(result)
            return result
        except Exception as exc:
            self.write_error = safe_error(exc)
            raise

    def search(self, question, filters):
        if self.counts["search_attempts"] >= 12:
            raise RuntimeError("Validation semantic-search budget exhausted.")
        self.counts["search_attempts"] += 1
        return super().search(question, filters)

    def listed(self, filters):
        if self.counts["list_attempts"] >= 2:
            raise RuntimeError("Validation cleanup-read budget exhausted.")
        self.counts["list_attempts"] += 1
        return result_rows(self._sdk().get_all(filters=filters))

    def delete_exact(self, memory_id):
        if self.counts["delete_attempts"] >= 1:
            raise RuntimeError("Validation deletion budget exhausted.")
        self.counts["delete_attempts"] += 1
        return self._sdk().delete(memory_id, delete_linked=False)


class ReadOnlyGraphMemory:
    """Test-only dispatch guard: graph reads stay live; derived writes are suppressed."""
    def __init__(self, service):
        self.service = service
        self.project_scope = service.project_scope

    def recall(self, question, thread_id):
        return self.service.recall(question, thread_id)

    def remember(self, findings, thread_id):
        return "validation_read_only"

    def close(self):
        # The harness, not an individual graph call, owns this shared client.
        pass


class DiagnosticLedger(PostgresLedger):
    """Distinguish response parsing from transaction failures without row data."""
    def __init__(self, dsn):
        super().__init__(dsn)
        self.finalizations = []

    def finish(self, finding_id, status, event_id=None):
        diagnostic = {"target_status": status, "has_event_id": event_id is not None}
        self.finalizations.append(diagnostic)
        try:
            super().finish(finding_id, status, event_id)
            diagnostic["outcome"] = "committed"
        except Exception as exc:
            diagnostic.update(outcome="uncertain", error=safe_error(exc))
            raise


def cleanup(provider, ledger, record):
    scope = {key: record[key] for key in (
        "project_id", "owner_scope", "environment", "finding_id",
    )}
    filters = {"AND": [
        {"user_id": record["owner_scope"]},
        *[{"metadata": {key: value}} for key, value in scope.items()],
    ]}

    def owned(row):
        metadata = row.get("metadata", {})
        return (
            row.get("user_id") == record["owner_scope"]
            and all(metadata.get(key) == value for key, value in scope.items())
            and isinstance(row.get("id"), str)
        )

    rows = [row for row in provider.listed(filters) if owned(row)]
    if len(rows) > 1:
        return {"status": "FAIL", "reason": "Unexpected duplicate remote memories; no broad deletion attempted."}
    for row in rows:
        provider.delete_exact(row["id"])
    remaining = [row for row in provider.listed(filters) if owned(row)]
    rejected = provider.write_error.get("http_status") in {400, 401, 402, 403, 422}
    confirmed = not remaining and (bool(rows) or not provider.counts["add_attempts"] or rejected)
    if confirmed:
        with ledger._connection() as connection:
            connection.execute(
                """DELETE FROM public.sprintpulse_memory_ingestion
                   WHERE finding_id=%s AND project_id=%s AND owner_scope=%s AND environment=%s""",
                (record["finding_id"], record["project_id"], record["owner_scope"], record["environment"]),
            )
    return {
        "status": "PASS" if confirmed else "PARTIAL",
        "remote_records_deleted": len(rows), "remote_records_remaining": len(remaining),
        "ledger_row_deleted": confirmed,
        "uncertain_ingestion_retained": not confirmed,
    }


def run_validation():
    report = {
        "environment": "development", "checks": {}, "live_operations": {},
        "test_only_stubs": [
            "Additional graph-derived memory writes suppressed to enforce one synthetic add.",
            "Provider search raises TimeoutError during the simulated outage only.",
            "LLM bypassed for outage/recovery checks; fresh-data answer uses the existing LLM.",
        ],
    }
    if os.getenv("REPLIT_DEPLOYMENT") == "1" or not os.getenv("REPLIT_DEV_DOMAIN", "").endswith(".replit.dev"):
        return {**report, "status": "BLOCKED", "reason": "Production execution refused."}
    key = os.getenv("MEM0_TEST_API_KEY")
    dsn = os.getenv("DATABASE_URL")
    if not key or not dsn:
        return {**report, "status": "BLOCKED", "reason": "Development test credentials/backend missing."}

    project = f"sp_validate_{uuid.uuid4().hex[:12]}_test"
    capability = new_conversation_key()
    provider = BoundedProvider(key)
    ledger = DiagnosticLedger(dsn)
    service = SemanticMemory(project, "development", provider, ledger)
    finding = Finding(
        "recurring_blocker",
        "Synthetic historical blocker: SP-124 repeatedly waited for partner sandbox "
        "access approval in two prior sprints. Historical completion was 10%.",
        ("SP-124",), "Synthetic historical sprint", "2000-01-01T00:00:00+00:00",
        {"source": "isolated_synthetic_validation", "appearances": 2, "historical_completion_rate": 10},
    )
    record = finding.envelope(project, service._owner(capability), "development")
    stage = "readiness"
    original_logging_level = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        # Process-local telemetry suppression before importing the optional SDK.
        with patch.dict(os.environ, {"MEM0_TELEMETRY": "false"}), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            try:
                service._ensure_ready()
                report["checks"]["backend_and_authentication"] = "PASS"
                stage = "one_synthetic_write"
                status = service.remember([finding], capability)
                report["checks"][stage] = {"status": "PASS" if status == "pending" else "FAIL", "adapter_status": status}
                # Continue read diagnostics if the provider accepted a call without
                # an exception, even if the application rejected its acknowledgment.
                # The overall result must remain PARTIAL in that case.
                assert status == "pending" or (
                    provider.counts["add_attempts"] == 1 and not provider.write_error
                )
                stage = "paraphrased_retrieval"
                question = "Which work repeatedly stalled awaiting access to a partner testing environment?"
                matches = []
                for attempt in range(8):
                    matches, search_status = service.recall(question, capability)
                    if any(item["finding_id"] == record["finding_id"] for item in matches):
                        break
                    if attempt < 7:
                        time.sleep(3)
                assert any(item["finding_id"] == record["finding_id"] for item in matches)
                report["checks"][stage] = {
                    "status": "PASS", "query": question, "source_ticket_ids": ["SP-124"],
                    "historical": True,
                }
                stage = "project_isolation"
                other = SemanticMemory(project + "_other", "development", provider, ledger)
                isolated, state = other.recall(question, capability)
                assert state == "ok" and not isolated
                report["checks"][stage] = "PASS"
                stage = "conversation_isolation"
                isolated, state = service.recall(question, new_conversation_key())
                assert state == "ok" and not isolated
                report["checks"][stage] = "PASS"

                stage = "fresh_data_precedence"
                data = load_sprint_data(ROOT / "data")
                captured = {}

                def capture_answer(task, facts):
                    captured.update(copy.deepcopy(facts))
                    return llm.generate_grounded_text(task, facts)

                view = ReadOnlyGraphMemory(service)
                with tempfile.TemporaryDirectory(prefix="sp-mem0-") as temporary:
                    with patch.object(graph, "CHECKPOINT_PATH", Path(temporary) / "checkpoint.sqlite"), patch.object(
                        graph, "configured_semantic_memory", lambda: view
                    ):
                        with patch.object(graph, "generate_grounded_text", capture_answer):
                            current = graph.invoke_sprint_graph(
                                "For the historical sandbox access blocker, report CURRENT sprint completion "
                                "as the exact percentage from fresh tools, not the historical 10%.",
                                "Sprint 26", data, capability,
                            )
                        fresh = current["tool_outputs"]["sprint"]["completion_rate"]
                        assert fresh == 66.7
                        assert any(item["finding_id"] == record["finding_id"] for item in captured.get("semantic_memory", []))
                        assert all(not item["current_status_authority"] for item in captured["semantic_memory"])
                        live_llm = current["generation_mode"] == "LangChain LLM grounded in tool outputs"
                        assert "66.7%" in current["response"].replace(" ", "")
                        report["checks"][stage] = {
                            "status": "PASS" if live_llm else "PARTIAL",
                            "current_completion_rate": fresh, "stale_memory_completion_rate": 10,
                            "live_memory_reached_graph": True, "live_llm_answer_verified": live_llm,
                            "source_csv_SP124_status": str(data["Sprint 26"].set_index("ticket_id").loc["SP-124", "status"]),
                        }
                        stage = "simulated_outage"
                        with patch.object(provider, "search", side_effect=TimeoutError("synthetic outage")), patch.object(
                            graph, "generate_grounded_text", lambda *args: (None, "validation fallback")
                        ):
                            failed = graph.invoke_sprint_graph("Current completion metrics?", "Sprint 26", data, capability)
                        assert failed["semantic_memory_status"]["search"] == "unavailable"
                        assert failed["error"] is None and failed["tool_outputs"]["sprint"]["completion_rate"] == fresh
                        report["checks"][stage] = "PASS (simulated provider timeout; real graph/tools)"
                stage = "live_recovery"
                recovered, state = service.recall(question, capability)
                assert state == "ok" and recovered
                report["checks"][stage] = "PASS"
            except Exception as exc:
                report["checks"].setdefault(stage, {"status": "FAIL", **safe_error(exc)})
                report["failure_stage"] = stage
            finally:
                if service._ready:
                    try:
                        report["cleanup"] = cleanup(provider, ledger, record)
                    except Exception as exc:
                        report["cleanup"] = {"status": "PARTIAL", **safe_error(exc), "ledger_retained_for_reconciliation": True}
    finally:
        provider.close()
        logging.disable(original_logging_level)
    report["live_operations"] = provider.counts
    report["provider_write_error"] = provider.write_error
    report["provider_acknowledgment_shape"] = provider.write_acknowledgment
    report["ledger_finalizations"] = ledger.finalizations
    required = ["paraphrased_retrieval", "project_isolation", "conversation_isolation", "fresh_data_precedence",
                "simulated_outage", "live_recovery"]
    report["status"] = "PASS" if (
        not report.get("failure_stage") and all(name in report["checks"] for name in required)
        and report["checks"]["one_synthetic_write"]["status"] == "PASS"
        and report["checks"]["fresh_data_precedence"].get("status") == "PASS"
        and report.get("cleanup", {}).get("status") == "PASS"
    ) else "PARTIAL"
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Explicitly permit approved sandbox API calls.")
    args = parser.parse_args()
    if not args.live:
        parser.error("--live is required; this command writes one synthetic remote finding.")
    try:
        result = run_validation()
    except Exception as exc:
        result = {"status": "FAIL", "sanitized_error": safe_error(exc)}
    destination = ROOT / ".local" / "validation" / "mem0-sandbox-result.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
