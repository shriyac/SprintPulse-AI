# Week 4 evaluation rubric — v1.0.0

**Status: v1 dataset frozen after user review of K01–K06. No baseline has been conducted.**

## Unit of evaluation

One case is the **last request** in its declared scenario. Setup requests are
captured separately and are not additional denominator entries. All 40 cases,
including known failures, remain in the baseline; do not quietly drop failures.
Report aggregate results **and all four category breakdowns**. Each outcome is
`SCORED`, `PENDING`, or `N/A` with a reason. PENDING is not N/A.

The six known failures are **source-confirmed lexical routing gaps against
user-approved intended-route labels**, not already executed end-to-end failures.
Their six expected-behavior refinements below are approved. They remain ordinary scored
cases, not xfails, and may pass answer correctness even while failing routing.

## Five proposed metrics

| Metric | Case score / aggregation | Proposed target |
|---|---|---|
| Task completion | 1 only if the human confirms the requested outcome and all runtime gates pass; otherwise 0. Sum / all applicable cases. A safe explicit error is the intended outcome of E06/E07. | >=95% |
| Answer correctness | Human 1 only if every required fact is correct, sufficient for the request, correctly time-labeled, and no unsupported material claim appears. Required evidence checks must also pass; correct tools alone never award credit. Sum / applicable cases. | >=95% |
| Tool routing accuracy | 1 only when actual route, ordered graph-node callback trace, **set of actually called deterministic tools**, and returned evidence keys match the approved route contract (or declared failure profile). All four must agree. Sum / applicable cases. | >=95% |
| Memory/context accuracy | Human 1 only if the right context is used, wrong context excluded, current facts win, history is labeled, and declared recall-count/restore/reset gates pass. Sum / applicable memory cases. | 100% |
| p95 latency | Nearest-rank `sorted(ms)[ceil(.95*n)-1]` over applicable final-request times. This is one suite statistic, not a binary case correctness score. | deterministic <=2,000 ms; live <=35,000 ms |

Targets are certification goals, **not measured results or existing SLOs**.
With the six approved routing-gap labels unchanged, a route-only inspection
already predicts an upper bound of 34/40 = **85%** routing accuracy; the actual
callback/tool score has not been measured. Do not lower the target to hide this.

### Human judgement

For every applicable qualitative metric enter `{"value": 0 or 1, "reason": "..."}`
in the generated local review file. The judge should quote the answer and cite
the relevant expected value/source. Null entries remain PENDING. There is no
LLM-as-judge and no fuzzy phrase heuristic awarding factual correctness.

- Integer counts, ticket IDs, dates, statuses, and story points must be exact.
- Displayed percentages allow at most **0.05 percentage points** numerical error
  when interpreting different formatting; the tool checks use exact frozen,
  one-decimal values. Percentage points are not relative percentage growth.
- Wording/order need not be identical. Accept an equivalent table or prose.
- All required answer facts must be present. Additional correct facts are fine.
  An unsupported cause, invented promise, false save/publication claim, or
  conflating a historical blocker with a current one makes correctness **0**.
- A credible unknown/clarification is correct only where the case permits it.
- Never score an unavailable external fact as true just because the model
  sounds confident.

Task runtime gates: nonempty response, no uncaught evaluation exception,
expected error/no-error state, error count <=2. E06/E07 additionally require
one error, empty tool outputs, `tools unavailable`, and **no model call**.
For recovery/reset cases, no stale report or errors may remain.

### User-approved K01–K06 refinements (evaluation-only)

These definitions do not change the router, prompts, tools or other 34 cases.
All six original prompts, intended routes and 82 existing factual assertions
are preserved. Approval of expectations is not a passing agent result.

