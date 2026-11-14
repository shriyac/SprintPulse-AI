# SprintPulse AI — Week 4 unseen-question holdout

## Generalization assessment: PARTIAL

The focused improvements transfer to several new phrasings and fixtures, but
do not meet the 95% answer-completeness/correctness targets on this holdout.
Routing meets its target. Three previously unmeasured answer gaps remain:
explicit unfinished-ticket totals, missing-predecessor handling, and selection
of a non-SP ticket ID. No application fix was made during this evaluation.

**Qualitative scores below are provisional agent-assisted judgments. Independent
human acceptance is PENDING.** All 28 saved answers were reviewed against the
approved requirements, not graded merely from matching tool JSON. Separate
unreviewed summaries preserve pending qualitative status; no pending case was
reclassified as N/A. This is a developer-authored, user-approved holdout, not an
external blind benchmark or a live-model evaluation.

## Frozen dataset and preservation

- Separate dataset: `evaluation/holdout/v1.json`, **holdout-v1.0.0**.
- SHA-256: `1965d096ebcf40d9c41a95ea519ec6f231456100a5b72f972149c92e3395ceee`.
- Checksum file: `evaluation/holdout/v1.sha256`.
- Provenance binds the reviewed proposal, independently verified CSV/tool
  evidence, exact fixture recipes, golden v1, rubric and both source archives.
- Prompts, intended routes, expected behaviors, fixtures and scenarios match the
  approved proposal. Additional scoring checks/applicability were frozen before
  any holdout graph execution; no label was changed after seeing results.
- Original golden v1, scoring/rubric, all original runs, application/UI, CSVs,
  checkpoint storage and deployment configuration remain unchanged. Before/after
  fingerprints verify preservation; no deployment or workflow was started.
- Freeze is version/checksum plus local read-only files, not a claim of WORM storage.

## Exact versions and execution

Run folder: `.local/evaluations/holdout-v1-20261110T045936Z/`.

| Version | Archived snapshot | Graph SHA-256 |
| --- | --- | --- |
| Baseline | `20261110T034016Z-1d9ab6bc` | `9f0a86f86ef4c1414a597e5f7ad76ca9d557fc7ceac8b1a8f0f872a41905248c` |
| Improved | `20261110T035032Z-765dcbc8` | `6562e46275888edb2c6d8780d88ff16a2a0b40cef5e1eb6020ea1e975df1d502` |

Both versions were restored into independent source directories, verified by
archival manifests, and executed in separate subprocesses. The improved archive
omitted the unchanged report-publishing dependency. Initial preflight stopped
before any graph execution; exact baseline-archived publisher/init bytes were
then supplied to the improved copy only after matching their pre-change
fingerprints and unchanged current files. This supplement is explicitly recorded
in run metadata; no approximate implementation or original-archive edit was used.

The shared tools, instrumentation, scoring, memory, LLM module and lockfile
hashes match across versions. Actual imported graph/module paths were checked.
Cases were shuffled with a recorded seed and version order counterbalanced.
Paired fixtures have identical serialized hashes. The current deployment was
not checked out, restarted, reconfigured or used for any test.

**Actual execution: 28 scored final requests + all 6 setup requests = 34 graph
requests.** Every case/version used an isolated temporary SQLite environment.
G12 shares its private key only within its scenario; G13 switches keys.
All temporary checkpoint directories were removed afterward.

- 32 local generation-wrapper calls were stubbed to deterministic fallback.
- **0 live LLM calls, 0 hosted mem0 calls, 0 production database calls, 0 paid
  service calls, 0 outbound networking attempts.**
- Child environments did not inherit credentials; socket networking was denied,
  hosted memory was DisabledMemory, tracing was disabled and report saving blocked.
- 0 final graph exceptions/errors. Two intentional setup tool failures occurred,
  one per version; each produced one bounded error and successful subsequent recovery.
- Tool evidence checks: baseline **29/31**, improved **31/31**. Both failed baseline
  checks belong to G04, whose wrong route omitted historical comparison evidence.

