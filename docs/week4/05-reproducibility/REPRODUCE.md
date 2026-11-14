# Reproducibility without new inference

## Verify this export (offline; does not execute the app)

From the extracted packet root:

    sha256sum -c SHA256SUMS
    sha256sum -c evaluation/golden/v1.sha256
    sha256sum -c evaluation/holdout/v1.sha256

Inspect four-page PDF, original `records.jsonl`, `reviewed-records.jsonl`,
metadata/source manifests and the unchanged rubric. Every copied file's original
workspace path/hash is in MANIFEST.json. Absolute/relative source references in
original records are historical; use the manifest to locate packaged copies.
Original source manifests intentionally also name files excluded for privacy.
They are provenance lists, not declarations that excluded databases are shipped.

## Independently reproduce sample agreement (stdlib only)

This reads the completed CSV and preserved predictions; no model is called:

    python - <<'PY'
    import csv,json
    from pathlib import Path
    p=Path('03-author-review')
    rows=list(csv.DictReader((p/'completed-review.csv').open(encoding='utf-8-sig',newline='')))
    predictions={r['judgment_id']:r for r in json.loads((p/'automation/automated-predictions.json').read_text())}
    assert len(rows)==len({r['judgment_id'] for r in rows})==15
    assert all(r['independence_attestation']=='Author review — not independent third-party review' for r in rows)
    assert all(r['reviewer_notes'].strip() and r['reviewer_decision']=='1' for r in rows)
    assert all(predictions[r['judgment_id']]['predicted']=='PASS' for r in rows)
    print('Author PASS 15/15; agreement 15/15; not independent review')
    PY

## Future agent/evaluator replay — NOT executed for this packet

Use an isolated development workspace, never production, with no credentials
available, tracing/hosted memory disabled and network blocked by the existing
offline workers. Dependency installation can require downloads; it is not needed
to inspect this packet or verify sample agreement. Exact pinned dependencies are
in environment/pyproject.toml and uv.lock. `uv sync --frozen` prepares the Python
environment; do not substitute package versions.

Baseline, initial-improved and final source-only versions are under
source-versions/. They came from existing saved version archives. Their original
graph/LLM/tool files and synthetic CSVs are unchanged; checkpoint and approved
report files were deliberately excluded. The initial improved holdout source
already contains the previously verified unchanged publisher dependency repair.

The exported evaluator implementation is under ../04-methods/evaluation/.
For a future authorized replay, reconstruct a NEW temporary workspace with the
chosen source version and its matching evaluator/dataset (never overwrite an
active workspace), then use the documented CLI --help and archived metadata.
Golden README contains original approval/run/review commands; its initial-status
text is historical. Supply a new run-bound approval file, retain labels and N/A,
use deterministic mode only, isolated temporary SQLite and NEW output folders.
Workers and runners reference original workspace `.local/evaluations/...`
paths; configure their source/run paths in a separate scratch copy or reproduce
the original path layout there using MANIFEST.json. The ZIP is not claimed to
be a turn-key reconstruction of omitted private checkpoint state.

Do not rerun the repaired holdout as “unseen.” The original paired holdout run
has28final+6setup requests. Final remediation has54final+10setup. Counts, routing,
answer outputs, failures and timings are in original records/metadata. Timings
are environment-dependent; no exact latency reproduction guarantee is made.

Regression evidence is the preserved log/XML:252passed,1skipped,27warnings.
This packaging operation did NOT run pytest or any agent evaluation.
The archived source-only versions intentionally omit unrelated/private files;
consult the repository and exact source manifests for full future test setup.
