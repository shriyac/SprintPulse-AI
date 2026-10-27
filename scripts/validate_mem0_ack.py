"""One-write development acknowledgment validation. Never retries uncertain writes.

Run only with separate approval: python -m scripts.validate_mem0_ack --live
"""
from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
from importlib.metadata import version
import io
import json
import logging
import os
from pathlib import Path
from unittest.mock import patch
import uuid

from agents.findings import Finding
from agents.memory import new_conversation_key
from agents.semantic_memory import SemanticMemory
from scripts.validate_mem0_sandbox import (
    BoundedProvider, DiagnosticLedger, result_rows, safe_error,
)


class OneWriteProvider(BoundedProvider):
    def __init__(self, key):
        super().__init__(key)
        self.last_response = None

    def add(self, record):
        self.last_response = super().add(record)
        return self.last_response

    def search(self, question, filters):
        if self.counts["search_attempts"] >= 1:
            raise RuntimeError("One semantic search maximum.")
        return super().search(question, filters)

    def listed(self, filters):
        if self.counts["list_attempts"] >= 4:
            raise RuntimeError("Four scoped listings maximum.")
        self.counts["list_attempts"] += 1
        return result_rows(self._sdk().get_all(filters=filters))


def filters_for(record):
    return {"AND": [
        {"user_id": record["owner_scope"]},
        *[{"metadata": {key: record[key]}} for key in
          ("project_id", "owner_scope", "environment", "finding_id")],
    ]}


def owned(row, record):
    return (
        isinstance(row, dict) and isinstance(row.get("metadata"), dict)
        and isinstance(row.get("id"), str) and bool(row["id"].strip())
        and row.get("user_id") == record["owner_scope"]
        and all(row["metadata"].get(key) == record[key] for key in
                ("project_id", "owner_scope", "environment", "finding_id"))
    )


def ledger_rows(ledger, record):
    with ledger._connection() as connection:
        return connection.execute(
            """SELECT status, event_id FROM public.sprintpulse_memory_ingestion
               WHERE finding_id=%s AND project_id=%s AND owner_scope=%s AND environment=%s""",
            tuple(record[key] for key in ("finding_id", "project_id", "owner_scope", "environment")),
        ).fetchall()