## Five-metric comparison

| Metric | Baseline | Improved | Change | Target / improved outcome |
| --- | --- | --- | --- | --- |
| Task completion, assisted | 1/14 (7.14%) | 11/14 (78.57%) | +71.43 pp | >=95%: FAIL, provisional |
| Answer correctness, assisted | 1/14 (7.14%) | 11/14 (78.57%) | +71.43 pp | >=95%: FAIL, provisional |
| Actual routing contract | 10/14 (71.43%) | 14/14 (100%) | +28.57 pp | >=95%: PASS |
| Memory/context, assisted plus runtime gates | 2/2 (100%) | 2/2 (100%) | 0 pp | 100%: PASS, provisional |
| Final-request nearest-rank p95 | 233.174 ms | 228.572 ms | -4.602 ms | <=2,000 ms: PASS |

All 14 cases are applicable to task/correctness/routing/latency for each version.
Only G12/G13 are applicable to memory: 12 N/A per version, with explicit reasons.
No failed or slow final request was excluded. Setup timings are recorded
separately, not included as extra scored cases.

At n=14, nearest-rank p95 is the maximum observed sample; these single-pass
figures do not establish statistically reliable performance improvement.
Do not compare their latency directly with the different 40-case workload.

### Holdout group breakdown

| Group | Cases | Task/correctness baseline -> improved | Routing baseline -> improved |
| --- | ---: | --- | --- |
| Happy | 6 | 0/6 -> 5/6 | 3/6 -> 6/6 |
| Edge/fixture | 5 | 0/5 -> 3/5 | 4/5 -> 5/5 |
| Memory/recovery | 2 | 1/2 -> 2/2 | 2/2 -> 2/2 |
| Adversarial | 1 | 0/1 -> 1/1 | 1/1 -> 1/1 |

These are the separately frozen holdout groups, not altered categories in
golden v1. Detailed category summaries include all five metrics and N/A counts.

## Complete per-case comparison

PASS below requires all applicable quality/routing scores to pass; qualitative
components are still provisional. Correct route alone is not overall success.

| Case | Actual route baseline -> improved | Baseline | Improved | Difference / remaining failure |
| --- | --- | --- | --- | --- |
| G01 | metrics -> metrics | FAIL | FAIL | Both give 16/24 and 8 overdue, not an explicit total of 8 not done. |
| G02 | question -> metrics | FAIL | PASS | Both requested ratios and denominators now explicit. |
| G03 | risk -> report | FAIL | PASS | Weekly draft replaces risk-only answer; approval notice present. |
| G04 | risk -> compare | FAIL | PASS | Previous count 3 -> current 2 and no-confirmed-fix caveat now supplied. |
| G05 | risk -> risk | FAIL | PASS | SP-123 To Do, 1 day overdue at selected Sprint 25 end now explicit. |
| G06 | compare -> compare | FAIL | FAIL | Improved gives correct 10/24 but still omits “previous snapshot unavailable”. |
| G07 | risk -> risk | FAIL | PASS | SP-121 To Do, due July 7, 3 days overdue now explicit. |
| G08 | metrics -> metrics | FAIL | PASS | Zero-point percentage explicitly unavailable instead of omitted. |
| G09 | question -> risk | FAIL | PASS | Renamed TEST-118/TEST-122 listed under explicit current-Blocked definition. |
| G10 | risk -> risk | FAIL | FAIL | Improved includes correct TEST-122 32 days, but also TEST-118/124 despite “only”. |
| G11 | risk -> risk | FAIL | PASS | Correct 2/7 totals, SP-118 and incomplete-ID evidence now explicit. |
| G12 | metrics -> metrics | FAIL | PASS | Current 24 remaining now explicit; recovery/preservation pass in both. |
| G13 | question -> question | PASS | PASS | Both recall zero other-key turns and return permitted fresh facts. |
| G14 | report -> report | FAIL | PASS | Both resist fake 100%/publication; improved adds required draft/approval notice. |

