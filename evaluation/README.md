# SprintPulse AI — Week 4: Evaluate Your Agent

Evaluation-only additions. **v1 dataset review is complete; no baseline has run.**
No UI, application logic, deployment settings, existing checkpoints, or mem0
records are changed by preparing these files.

## Frozen v1 and review record

1. [Golden dataset v1](golden/v1.json): 20 happy, 12 edge, 6 known-failure and
   2 adversarial cases. Each includes prompt, selected sprint, scenario, expected
   route, source references, exact evidence assertions, required answer, and N/A
   declarations. Read [the review index](golden/REVIEW-v1.md).
2. [Rubric and targets](RUBRIC.md).
3. [Final frozen v1 validation report](FINAL_VALIDATION-v1.md), including checksum
   and the complete 177-pass / 1-skip test result.
4. [Optional LangSmith proposal](LANGSMITH_PROPOSAL.md)—not enabled.

**Dataset version:** 1.0.0. Do not confuse `ground_truth_status` with an agent
test result. All 40 golden answers remain unexecuted. K01–K06 now record
`source_verified_user_approved` with the user's expected-behavior refinements;
the other 34 cases are unchanged. The six actual lexical-routing gaps remain.
All 82 original factual assertions are preserved.

The dataset's SHA-256 is recorded in `golden/v1.sha256`. From the root:

```bash
sha256sum -c evaluation/golden/v1.sha256
```

The verifier checks this frozen checksum and the preserved 34-case fingerprint.
Any later v1 edit requires a new reviewed dataset version, not silent replacement.
The final validation report must be delivered before baseline execution.

## Safe validation checks — no baseline execution

From the repository root, using the existing environment:

```bash
uv run --frozen --no-sync python -m evaluation.verify
uv run --frozen --no-sync pytest -q tests/test_evaluation_framework.py
```

These verify data and harness infrastructure. The new tests use pure tools,
fakes, and a tiny unrelated LangGraph to check callback wiring; **they do not
run the SprintPulse golden cases**, call an LLM, or contact mem0. If installing
locally on a fresh machine, first run `uv sync --frozen` to include the existing
development dependency group (pytest). No dependency or lockfile changes are needed.

## Baseline gate — after the final validation report

The user has reviewed the six labels/refinements and requested this freeze.
After the final validation report, when a baseline is instructed:

```bash
mkdir -p .local/evaluations
cp evaluation/approval.example.json .local/evaluations/dataset-approval.json
uv run --frozen --no-sync python -m evaluation.verify
```

Edit **only the local copy**: set `approved` to true, set `dataset_sha256` to
the verifier's exact dataset hash, provide a reviewer alias (not personal
information) and ISO-8601 `reviewed_at`. Keep this approval and all results out
of Git. The shipped example is deliberately unapproved; the runner rejects it.
The runner does not approve its own dataset or bypass the user's review.
The template stays false; dataset approval does not authorize live LLM charges,
remote memories, report saving or publication.

## Baseline commands — provided, NOT executed during preparation

Deterministic graph/fallback baseline (no external LLM or mem0):

```bash
uv run --frozen --no-sync python -m evaluation.runner run \
  --mode deterministic \
  --approval .local/evaluations/dataset-approval.json
```

Separately approved live LLM baseline (uses the application's existing
LangChain client/credentials; provider token charges apply):

```bash
uv run --frozen --no-sync python -m evaluation.runner run \
  --mode live --acknowledge-live-costs \
  --approval .local/evaluations/dataset-approval.json
```

`--case H01 --case E11` selects an explicitly labeled subset for an approved
smoke run. It is not reported as a full 40-case baseline. Both modes always
disable hosted mem0 and LangSmith tracing, reject production execution, use
temporary SQLite, and never save reports. Live mode requires configured LLM
access; it does not silently call an unconfigured fallback a live evaluation.
No new dependencies, secrets or service provisioning are required for offline
preparation/deterministic evaluation.

Outputs: `.local/evaluations/<run-id>/`

| File | Contents |
|---|---|
| `metadata.json` | Dataset hash, application/evaluation source hashes, prompt/report-task versions, Git status, Python/packages, model ID, run mode |
| `records.jsonl` | Case ID/prompt, actual route, final answer/report/errors, real graph-node callback sequence, nested tool calls/outputs/timings, generation evidence/mode, setup-vs-final phase, latency and scores |
| `summary.json` | Eligible/scored/pending/N/A counts, proposed targets, p95, category breakdowns and live-LLM coverage |
| `review.json` | Human scoring template bound to the exact run, dataset and answers |

Tool-output matches are **evidence diagnostics, not an answer-correctness score**.
Qualitative scores remain PENDING until reviewed. Fill the applicable 0/1
entries and reasons in the local `review.json`, then score recorded answers
without rerunning the agent:

```bash
uv run --frozen --no-sync python -m evaluation.runner review \
  --run-dir .local/evaluations/ACTUAL_RUN_ID \
  --reviews .local/evaluations/ACTUAL_RUN_ID/review.json
```

This writes separate `reviewed-records.jsonl` and `reviewed-summary.json`;
original results are preserved.

## Architecture inspected

- `app.py` invokes `agents/graph.py:invoke_sprint_graph`; report tab supplies a
  route override, and the assistant uses ordinary classification.
- `StateGraph`: `START → recall_conversation → route_request →` one of
  `retrieve_sprint_data`, `detect_risk`, `compare_sprint_history`,
  `gather_report_evidence`, `retrieve_question_context` `→ remember_findings →`
  `answer` or `report → END`. Tools/errors do not route to a retry loop.
- `tools/sprint_metrics.py` supplies six deterministic functions. The lexical
  router is conditional, but tool bundles are fixed per node. Risk calculations
  run even before the metrics node trims its output; instrumentation records
  these real calls, including nested `sprint_metrics` calls.
- `agents/memory.py` recalls at most three relevant completed checkpoint turns;
  failed/incomplete turns and wrong namespaces are filtered. The wrapper resets
  request-scoped state while retaining historical checkpoints.
- `agents/semantic_memory.py` / `semantic_ledger.py` implement optional scoped
  hosted mem0 and a PostgreSQL ingestion ledger. They are not exercised live by
  this framework. Source CSV history is re-read, not learned by an LLM.
- Existing regression tests cover request reset/recovery, conversation history,
  memory scope/staleness, provider acknowledgment and ledger behavior. Their
  earlier passes are not substituted for a new evaluation baseline.

### Data limits reviewers should know

There are 24 preserved ticket IDs in each of Sprint 24/25/26. All metrics use
each snapshot's sprint end, not today's date. Recurrence and maximum blocker
duration use **all supplied snapshots**, even when an older sprint is selected.
The loader coerces invalid dates rather than rejecting every malformed date;
this dataset is not an exhaustive CSV-validation/security audit. SP-124's
observed duration remains 2 days because its blocked-since date resets in
Sprint 25; do not invent continuous blockage. The dataset includes this fact
without claiming that historical records are complete real Jira history.

No baseline outcomes, model-quality scores, live p95, actual adversarial
resistance, or production-readiness conclusions have been measured yet.
