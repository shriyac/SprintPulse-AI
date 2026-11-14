# SprintPulse AI — post-holdout remediation v1

**Known-case regression replay, not an independent unseen evaluation.**
Qualitative scores below are agent-assisted saved-answer reviews, pending
independent human acceptance. Frozen expected behaviors, labels, applicability
rules and scoring code were not changed.

## Changes

- `agents/answer_rendering.py`: explicitly derive requested unfinished count
  as deterministic total minus completed, distinct from overdue. Missing or
  invalid counts remain unavailable. Completion-rate calculations are unchanged.
  Detect unavailable requested snapshots/predecessors and separately label
  available selected-snapshot information. Validate whole ticket identifiers
  against selected-snapshot IDs; unknown/partial IDs fail closed. Ticket-specific
  risk answers omit unrelated tickets and sprint-wide risk flags.
- `agents/graph.py`: pass selected-snapshot ticket IDs transiently to the
  deterministic renderer. No graph routing/node/tool changes, new state fields,
  checkpoint schema changes, or additions to persisted tool findings.
- `tests/test_holdout_remediation.py`: 33 regressions covering unequal unfinished
  and overdue counts, zero/all/no completed, invalid/missing counts, missing
  predecessors, explicit absent snapshots, available-history boundaries,
  renamed/case-insensitive IDs, whole-token negative matches, multi-ID scope,
  historical-only IDs, absent current evidence, and transient graph validation.
- `evaluation/remediation.py`, `evaluation/remediation_worker.py`: new offline
  replay runner/worker using source copies, network denial, stub generation,
  DisabledMemory, temporary SQLite checkpoints and forbidden report saves.
  Existing evaluation runners, rubrics, datasets and archived artifacts unchanged.
- This report and supplemental project-memory guidance were added/updated.

## Final verification

Full suite: **252 passed, 1 skipped, 27 warnings**, executed with:

```bash
uv run --frozen --no-sync pytest -q \
  --junitxml=.local/remediation-verified-pytest.xml
uv run --frozen --no-sync python -m evaluation.remediation
```

The skip is the guarded live mem0 test; warnings are existing Streamlit/Pandas
deprecation warnings. No hosted mem0 or live model call was run.

Final run:
`.local/evaluations/post-holdout-remediation-20261111T011644Z/`

All 40 golden cases and 14 holdout cases were executed through the real graph.
Golden setup scenarios used seven extra requests; the holdout used three setup
requests for this one-version replay. The previous paired two-version evaluation
used six setup requests; its fixture/scenario definitions are unchanged.
All final routing contracts and deterministic tool evidence checks passed.

### G01, G06, G10

| Case | Route / evidence node | Result | Saved-answer evidence |
|---|---|---|---|
| G01 | metrics / retrieve_sprint_data | PASS | 16 of 24 complete, 66.7%; explicitly “Unfinished tickets (total minus completed): 8,” distinguished from overdue. |
| G06 | compare / compare_sprint_history | PASS | “The requested comparison cannot be completed: the requested predecessor snapshot is unavailable.” Separately provides Sprint 24, 10/24, 41.7%; no later sprint substituted. |
| G10 | risk / detect_risk | PASS | TEST-122 only, maximum observed 32 days in Sprint 26; TEST-118/TEST-124 absent. |

Every final request traversed `recall_conversation`, `route_request`, its evidence
node, `remember_findings`, and `answer` or `report`. Per-case records include
actual callbacks, nested tool calls, outputs, errors, generation-stub events,
setup turns, timing, evidence checks and provisional review scores.

## Updated five-metric results

### Original 40-case golden v1

| Metric | Prior improved run | Post-holdout remediation | Delta |
|---|---:|---:|---:|
| Task completion | 40/40, 100% | 40/40, 100% | 0 pp |
| Answer correctness | 38/38, 100% | 38/38, 100% | 0 pp |
| Tool routing | 40/40, 100% | 40/40, 100% | 0 pp |
| Memory/context | 7/7, 100% | 7/7, 100% | 0 pp |
| Offline p95 | 102.532 ms | 93.482 ms | −9.050 ms |

