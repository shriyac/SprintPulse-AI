# Routing and answer completeness — frozen v1 re-evaluation

## Scope and provenance

Implemented focused deterministic routing and answer-rendering fixes in the
existing SprintPulse AI application. No UI, model/prompt, metric calculation,
tool-output contract, graph topology, state/checkpoint schema, memory ownership,
source CSV, production setting or report-approval control was changed.

The unchanged frozen dataset is `evaluation/golden/v1.json`, version 1.0.0:

`c35be99dbf15d2b9fff4e4aa479c6de5c03ddccfc9fff80a5ab2b38d548cf199`

Reference baseline: `.local/evaluations/20261110T033345Z-e8181434/`.
New execution: `.local/evaluations/20261110T035032Z-765dcbc8/`.
Both execute the real LangGraph wrapper with temporary SQLite, synthetic data,
generation forced through deterministic fallback, hosted mem0 disabled, and
tracing disabled. Original baseline records and judgments are preserved.

The later pre-fix run `20261110T034016Z-1d9ab6bc` also remains intact; it is
not substituted for the original reference in the comparisons below.

## Changes and root causes

- `agents/graph.py`: expand narrow intent recognition for weekly summaries,
  impediments, delivery percentages, finished work, side-by-side sprint views,
  and risks compared with a prior sprint. Preserve report > comparison > risk >
  metrics precedence, existing overrides, latest-request initialization and edges.
- `agents/answer_rendering.py`: new internal renderer uses only existing tool
  evidence. It supplies requested remaining points, overdue IDs/dates, durations,
  recurrence, ticket-specific status, count changes, scope and reference dates.
  It distinguishes historical observations from current selected-snapshot status
  and confirmed resolution. No additional tool calls or retrieval are introduced.
- Delivery percentages explicitly label tickets and story points. The latter is
  arithmetic on tool-provided completed points/scope, unavailable for zero or
  missing scope. Derived blocked-since dates are labeled and use the observation's
  matching selected sprint end, not today's date.
- Blocked IDs are identified only where current ticket evidence supports them;
  if the aggregate blocked count exceeds the identified rows, the response
  explicitly says evidence is incomplete rather than inventing missing IDs.
- `evaluation/verify.py`: the old pre-flight guard required the original
  routing defects to remain. It now reports current source-route differences
  without preventing their measurement. Historical `observed_source_route`
  fields remain frozen. Actual route/node/tool/evidence-key grading, rubric,
  thresholds, applicability, assertions and denominators are unchanged.
- `tests/test_answer_completeness.py` and `tests/test_evaluation_framework.py`:
  focused rendering/routing/failure and honest pre-flight regression coverage.

The old fallback formatted answers by route alone; it could retrieve a correct
duration or ticket list but still output only generic risk flags. Comparison
responses similarly omitted ticket-specific findings, scope and counts. These
were presentation omissions, separately from the six lexical-routing defects.

## Measured results

Qualitative judgments are **provisional agent-assisted direct reviews** of saved
answers against the same frozen rubric, not independent human certification.
All 40 answers were inspected; every applicable judgment has a case-specific
reason. The blank independent-review template remains available. Tool-output
matches were not used to automatically award answer correctness.

| Metric | Original reference | New execution | Frozen target |
| --- | --- | --- | --- |
| Task completion, assisted | 24/40 (60%) | 40/40 (100%); 0 N/A | >=95% |
| Answer correctness, assisted | 20/38 (52.6%) | 38/38 (100%); 2 N/A | >=95% |
| Actual routing contract | 34/40 (85%) | 40/40 (100%); 0 N/A | >=95% |
| Local memory/context, assisted | 7/7 (100%) | 7/7 (100%); 33 N/A | 100% |
| p95 final-request latency | 102.315 ms | 102.532 ms; 40 requests, 0 N/A | <=2,000 ms |

New p50: 94.059 ms. Single-sample-per-case latency is exploratory; the 0.217 ms
p95 difference is not evidence of a meaningful performance change.

All frozen targets are met for this deterministic suite under the disclosed
assisted review. E06/E07 correctness remains N/A, because the intended outcome is
graceful failure, not a factual answer. Qualitative human acceptance is pending,
not silently reclassified as N/A. The unreviewed summary preserves that distinction.

### All four categories

| Category | Task before -> after | Correctness before -> after | Routing before -> after | Memory before -> after |
| --- | --- | --- | --- | --- |
| Happy | 11/20 -> 20/20 | 9/20 -> 20/20 | 20/20 -> 20/20 | 3/3 -> 3/3 |
| Edge | 10/12 -> 12/12 | 8/10 -> 10/10; 2 N/A | 12/12 -> 12/12 | 4/4 -> 4/4 |
| Known failure | 1/6 -> 6/6 | 1/6 -> 6/6 | 0/6 -> 6/6 | N/A both |
| Adversarial | 2/2 -> 2/2 | 2/2 -> 2/2 | 2/2 -> 2/2 | N/A both |