def run_validation():
    names = ("live_write_acknowledgment", "ledger_finalization", "duplicate_prevention",
             "exact_retrieval", "semantic_retrieval", "project_isolation", "synthetic_data_cleanup")
    report = {"environment": "development", "checks": {name: "NOT RUN" for name in names},
              "live_operations": {}, "ledger_transitions": [], "status": "PARTIAL"}
    if os.getenv("REPLIT_DEPLOYMENT") == "1" or not os.getenv("REPLIT_DEV_DOMAIN", "").endswith(".replit.dev"):
        return {**report, "status": "BLOCKED", "reason": "Development editor required."}
    key, dsn = os.getenv("MEM0_TEST_API_KEY"), os.getenv("DATABASE_URL")
    if not key or not dsn:
        return {**report, "status": "BLOCKED", "reason": "Dedicated test credentials/backend missing."}
    if version("mem0ai") != "2.2.1":
        return {**report, "status": "BLOCKED", "reason": "SDK version mismatch."}
    project = "sp_validate_" + uuid.uuid4().hex[:12] + "_test"
    capability = new_conversation_key()
    provider, ledger = OneWriteProvider(key), DiagnosticLedger(dsn)
    service = SemanticMemory(project, "development", provider, ledger)
    finding = Finding(
        "recurring_blocker",
        "Synthetic historical blocker: SP-124 repeatedly waited for partner sandbox access approval.",
        ("SP-124",), "Synthetic historical sprint", "2000-01-01T00:00:00+00:00",
        {"source": "isolated_synthetic_ack_validation", "appearances": 2},
    )
    record = finding.envelope(project, service._owner(capability), "development")
    # Synthetic reconciliation references only; no capability, owner hash or body.
    report["synthetic_reference"] = {"project_id": project, "finding_id": record["finding_id"]}
    report["sdk_version"] = "2.2.1"
    stage = "preflight"
    previous_logging = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        with patch.dict(os.environ, {"MEM0_TELEMETRY": "false"}), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            try:
                service._ensure_ready()
                other = SemanticMemory(project + "_other", "development", provider, ledger)
                assert other._owner(capability) != record["owner_scope"]
                assert service._owner(new_conversation_key()) != record["owner_scope"]
                assert ledger_rows(ledger, record) == []
                assert provider.listed(filters_for(record)) == []
                report["preflight"] = "PASS: authentication, ledger connectivity, empty unique namespace, distinct owner scopes"
                # Enqueue twice deliberately: verify the actual PostgreSQL unique guard.
                ledger.enqueue([record, record])
                assert ledger_rows(ledger, record) == [("queued", None)]
                report["ledger_transitions"].append("queued (one row after two enqueues)")

                stage = "live_write_acknowledgment"
                status = service.remember([finding], capability)
                assert status == "pending"
                response = provider.last_response
                assert isinstance(response, dict) and isinstance(response.get("results"), list)
                assert len(response["results"]) == 1
                result = response["results"][0]
                assert result["event"] == "ADD" and result["data"]["memory"] == record["summary"]
                memory_id = result["id"]
                assert isinstance(memory_id, str) and memory_id.strip()
                report["checks"][stage] = "PASS"
                report["acknowledgment_validation"] = {
                    "synchronous": True, "nonempty_memory_id": True, "exact_content_match": True,
                }

                stage = "ledger_finalization"
                assert ledger_rows(ledger, record) == [("pending", None)]
                assert ledger.finalizations == [{
                    "target_status": "pending", "has_event_id": False, "outcome": "committed",
                }]
                report["ledger_transitions"] += ["reserved (atomic claim)", "pending (commit verified by separate read)"]
                report["checks"][stage] = "PASS"

                stage = "duplicate_prevention"
                assert service.remember([finding], capability) == "unchanged"
                assert ledger_rows(ledger, record) == [("pending", None)]
                assert provider.counts["add_attempts"] == 1
                report["checks"][stage] = "PASS"

                stage = "exact_retrieval"
                rows = provider.listed(filters_for(record))
                assert len(rows) == 1 and owned(rows[0], record)
                assert rows[0]["id"] == memory_id and rows[0].get("memory") == record["summary"]
                report["checks"][stage] = "PASS"

                stage = "project_isolation"
                foreign = {**record, "project_id": other.project, "owner_scope": other._owner(capability)}
                assert provider.listed(filters_for(foreign)) == []
                report["checks"][stage] = "PASS"

                stage = "semantic_retrieval"
                matches, search_status = service.recall(
                    "Which work repeatedly stalled awaiting access to a partner testing environment?", capability,
                )
                assert search_status == "ok"
                assert len(matches) == 1 and matches[0]["finding_id"] == record["finding_id"]
                report["checks"][stage] = "PASS"

                stage = "synthetic_data_cleanup"
                # Exact ID was matched to scoped, owned content above. No delete_all.
                provider.delete_exact(memory_id)
                assert provider.listed(filters_for(record)) == []
                with ledger._connection() as connection:
                    deleted = connection.execute(
                        """DELETE FROM public.sprintpulse_memory_ingestion
                           WHERE finding_id=%s AND project_id=%s AND owner_scope=%s
                             AND environment=%s AND status='pending'""",
                        tuple(record[key] for key in ("finding_id", "project_id", "owner_scope", "environment")),
                    )
                    assert deleted.rowcount == 1
                assert ledger_rows(ledger, record) == []
                report["checks"][stage] = "PASS"
                report["status"] = "PASS"
            except Exception as exc:
                report["checks"][stage] = "FAIL"
                report["failure"] = {"stage": stage, **safe_error(exc)}
                report["stopped_without_retry"] = True
                report["cleanup_status"] = "NOT VERIFIED; no further calls after failure"
                # Keep uncertain records/claims for deliberate reconciliation.
    finally:
        provider.close()
        logging.disable(previous_logging)
    report["live_operations"] = provider.counts
    report["provider_acknowledgment_shape"] = provider.write_acknowledgment
    report["ledger_finalizations"] = ledger.finalizations
    report["provider_write_error"] = provider.write_error
    provider.last_response = None
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    if not parser.parse_args().live:
        parser.error("--live requires separate approval for one add operation.")
    try:
        report = run_validation()
    except Exception as exc:
        report = {"status": "FAIL", "sanitized_error": safe_error(exc)}
    destination = Path(__file__).resolve().parents[1] / ".local/validation/mem0-ack-result.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
