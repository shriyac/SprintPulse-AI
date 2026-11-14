# SprintPulse AI Week 4 — chronological evidence comparison

Prepared from saved records only. No evaluation was rerun for this packet.
All task/correctness/context judgments are provisional agent-assisted reviews,
not independent human approval. Routing and timing come from executed traces.

## Chronology (UTC)

1. **2026-11-10 03:33:45 — original golden baseline:** 40 frozen cases;
   task 24/40, correctness 20/38, routing 34/40. This is the original reference,
   not the later pre-fix rerun.
2. **2026-11-10 03:50:32 — initial improved golden run:** 40/40 task and route,
   38/38 correctness. Intent recognition and evidence rendering improved.
3. **2026-11-10 04:59:36 — original untouched holdout:** 14 newly frozen cases
   run against both archived versions. Improved version passed **11/14**, not
   14/14. Baseline passed 1/14. This is the generalization evidence before
   holdout-directed repair; the holdout was developer-authored/user-approved,
   not an externally administered blind benchmark.
4. **2026-11-11 01:16:44 — post-holdout remediation:** targeted G01/G06/G10
   fixes, then 40 golden and 14 known holdout cases replayed. **14/14 is
   remediation/regression evidence, not a new unseen result.**

## All five metrics

| Stage | Task | Correctness | Routing | Memory/context | p95 |
|---|---:|---:|---:|---:|---:|
| Golden original baseline | 24/40 (60.00%) | 20/38 (52.63%) | 34/40 (85.00%) | 7/7 (100.00%) | 102.315 ms |
| Golden initial improved | 40/40 (100.00%) | 38/38 (100.00%) | 40/40 (100.00%) | 7/7 (100.00%) | 102.532 ms |
| Original holdout baseline | 1/14 (7.14%) | 1/14 (7.14%) | 10/14 (71.43%) | 2/2 (100.00%) | 233.174 ms |
| Original holdout improved | 11/14 (78.57%) | 11/14 (78.57%) | 14/14 (100.00%) | 2/2 (100.00%) | 228.572 ms |
| Remediation golden replay | 40/40 (100.00%) | 38/38 (100.00%) | 40/40 (100.00%) | 7/7 (100.00%) | 93.482 ms |
| Remediation holdout replay | 14/14 (100.00%) | 14/14 (100.00%) | 14/14 (100.00%) | 2/2 (100.00%) | 401.262 ms |


### Measured deltas — percentage points, not relative percentages

- Golden baseline -> initial improved: task **+40.00 pp**, correctness
  **+47.37 pp**, routing **+15.00 pp**, memory **0 pp**, p95 **+0.217 ms**.
- Original holdout baseline -> original improved: task/correctness
  **+71.43 pp**, routing **+28.57 pp**, memory **0 pp**, p95 **-4.602 ms**.
  Ten wins, zero regressions, one shared pass and three shared failures.
- Initial improved -> remediation golden: quality/routing/memory **0 pp**;
  p95 **-9.050 ms**, no scored regressions.
- Original improved holdout -> remediation: task/correctness **+21.43 pp**,
  routing/memory **0 pp**; p95 **+172.690 ms**. All G01-G14 pass provisionally.

Do not compare different datasets' p95 as like-for-like performance. One
sample per case is exploratory; at n=14 nearest-rank p95 is the maximum.
The higher remediation holdout p95 is retained, not dropped. It remains below
the 2,000 ms offline target but is not a statistically confirmed latency trend.

## Metrics, denominators and provenance

Targets: task/correctness/routing >=95%; memory 100%; offline p95 <=2,000 ms;
proposed live p95 <=35,000 ms. Task/correctness require sufficient grounded
answers plus runtime gates. Routing requires actual route, ordered callback
nodes, called-tool set and returned evidence keys. Memory requires proper
scope, current-data precedence, history labels and declared reset/restore gates.

Golden correctness excludes E06/E07 (2 N/A); memory includes only H17-H19 and
E09-E12 (7 applicable, 33 N/A). Holdout memory includes G12/G13 only
(2 applicable, 12 N/A); the other holdout metrics include all 14.
Pending independent review is not N/A. Correct tool JSON is not automatically
correct final prose. Live output has not been evaluated by these results.

Golden 1.0.0 SHA-256:
`c35be99dbf15d2b9fff4e4aa479c6de5c03ddccfc9fff80a5ab2b38d548cf199`

Holdout holdout-v1.0.0 SHA-256:
`1965d096ebcf40d9c41a95ea519ec6f231456100a5b72f972149c92e3395ceee`

All 40 golden expectations were source-verified before execution: 34 initially
unambiguous and six intended-route/behavior refinements explicitly reviewed.
All 14 holdout expectations were independently checked from CSV/tool evidence
and documented behavior before freezing. No ground truth came from an agent
prediction. 'Source verified' is not a runtime pass or independent grade.

Exact source paths, record hashes and version filters are in
`source-provenance.json`. The holdout baseline archive comes from the later
pre-fix source snapshot `20261110T034016Z-1d9ab6bc`, not a replacement for
the original 03:33:45 golden result. The improved source archive needed an
unchanged publisher dependency restored with matching archived/pre-change
hashes; this is disclosed in the original holdout report.

## Failure analysis and improvements

1. **Intent routing gaps:** six golden lexical misses; narrow aliases and
   precedence fixes raised golden routing 85% -> 100%. On unseen cases,
   original improved routing was 14/14 vs baseline 10/14.
2. **Retrieved facts omitted from answers:** route-only fallback summaries
   omitted requested IDs, durations, remaining points, dated status and history.
   Grounded deterministic rendering raised golden correctness 52.63% -> 100%;
   original holdout answer quality still reached only 78.57%.
3. **Boundary/scope errors exposed by holdout:** G01 gave overdue count rather
   than explicit unfinished count; G06 substituted later history for an absent
   predecessor; G10 failed to filter renamed TEST IDs. Narrow remedies now
   derive total-minus-done, explicitly decline unavailable comparisons, and
   validate exact IDs transiently. Completion calculations and persisted
   checkpoint findings were preserved.

Final recorded regression suite: **252 passed, 1 skipped, 27 existing
Streamlit/Pandas warnings**. No tests were rerun for this submission packet.
Final replay: 54 scored requests + 10 setup requests; 113/113 evidence checks,
zero unexpected graph exceptions and zero outbound/live-provider calls.
The original paired holdout used 28 final + 6 setup requests.

## Caveats and archival status

All measurements are deterministic real-graph execution with generation
stubbed/fallback, mem0 disabled, isolated local SQLite and synthetic data.
No live-model quality, hosted semantic memory, production storage/authentication,
deployment durability or comprehensive security certification is established.
G12 remediation recalls zero irrelevant blocker turns (previously one), allowed
by the frozen recall range; success history and old checkpoint IDs remain.
No exact-output equivalence is claimed.

Earlier rubric/README status sentences saying 'no baseline conducted' describe
their original preparation date. They are preserved, not edited; this chronology
and the later executed records describe subsequent progress.

Frozen datasets, checksum files, rubrics, outputs, old reports and source
archives remain unchanged. Preliminary runs and failures are preserved.
See `preservation-verification.json` for the before/after file hash check.
