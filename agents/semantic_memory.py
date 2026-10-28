"""Optional hosted mem0 adapter. No SDK, database or network access when disabled."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import logging
import math
import os
import re
from typing import Any

from agents.findings import Finding, canonical
from agents.memory import valid_conversation_key

LOGGER = logging.getLogger(__name__)
MAX_RESULTS = 3
MAX_WRITES = 3
# V3 returns fused hybrid scores, not cosine similarity. A verified live
# paraphrase scored 0.2717; the former 0.45 cutoff rejected it. Use the
# documented V3 default while retaining independent scope/provenance checks.
MIN_SCORE = 0.1
KINDS = {"recurring_blocker", "risk", "dependency", "decision"}


def ingestion_acknowledgment(response, record) -> str | None:
    """Validate the hosted V3 contract; return an async event ID, or None.

    infer=False may finish synchronously with results instead of an event ID.
    Neither a 200 response nor a generic success message proves ingestion.
    """
    if not isinstance(response, dict):
        raise ValueError("Unconfirmed memory ingestion")
    status = response.get("status")
    event_id = response.get("event_id")
    if status == "PENDING" and isinstance(event_id, str) and event_id.strip():
        return event_id
    results = response.get("results")
    if status not in (None, "SUCCEEDED") or not isinstance(results, list) or len(results) != 1:
        raise ValueError("Unconfirmed memory ingestion")
    result = results[0]
    if (
        not isinstance(result, dict) or result.get("event") != "ADD"
        or not isinstance(result.get("id"), str) or not result["id"].strip()
        or not isinstance(result.get("data"), dict)
        or result["data"].get("memory") != record["summary"]
    ):
        raise ValueError("Unconfirmed memory ingestion")
    # No schema migration or remote ID masquerading as an async event ID.
    # The ledger remains pending reconciliation, including semantic visibility.
    return None


def configured_project_scope() -> str | None:
    project = os.getenv("MEM0_PROJECT_ID", "")
    environment = os.getenv("MEM0_ENVIRONMENT", "")
    # REPLIT_ENVIRONMENT can say "production" inside the editor. Only the
    # documented published-process flag may select the production namespace.
    expected = "production" if os.getenv("REPLIT_DEPLOYMENT") == "1" else "development"
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{2,79}", project) and environment == expected:
        return f"{environment}:{project}"
    return None


class DisabledMemory:
    def __init__(self, status="disabled"):
        self.status = status
        self.project_scope = configured_project_scope()

    def recall(self, question, thread_id):
        return [], self.status

    def remember(self, findings, thread_id):
        return self.status

    def close(self):
        pass


class HostedMem0:
    """SDK 2.2 adapter with an owned, bounded, non-retrying HTTP client."""
    def __init__(self, api_key):
        self.api_key = api_key
        self._client = None
        self._http = None

    def _sdk(self):
        if self._client is None:
            import httpx
            from mem0 import MemoryClient
            transport = httpx.Client(
                timeout=httpx.Timeout(3.0), transport=httpx.HTTPTransport(retries=0),
            )
            try:
                self._client = MemoryClient(api_key=self.api_key, client=transport)
            except Exception:
                transport.close()
                raise
            self._http = transport
        return self._client

    def ready(self):
        self._sdk()

    def search(self, question, filters):
        return self._sdk().search(
            question, filters=filters, top_k=MAX_RESULTS,
            threshold=MIN_SCORE, show_expired=False,
        )

    def add(self, record):
        return self._sdk().add(
            messages=[{"role": "user", "content": record["summary"]}],
            user_id=record["owner_scope"], app_id=record["project_id"],
            metadata=record, infer=False,
        )

    def close(self):
        if self._http is not None:
            self._http.close()


class SemanticMemory:
    def __init__(self, project: str, environment: str, provider, ledger):
        self.project = project
        self.environment = environment
        self.provider = provider
        self.ledger = ledger
        self._ready = False
        self.project_scope = f"{environment}:{project}"
        self.last_recall_diagnostics = {}

    def _owner(self, thread_id):
        if not valid_conversation_key(thread_id):
            raise ValueError("A private conversation capability is required.")
        return hashlib.sha256(
            f"{self.environment}\0{self.project}\0{thread_id}".encode()
        ).hexdigest()

    def _ensure_ready(self):
        if not self._ready:
            self.ledger.ready()
            self.provider.ready()
            self._ready = True

    def recall(self, question: str, thread_id: str) -> tuple[list[dict], str]:
        # Counts and fixed rejection labels only; never retain questions, scope
        # capabilities, provider bodies, or previous-request diagnostics.
        diagnostic = {"result_count": 0, "accepted": 0, "restored_provenance": 0, "rejections": {}}
        self.last_recall_diagnostics = diagnostic

        def reject(reason):
            reasons = diagnostic["rejections"]
            reasons[reason] = reasons.get(reason, 0) + 1

        try:
            owner = self._owner(thread_id)
            self._ensure_ready()
            filters = {"AND": [
                {"user_id": owner},
                {"metadata": {"project_id": self.project}},
                {"metadata": {"owner_scope": owner}},
                {"metadata": {"environment": self.environment}},
            ]}
            response = self.provider.search(question[:2000], filters)
            if not isinstance(response, dict) or not isinstance(response.get("results"), list):
                reject("unexpected_response_schema")
                raise ValueError("Unexpected search response")
            diagnostic["result_count"] = len(response["results"])
            matches, seen = [], set()
            for row in response["results"][:20]:
                if not isinstance(row, dict) or not isinstance(row.get("metadata"), dict):
                    reject("invalid_metadata")
                    continue
                record = dict(row["metadata"])
                try:
                    score = float(row.get("score", 0))
                except (ValueError, TypeError):
                    reject("invalid_score")
                    continue
                if not math.isfinite(score) or not 0 <= score <= 1:
                    reject("invalid_score")
                    continue
                if score < MIN_SCORE:
                    reject("low_score")
                    continue
                if (
                    record.get("project_id") != self.project
                    or record.get("owner_scope") != owner
                    or record.get("environment") != self.environment
                    or row.get("user_id") != owner
                    or row.get("app_id") not in (None, self.project)
                ):
                    reject("scope_mismatch")
                    continue
                if record.get("kind") not in KINDS:
                    reject("invalid_kind")
                    continue
                identity = record.get("finding_id", "")
                if (
                    not isinstance(identity, str) or not re.fullmatch(r"[a-f0-9]{64}", identity)
                ):
                    reject("invalid_identity")
                    continue
                if identity in seen:
                    reject("duplicate")
                    continue
                expiry_values = [record.get("expires_at")]
                # Hosted get-all was observed changing structured metadata types.
                # Never guess how strings/lists encode ticket IDs or evidence.
                # Recover the exact submitted payload through a scoped read.
                if not isinstance(record.get("source_ticket_ids"), list) or not isinstance(record.get("evidence"), dict):
                    restored = self.ledger.get_finding(identity, self.project, owner, self.environment)
                    if not isinstance(restored, dict) or any(
                        restored.get(key) != value for key, value in {
                            "finding_id": identity, "project_id": self.project,
                            "owner_scope": owner, "environment": self.environment,
                        }.items()
                    ):
                        reject("unrecoverable_provenance")
                        continue
                    if row.get("memory") != restored.get("summary") or record.get("summary") != restored.get("summary"):
                        reject("content_mismatch")
                        continue
                    # Bind canonical source data to its original deterministic ID.
                    identity_fields = {key: restored.get(key) for key in (
                        "kind", "summary", "source_ticket_ids", "sprint_name", "evidence",
                        "project_id", "owner_scope", "environment",
                    )}
                    if hashlib.sha256(canonical(identity_fields).encode()).hexdigest() != identity:
                        reject("fingerprint_mismatch")
                        continue
                    if record.get("kind") != restored.get("kind"):
                        reject("invalid_kind")
                        continue
                    record = dict(restored)
                    # Neither provider nor ledger can extend the other's expiry.
                    expiry_values.append(record.get("expires_at"))
                    diagnostic["restored_provenance"] += 1
                ids = record.get("source_ticket_ids")
                if (
                    not isinstance(ids, list) or not ids
                    or not all(isinstance(i, str) and re.fullmatch(r"[A-Z][A-Z0-9_]*-\d+", i) for i in ids)
                    or not isinstance(record.get("evidence"), dict)
                    or not isinstance(record.get("summary"), str)
                    or len(canonical(record)) > 12000
                ):
                    reject("invalid_provenance")
                    continue
                try:
                    observed = datetime.fromisoformat(record["observed_at"])
                    recorded = datetime.fromisoformat(record["recorded_at"])
                    expirations = [datetime.fromisoformat(value) for value in expiry_values if value]
                except (KeyError, TypeError, ValueError):
                    reject("invalid_timestamp")
                    continue
                if observed.tzinfo is None or recorded.tzinfo is None:
                    reject("invalid_timestamp")
                    continue
                if any(expires.tzinfo is None or expires <= datetime.now(timezone.utc) for expires in expirations):
                    reject("expired")
                    continue
                seen.add(identity)
                matches.append({
                    **record, "historical": True, "current_status_authority": False,
                })
                if len(matches) == MAX_RESULTS:
                    break
            diagnostic["accepted"] = len(matches)
            return matches, "ok"
        except Exception:
            # Never log provider exceptions: they can contain keys or user content.
            LOGGER.warning("semantic_memory_unavailable stage=search")
            diagnostic["unavailable"] = True
            return [], "unavailable"

    def remember(self, findings: list[Finding], thread_id: str) -> str:
        try:
            owner = self._owner(thread_id)
            self._ensure_ready()
            # Queue every sourced finding durably before dispatching a bounded
            # number. Later turns drain remaining queued entries for this owner.
            self.ledger.enqueue([
                finding.envelope(self.project, owner, self.environment) for finding in findings
            ])
            writes = 0
            for _ in range(MAX_WRITES):
                record = self.ledger.claim(self.project, owner, self.environment)
                if record is None:
                    break
                try:
                    result = self.provider.add(record)
                    event_id = ingestion_acknowledgment(result, record)
                    self.ledger.finish(record["finding_id"], "pending", event_id)
                except Exception:
                    # A timeout might mean the remote write succeeded. Never retry it
                    # blindly, including when finish() itself failed.
                    self.ledger.finish(record["finding_id"], "unknown")
                    raise
                writes += 1
            return "pending" if writes else "unchanged"
        except Exception:
            LOGGER.warning("semantic_memory_unavailable stage=write")
            return "unavailable"

    def close(self):
        self.provider.close()


def configured_semantic_memory():
    if os.getenv("MEM0_ENABLED", "").lower() != "true":
        return DisabledMemory()
    project = os.getenv("MEM0_PROJECT_ID", "")
    environment = os.getenv("MEM0_ENVIRONMENT", "")
    key = os.getenv("MEM0_API_KEY", "")
    dsn = os.getenv("MEM0_LEDGER_DATABASE_URL") or os.getenv("DATABASE_URL", "")
    # These are fail-closed preconditions, not automatic backend provisioning.
    if (
        configured_project_scope() is None
        or not key or not dsn or os.getenv("MEM0_TELEMETRY", "").lower() != "false"
    ):
        LOGGER.warning("semantic_memory_unavailable stage=configuration")
        return DisabledMemory("unavailable")
    from agents.semantic_ledger import PostgresLedger
    return SemanticMemory(project, environment, HostedMem0(key), PostgresLedger(dsn))


def historical_semantic_excerpt(records: list[dict[str, Any]]) -> str:
    if not records:
        return ""
    return (
        "\n\n### Relevant semantic memories (historical, not current)\n"
        + json.dumps(records, ensure_ascii=False)
    )