**No scored golden regressions.** Correctness excludes E06/E07 (N/A);
memory excludes 33 cases. H15/H16 omit unrelated aggregate risks; H19/E11
accordingly recall a more narrowly scoped earlier answer. Other golden answers
are byte-identical to prior improved outputs.

### Frozen 14-case holdout

| Metric | Prior improved run | Post-holdout remediation | Delta |
|---|---:|---:|---:|
| Task completion | 11/14, 78.57% | 14/14, 100% | +21.43 pp |
| Answer correctness | 11/14, 78.57% | 14/14, 100% | +21.43 pp |
| Tool routing | 14/14, 100% | 14/14, 100% | 0 pp |
| Memory/context | 2/2, 100% | 2/2, 100% | 0 pp |
| Offline p95 | 228.572 ms | 401.262 ms | +172.690 ms |

G01–G14 all pass the unchanged expectations in provisional review.
Memory excludes 12 cases. G12 now recalls zero irrelevant blocker turns for a
points-only request (previously one); its frozen allowable recall range starts
at zero. Successful historical turn and old checkpoint IDs remain preserved,
failed turn excluded, current request reset, and correct tool route selected.
G13 still recalls zero from another private key. This is not exact-output
equivalence or evidence that all possible memory follow-ups are covered.

Nearest-rank p95 is exploratory: at n=14 it is the maximum. The higher observed
holdout latency is reported, not discarded; both datasets remain below the
2,000 ms offline target. Single-run, heterogeneous samples do not establish a
performance improvement or statistically confirmed regression. Workers execute
different dataset scenario wrappers; compare each dataset only to itself.

## Preservation and evidence

- Golden version and checksum unchanged:
  `c35be99dbf15d2b9fff4e4aa479c6de5c03ddccfc9fff80a5ab2b38d548cf199`
- Holdout version and checksum unchanged:
  `1965d096ebcf40d9c41a95ea519ec6f231456100a5b72f972149c92e3395ceee`
- Hash verification preserved all 345 pre-existing evaluation/data files,
  including prior reports, results, source archives and scoring rubrics.
- Preliminary replay and failed/intermediate test logs are retained separately;
  the initial replay exposed wording and context-ranking issues before final
  correction. This report scores only the final identified source snapshot/run.
- `scored-results.csv`, per-case JSON, `records.jsonl`, reviewed records,
  exact source copies/manifests, answer diffs, pytest text/XML, review templates,
  summary, integrity evidence and SHA256SUMS are in the final run folder.
- Qualitative judgments are explicitly provisional. Blank human-review
  templates remain available for both datasets; no human sign-off is implied.

## Limitations and boundaries

These fixes and measured quality results cover deterministic fallback rendering.
Live LangChain output remains model-generated; model prompts/client behavior
were not changed, no paid calls were made, and live-model compliance is untested.
Ticket status still uses supplied ticket-level evidence; knowing an ID exists
does not invent a status when that evidence is missing. Numeric immediate
predecessor detection follows existing `Sprint N` naming; arbitrary unknown
sprint names or unrestricted natural-language expressions are not newly certified.

Existing SQLite memory/checkpoint retention and hosted-memory opt-in boundaries
are unchanged. No hosted mem0, production DB, UI, CSV, deployment setting,
credential or production checkpoint change was made.

The development workflow restarted successfully and its health endpoint returned
HTTP 200. The screenshot captured a loading placeholder, not a completed visual
journey; existing Streamlit session/UI regression tests passed. Production was
not republished or validated.

The repaired holdout has been used for remediation and is no longer independent
unseen evidence. No new holdout was generated. Any further unseen dataset
requires separate user review and freezing before execution.