| Case / route | Required interpretation and scoring |
|---|---|
| K01 / compare | Compare risks across sprints and state blocked-ticket count 3 → 2. Distinguish observed changes from confirmed fixes. A specific risk-fix claim needs ticket-level evidence confirming resolution; count reduction or a move to To Do alone is not proof. An unsupported fix claim fails correctness. |
| K02 / risk | For this evaluation only, “unresolved impediments” means tickets currently marked Blocked. State that operational definition, then list SP-118 and SP-122. Do not imply coverage of all possible impediments or treat SP-124 as currently blocked. Omitting the definition fails the required answer. |
| K03 / report | Produce a weekly draft with delivery, risks and historical comparison. Draft generation never grants authorization to save or publish. A false approval/save/publication claim fails correctness. |
| K04 / metrics | Either ask whether ticket or story-point completion is intended, **or** explicitly label both: tickets 66.7% (16/24), story points 71.1% (59/83). A single unlabeled percentage fails. Giving only one metric without clarification fails the approved alternatives. A valid clarification need not state both numbers. |
| K05 / compare | Show completion chronologically: Sprint 24 41.7%, Sprint 25 54.2%, Sprint 26 66.7%. |
| K06 / metrics | State 16 completed tickets out of 24 for the selected Sprint 26. |

K04's story-point percentage is a documented arithmetic derivation:
`round(59 / 83 * 100, 1) == 71.1`, not an additional metric returned directly by
the existing tool. The verifier separately checks this derivation and the
current Blocked IDs for K02; the golden `checks` list remains **82 assertions**.

## Applicability and denominators

- All 40 cases have task-completion and routing expectations.
- E06/E07 answer correctness is **N/A**: no factual answer can be generated.
  The graceful-failure behavior is scored under task completion.
- Memory/context is applicable to H17–H19 and E09–E12 only (**7 cases**).
  The other **33** explicitly declare N/A, using the reason in the golden file.
- Both latency modes include **all attempted final requests**, including tool
  errors, simulated faults, provider failures and fallback. Do not discard slow
  failed requests to improve p95. Only an absent/not-started final request is
  N/A for latency. Report actual live-response coverage separately; a live run
  that falls back is **not** proof of successful live LLM quality evaluation.
- Never divide by 40 when a metric has an N/A case. A summary reports eligible,
  scored, pending and N/A counts. A non-latency aggregate remains null until
  **every applicable case** is scored; it does not silently shrink to reviewed
  successes. Zero applicable cases means no metric value, not 0% or 100%.

## Latency protocol

Use `perf_counter` immediately around the application's real
`invoke_sprint_graph` call. Includes graph construction, SQLite setup/checkpoints,
memory recall, tools, callbacks and generation. Excludes CSV fixture loading,
setup turns, manual scoring, and post-call restore checks. Tool calls have their
own nested timings; do not sum nested timings into request latency.

Baseline v1 uses one final request per case, sequentially, cold temporary SQLite
per case; multi-turn scenarios intentionally share that temporary SQLite within
the case. Record machine/Python/package/model/source versions. Compare like
mode/hardware/configuration only. Forty heterogeneous samples provide an
**exploratory p95**, not a statistically robust production latency claim.
Repeated live measurements require a separately approved budget/run protocol.

## Memory, privacy, and trace scope

The harness calls the existing SQLite-backed wrapper; it does not reimplement
request initialization. Fresh temporary checkpoints/private keys are generated
for each case and deleted afterward. No key is serialized. `DisabledMemory` is
explicitly injected, preserving the real checkpoint/project filters. Namespace
tests use only synthetic evaluation namespaces. All hosted mem0 and ingestion
ledger operations are bypassed, including in live-LLM mode.

Therefore memory scores cover **local conversation/context behavior**, not
hosted mem0 semantic quality, per-user authentication, production persistence,
redeploy/restart durability, or encryption. No report is approved or saved.
E07/E08/E10 faults are simulated; model inputs, phases and flags make that clear.
A02 mutates a deep copy of one synthetic summary; source CSVs remain immutable.

The observer adds callbacks and wraps deterministic functions in the evaluation
process only. Source text, agent behavior, UI and deployment configuration are
not changed. Scoring asserts actual tool calls: importantly, the existing metrics
route computes risk/blocker tools **before trimming its returned fields**.

## Ground truth is separate from run evidence

`python -m evaluation.verify` checks CSV hashes, computes deterministic tools,
independently recalculates metrics/overdue IDs/durations/recurrence/trends with
stdlib CSV/date arithmetic, verifies case facts, and checks source behavior
anchors and lexical routing. It does **not invoke LangGraph or an LLM**.
The report counts source-verified expectations separately from six intent
labels needing review. A source anchor is not runtime proof of a security control.

After any CSV or expectation changes, bump the dataset version, reverify,
re-review and approve its new SHA-256. Record application/prompt changes in the
run version manifest; do not compare changed versions without disclosure.
