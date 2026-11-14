"""Durable duplicate guard, independent of the LangGraph checkpoint database."""
from __future__ import annotations

import json


class PostgresLedger:
    def __init__(self, dsn: str):
        self.dsn = dsn

    def _connection(self):
        import psycopg
        return psycopg.connect(
            self.dsn, connect_timeout=2,
            options="-c statement_timeout=1500 -c lock_timeout=1000",
        )

    def ready(self):
        # Never create/migrate production tables at startup.
        with self._connection() as connection:
            connection.execute("SELECT 1 FROM public.sprintpulse_memory_ingestion LIMIT 0")

    def enqueue(self, records: list[dict]):
        with self._connection() as connection:
            for record in records:
                connection.execute(
                    """INSERT INTO public.sprintpulse_memory_ingestion
                       (finding_id, project_id, owner_scope, environment, payload, status)
                       VALUES (%s, %s, %s, %s, %s::jsonb, 'queued')
                       ON CONFLICT (finding_id) DO NOTHING""",
                    (record["finding_id"], record["project_id"], record["owner_scope"],
                     record["environment"], json.dumps(record)),
                )

    def claim(self, project: str, owner: str, environment: str) -> dict | None:
        with self._connection() as connection:
            row = connection.execute(
                """WITH candidate AS (
                     SELECT finding_id FROM public.sprintpulse_memory_ingestion
                     WHERE project_id=%s AND owner_scope=%s AND environment=%s
                       AND status='queued'
                     ORDER BY created_at, finding_id
                     FOR UPDATE SKIP LOCKED LIMIT 1
                   )
                   UPDATE public.sprintpulse_memory_ingestion AS item
                   SET status='reserved', updated_at=NOW()
                   FROM candidate WHERE item.finding_id=candidate.finding_id
                   RETURNING item.payload""",
                (project, owner, environment),
            ).fetchone()
            return row[0] if row else None

    def finish(self, finding_id: str, status: str, event_id: str | None = None):
        if status not in {"pending", "unknown"} or (status == "unknown" and event_id is not None):
            raise ValueError("Invalid ingestion finalization")
        with self._connection() as connection:
            updated = connection.execute(
                """UPDATE public.sprintpulse_memory_ingestion
                   SET status=%s, event_id=%s, updated_at=NOW()
                   WHERE finding_id=%s AND status='reserved'""",
                (status, event_id, finding_id),
            )
            if updated.rowcount != 1:
                # A lost commit acknowledgment must not overwrite a committed
                # pending row with unknown (or erase its event ID).
                raise ValueError("Ingestion claim was not reserved")

    def get_finding(self, finding_id: str, project: str, owner: str, environment: str) -> dict | None:
        """Read canonical provenance only for this exact dispatched finding.

        This never requeues work or claims the provider still stores the record.
        The caller must first possess a matching remote search result.
        """
        with self._connection() as connection:
            row = connection.execute(
                """SELECT payload FROM public.sprintpulse_memory_ingestion
                   WHERE finding_id=%s AND project_id=%s AND owner_scope=%s
                     AND environment=%s AND status IN ('reserved', 'pending', 'unknown')""",
                (finding_id, project, owner, environment),
            ).fetchone()
            return row[0] if row else None
