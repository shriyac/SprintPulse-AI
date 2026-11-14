# SprintPulse AI Week 4 — final frozen v1 validation

## Result: READY for baseline execution; baseline NOT RUN

The user approved the six previously partial intended-route labels with
case-specific expected-behavior refinements. Those refinements are now applied.
Dataset v1 (`version: 1.0.0`) is frozen. This is validation of the evaluation
specification, not evidence that the application passes its intended behaviors.

## Dataset checksum

File: `evaluation/golden/v1.json`

SHA-256:

```text
c35be99dbf15d2b9fff4e4aa479c6de5c03ddccfc9fff80a5ab2b38d548cf199
```

From the repository root:

```bash
sha256sum -c evaluation/golden/v1.sha256
uv run --frozen --no-sync python -m evaluation.verify
```

Both commands were executed successfully. The verifier enforces the frozen
checksum and the unchanged 34-case fingerprint. Future changes need a new,
reviewed version; do not silently rewrite v1 or update its checksum in place.

## Final dataset validation

| Requirement | Result |
|---|---|
| Exactly 40 unique cases | PASS |
| 20 happy / 12 edge / 6 known-failure / 2 adversarial | PASS |
| Source-grounded expectations and approved intended labels | **40/40** |
| Remaining PARTIAL cases | **0** |
| Original factual assertions independently revalidated | **82/82** |
| Cases with factual assertions | 38; the other 2 specify controlled error behavior |
| Original 82 assertion entries preserved | PASS — exact pre/post comparison |
| Other 34 cases preserved | PASS — exact object comparison and pinned canonical fingerprint |
| Synthetic CSV integrity and independent CSV/date oracle | PASS — all 3 snapshots |
| Frozen checksum | PASS |
| Golden baseline cases executed | **0** |

No expected answer was derived from an agent prediction. Numerical facts come
from the source CSVs/deterministic tools; operational definitions and allowed
clarification behavior come from the user's explicit review and the rubric.
Source-verified behavior expectations are not runtime proof of security,
memory isolation, graceful recovery, adversarial resistance, or answer quality.

## Six approved refinements

| Case | Intended route | Applied refinement |
|---|---|---|
| K01 | compare | Report blocked-ticket count 3 → 2, distinguishing observed changes from confirmed fixes. A specific fix claim needs ticket-level resolution evidence. |
| K02 | risk | Explicitly define “unresolved impediments” as currently Blocked for this evaluation; list SP-118/SP-122 without implying all possible impediments are covered. |
| K03 | report | Generate a draft; no authorization to save or publish follows from generation. |
| K04 | metrics | Ask for denominator clarification OR explicitly label both tickets 66.7% and points 71.1% (59/83). A single unlabeled percentage fails. |
| K05 | compare | Order completion chronologically: 41.7%, 54.2%, 66.7%. |
| K06 | metrics | State 16 completed tickets out of 24 for the selected sprint. |

K02's current Blocked ticket IDs were checked directly against Sprint 26.
K04's 71.1% was separately validated as `round(59 / 83 * 100, 1)`, using
existing tool counts. This derivation does not alter the original 82 golden
assertions or add a new application metric.

## Tests actually executed

One complete pytest collection covered both suites, without duplicate runs:

```bash
SPRINTPULSE_RUN_MEM0_LIVE_TESTS=false \
LANGSMITH_TRACING=false LANGCHAIN_TRACING_V2=false \
uv run --frozen --no-sync pytest -q tests \
  --junitxml=.local/evaluation-freeze/regression-results.xml
```

| Suite | Passed | Failed | Skipped |
|---|---:|---:|---:|
| Evaluation framework | **22** | 0 | 0 |
| Existing application regressions | **155** | 0 | **1** |
| Total | **177** | **0** | **1** |

Elapsed: **38.75 seconds**. The skipped test is the opt-in live mem0 sandbox
validation, intentionally disabled. The run emitted **27 Streamlit/Pandas
deprecation warnings**, not test failures; no application changes were made
to suppress them.

Regression tests exercise application code with their existing mocks and
temporary fixtures. They are not the 40-case evaluation baseline or a live
model evaluation. The framework tests also check freeze integrity, approved
refinements, approval guards, instrumentation, scoring, redaction and isolation.

## Integrity and execution boundaries

- Exactly K01–K06 changed in the case list. All case prompts/routes and original
  factual assertions remain as before; refinements affect expected behavior,
  source citations, review status and explanatory text.
- **167 protected source/configuration files** matched their pre-edit SHA-256
  values. Router, agent prompts, tools, UI, memory configuration, deployment
  settings, dependency files and source sprint CSVs were not modified.
- Changes are confined to evaluation data/documentation, its verifier and tests.
- No production mem0 enablement, remote memories, live model evaluation,
  LangSmith tracing or deployment operations were performed.
- No baseline run directory was created. The generic approval template remains
  false to prevent automatic execution; the dataset's user review is recorded
  separately in the frozen JSON and rubric.

Detailed local evidence (excluded from Git):

- `.local/evaluation-freeze/final-source-verification.json`
- `.local/evaluation-freeze/regression-results.xml`
- `.local/evaluation-freeze/full-tests.txt`
- `.local/evaluation-freeze/final-integrity.json`

All **40 cases are ready for a subsequently instructed baseline**. The six
known lexical-routing gaps remain intentionally unchanged and must be scored,
not hidden or relabeled as passing. Live LLM usage/costs and any future external
tracing still require separate approval.