**Paired outcome: 10 wins, 0 regressions, 1 pass in both, 3 failures in both.**
Routing gains occur on G02/G03/G04/G09; ticket detail, date, zero-scope and
partial-evidence behavior transfer to new phrasings/fixtures.

### Actual trace interpretation

All final requests follow actual callback events:
`recall_conversation -> route_request -> evidence node -> remember_findings ->
answer/report`. Evidence nodes vary by measured route:

| Route | Actual evidence node |
| --- | --- |
| metrics | retrieve_sprint_data |
| risk | detect_risk |
| compare | compare_sprint_history |
| report | gather_report_evidence |
| question | retrieve_question_context |

Top-level deterministic calls include sprint_metrics, overdue_tasks, risk_flags,
blocker_durations and recurring_blockers; compare/report/question also call
historical_comparison. Nested sprint_metrics calls are captured separately with
parent IDs. These are the existing route-specific bundles, not a claim of
new dynamic tool planning. Exact order, outputs, errors and timing are in every
raw per-case record and the report details, including setup phases.

### Newly exposed limitations and grading cautions

- **G01:** no explicit unfinished total. “8 overdue” is a subset count, not in
  general an answer to “how many not done”, even when the fixture makes both 8.
  This strict completeness judgment needs human confirmation; it is not a false
  numerical statement. If a reviewer accepts deriving 24-16, improved quality
  rises to 12/14 (85.71%), still below 95%.
- **G06:** comparison does not explicitly handle the absence of a predecessor;
  listing later history is not the requested previous-sprint comparison.
- **G10:** renderer ticket extraction recognizes `SP-` IDs only; renamed
  `TEST-122` is not used to filter evidence. It retrieves correct facts but
  violates the explicit ticket-only constraint.
- **Baseline G12:** 24 appears in historical JSON, not as a current requested
  remaining-points answer. Memory preservation is separately scored PASS.
- **Baseline G14:** no fake completion, approval or publication occurred.
  Overall failure concerns the missing required notice, not an observed
  injection/security breach. Independent review must confirm that distinction.

Do not change labels or weaken expected behavior to turn these into passes.
All failure answers and provisional reasons are retained.

## Independent human-review preparation

The run includes:

- `human-review-template.json`: original version-labeled blank review.
- `blind-human-review-template.json`: 60 empty qualitative judgments, bound to
  dataset and raw-record hashes; null remains PENDING.
- `BLIND_REVIEW.html`: all 28 answers in shuffled per-case A/B order, with
  approved expected behavior and source/runtime evidence, but no version labels
  or agent-assisted grades.
- `human-review-key.json`: separate unblinding key; not in the blind-review packet.
- An unchanged rubric copy. A reviewer should submit reasoned judgments before
  seeing the key or assisted scores; disagreements remain explicit.

This prepares review; it does not claim that a human has reviewed the outputs.
Longer answers may suggest their source, so version-label removal is not perfect
blinding. The actual raw and assisted files remain separate.

## Reproduction and deliverables

Added evaluation-only files: `evaluation/holdout.py`,
`evaluation/holdout_worker.py`, separate frozen holdout/checksum, and this report.
No application or existing test/scoring/label file was modified.

```bash
# Verify the separate frozen dataset; do not freeze it again.
sha256sum -c evaluation/holdout/v1.sha256

# A future independently authorized repeat creates a fresh run directory.
uv run --frozen --no-sync python evaluation/holdout.py run
```

The actual execution used the second command once after successful preflight.
Full app pytest was not rerun: application code was unchanged. The new workers
compiled and all 34 graph requests executed. Exact source copies, runner/worker,
dependency versions, observations, raw/scored records, CSV, human review packet
and integrity manifest are saved with the run.

**Conclusion:** Routing generalizes on all 14 approved intents, memory boundaries
and recovery remain intact, and answer completeness improves materially. Full
answer generalization remains **PARTIAL**, not certification of live LLM quality,
production persistence, account authentication or broad adversarial resilience.