| Category | Original p95 ms | New p95 ms |
| --- | ---: | ---: |
| Happy | 106.989 | 101.173 |
| Edge | 98.096 | 102.532 |
| Known failure | 101.826 | 116.450 |
| Adversarial | 92.784 | 93.297 |

New tool-output assertions: **82/82** (original 80/82). No uncaught exceptions.
All final requests, including expected failures/outages, are included in latency.

### Representative actual evidence

- H05: now states “59 of 83 story points completed; 24 remaining.”
- H07/E04: actual `detect_risk` evidence is rendered as SP-117 through SP-124,
  including overdue days and selected-sprint date 2026-07-10.
- H08/H15: durations 37/32/2 days are explicitly observations; SP-122's
  blocked-since 2026-06-08 is transparently derived from the tool date/duration.
- H20: `compare_sprint_history` now presents SP-124's Blocked history in
  Sprints 24/25, selected Sprint 26 status To Do, and no unsupported fix claim.
- K01: actual compare branch states Sprint 25 blocked count 3 -> Sprint 26 2
  and explicitly distinguishes observations from confirmed fixes.
- K02: actual risk branch states the narrow impediment definition and lists
  SP-118/SP-122, not historical SP-124 as currently blocked.
- K03: actual report branch emits a draft requiring human approval.
- K04: actual metrics branch labels tickets 66.7% (16/24) and points 71.1%
  (59/83), derived from tool counts.
- K05/K06: actual compare/metrics branches now match the intended labels.

The actual callback path is `recall_conversation -> route_request -> evidence
node -> remember_findings -> answer/report`. Six K branches are now, respectively:
`compare_sprint_history`, `detect_risk`, `gather_report_evidence`,
`retrieve_sprint_data`, `compare_sprint_history`, `retrieve_sprint_data`.
Exact nested tool calls, outputs, errors and timings are preserved per case.

E09/E10 both record request_reset=true; failed setup is excluded from recovery
recall. H19 records restore_matches=true. Project/thread isolation remains
intact in applicable cases; no persistent history was cleared.

## Tests and development smoke check

Executed:

```bash
SPRINTPULSE_RUN_MEM0_LIVE_TESTS=false \
LANGSMITH_TRACING=false LANGCHAIN_TRACING_V2=false \
LANGCHAIN_TRACING=false LANGSMITH_OTEL_ENABLED=false \
uv run --frozen --no-sync pytest -q tests \
  --junitxml=.local/evaluations/improvement-regressions.xml
```

**219 passed, 1 skipped, 27 warnings in 51.59 seconds.** The opt-in live mem0
test was intentionally skipped. Warnings are existing Streamlit/Pandas
deprecations. Tests include aliases/paraphrases and precedence, requested
details, missing/zero scope, incomplete blocker evidence, selected-sprint
comparisons, no inferred resolution, drafts, shared-thread outage recovery,
unchanged model-result handling and the existing memory/approval regressions.

The managed development Streamlit workflow was restarted once after changes.
Logs show it serving cleanly. A real browser screenshot showed the existing
Dashboard, AI Assistant and Weekly Reports tabs unchanged, with 66.7%, 16/24,
2 blockers and 8 overdue. `/_stcore/health` returned HTTP 200 and `ok`.
This was a smoke check, not interactive end-to-end browser testing.

## Evidence and remaining limitations

New raw records SHA-256:
`771db68ed1e52bb09f61b12b9e9fa21059ca9308843d9dc64e99cf39d17fec67`.
The run manifest includes the dirty working-tree flag plus exact per-file
hashes, including the new renderer. A Git commit alone is not claimed as the
complete tested version. Old records and frozen dataset/rubric hashes remain intact.

Outputs include raw `records.jsonl`, `metadata.json`, unreviewed `summary.json`,
`agent-assisted-review.json`, `review-findings.json`, `reviewed-records.jsonl`,
`reviewed-summary.json`, case-level CSV, source snapshot and integrity manifest.

No live LLM calls, mem0 writes/reads, tracing or production validation occurred.
The live generation path still returns the existing model response unchanged;
improved deterministic scores do not establish improved live-model quality.
Routing remains lexical and can miss unfamiliar wording. The renderer cannot
identify current statuses absent from the existing evidence and says so.
Checkpoint durability, authentication, production storage and broader adversarial
resilience are not certified by this work. Independent human review and a
separately budget-approved live/holdout evaluation remain appropriate next steps.
