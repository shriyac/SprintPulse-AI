# Week 4 preparation report

> Historical pre-review snapshot. Superseded by
> [the final frozen v1 validation report](FINAL_VALIDATION-v1.md).
> The draft counts, checksum and test results below describe the earlier
> preparation phase. Frozen v1 now has 40 source-grounded cases, zero PARTIAL
> labels, and a completed 177-pass / 1-skip full test run.

## Scope and status

Evaluation artifacts only; application/Streamlit/production settings unchanged.
Dataset version **1.0.0** is **awaiting review**. The approval example is false.
**Zero golden baseline cases executed; zero live LLM, mem0 or tracing calls.**

## Ground truth verification actually executed

Command:

```bash
uv run --frozen --no-sync python -m evaluation.verify
```

Results:

- 40 cases: **20 happy + 12 edge + 6 known-failure + 2 adversarial**.
- **34 complete source-grounded expectations; 6 PARTIAL** because their proposed
  intended routes need human approval. Their current lexical-route mismatches
  were checked, not assumed.
- **82 exact factual assertions** checked in **38 cases** using actual CSV data
  and deterministic tools. The other two specify controlled failure behavior.
- All **3 CSV snapshots** independently cross-checked with stdlib CSV/date
  arithmetic for counts, completion, points, overdue IDs/durations, recurring
  blockers, maximum durations and completion trends.
- Existing source anchors for request reset, bounded errors, project filtering,
  fresh-data precedence and untrusted-text instructions verified. These are
  source checks, **not executed security/failure tests**.
- CSV hashes pinned in `golden/v1.json`. Dataset SHA-256:
  `6871f17c7d21073b55477066881ea3c512caac8490b79474175b0d8fdf9add39`.

| Snapshot | Tickets | Done | Completion | Points complete/scope | Blocked | Overdue |
|---|---:|---:|---:|---:|---:|---:|
| Sprint 24 | 24 | 10 | 41.7% | 39/83 | 3 | 14 |
| Sprint 25 | 24 | 13 | 54.2% | 49/83 | 3 | 11 |
| Sprint 26 | 24 | 16 | 66.7% | 59/83 | 2 | 8 |

Recurring blockers: SP-118 and SP-122 appear blocked in 3 snapshots; SP-124 in
2. Their maximum observed durations are 37, 32, and 2 days respectively.
SP-124 is **To Do** in Sprint 26; historical recurrence is not current blockage.

## Harness validation

Command actually executed:

```bash
uv run --frozen --no-sync pytest -q tests/test_evaluation_framework.py
```

**19 passed in 4.07 seconds** in the completed infrastructure pass. These cover
source verification, invalid expectations, known routing gaps, N/A/pending
denominators, p95, approval guards, production refusal, callback wiring through
an unrelated tiny graph, nested tool instrumentation, controlled tool failure,
manual scoring, live/fallback separation, redaction and identity-based lookups.
Two non-golden fake-agent invocations also verified temporary-storage isolation,
DisabledMemory injection, the report-save prohibition, copied-input mutation,
and cleanup without running the application graph.

No full existing-suite result is claimed for this phase. No golden SprintPulse
case was executed by these tests; the callback test uses an unrelated tiny graph.

## Deferred until review/approval

- Deterministic full 40-case LangGraph baseline.
- Separately approved live LLM baseline and its token charges.
- Human scoring of final answers/tasks/context and measured p95.
- LangSmith setup/tracing; proposal provided, no service enabled.
- Any application routing/logic change. The six lexical gaps remain unchanged.

All existing production mem0, checkpoints, sample datasets and UI are untouched.
Hosted memory quality, production persistence, UI journeys and report approval/
saving are explicitly outside this framework's measured coverage.
