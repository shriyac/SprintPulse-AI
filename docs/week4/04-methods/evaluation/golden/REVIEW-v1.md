# Golden dataset review index — v1.0.0

The JSON file is authoritative. This index is a short reading guide, not an
agent evaluation result. For each row review its prompt, checks, source citations,
required answer and scenario in `v1.json`. The user approved all six previously
partial labels with the refinements below. Dataset v1 is frozen; no baseline
has run. Verify its exact bytes with `sha256sum -c evaluation/golden/v1.sha256`
from the repository root.

| Case | Type | Review focus | Intended route |
|---|---|---|---|
| H01 | Happy | Sprint health: 66.7%, 2 blocked, 8 overdue | question |
| H02 | Happy | Sprint 26: 16/24 done | metrics |
| H03 | Happy | Sprint 25: 13/24, 54.2% | metrics |
| H04 | Happy | Sprint 24: 10/24, 41.7% | metrics |
| H05 | Happy | 59/83 story points, 24 remaining | metrics |
| H06 | Happy | High blocker/overdue risks; 70% threshold | risk |
| H07 | Happy | Exactly SP-117–SP-124 overdue | risk |
| H08 | Happy | Maximum observed durations 37/32/2 days | risk |
| H09 | Happy | Recurring blocker appearances 3/3/2 | risk |
| H10 | Happy | Completion 41.7 → 54.2 → 66.7 | compare |
| H11 | Happy | +3 done tickets; +12.5 percentage points | compare |
| H12 | Happy | Grounded Markdown draft; never approved/saved | report |
| H13 | Happy | Sprint 25 had 3 blocked tickets | risk |
| H14 | Happy | Longest: SP-118, 37 days | risk |
| H15 | Happy | SP-122: 32 days at snapshot end | risk |
| H16 | Happy | SP-124: To Do, 8 days overdue | risk |
| H17 | Happy | Another project's conversation excluded | question |
| H18 | Happy | Current 66.7% wins over historical 54.2% | compare |
| H19 | Happy | Private restore of temporary conversation | question |
| H20 | Happy | SP-124 historical blockage ≠ current blockage | compare |
| E01 | Edge | Vague prompt: summary/clarification, no news invented | question |
| E02 | Edge | Empty graph question, not an empty UI submission | question |
| E03 | Edge | Comparison keyword precedence | compare |
| E04 | Edge | Overdue takes precedence over tickets | risk |
| E05 | Edge | Report takes precedence over other keywords | report |
| E06 | Edge | Missing sprint: bounded explicit failure, no model | metrics |
| E07 | Edge | Injected tool failure: one attempt, no model | metrics |
| E08 | Edge | Simulated LLM outage: grounded fallback | metrics |
| E09 | Edge | Report → metrics on same thread; reset + retained history | metrics |
| E10 | Edge | Failed request → successful comparison, no stale context | compare |
| E11 | Edge | Relevant same-thread follow-up | question |
| E12 | Edge | Different-thread history excluded | question |
| K01 | Known gap | Observed count 3 → 2 is not proof of a fixed risk; currently risk | **compare — user approved** |
| K02 | Known gap | Explicitly define impediments as currently Blocked; currently question | **risk — user approved** |
| K03 | Known gap | Draft only; no saving/publication authorization; currently question | **report — user approved** |
| K04 | Known gap | Clarify denominator OR label both 66.7% tickets and 71.1% points; currently question | **metrics — user approved** |
| K05 | Known gap | Chronological completion 41.7%, 54.2%, 66.7%; currently question | **compare — user approved** |
| K06 | Known gap | 16 completed tickets out of 24 selected-sprint tickets; currently question | **metrics — user approved** |
| A01 | Adversarial | Direct false-metric/save/credential instructions | report |
| A02 | Adversarial | Malicious summary in copied tool input | risk |

### N/A declarations to review

- Answer correctness: E06/E07 N/A because no factual answer is expected;
  graceful failure is assessed as task completion.
- Memory/context: only H17/H18/H19/E09/E10/E11/E12 are applicable. The other
  33 cases declare N/A because they have no recall/isolation requirement.
- p95 includes all final request attempts, including errors and fallback, so
  slow failures are not hidden. Only a request never started is N/A. Actual
  live-LLM coverage is reported separately; simulated failures do not prove
  actual provider outage handling.
- Every applicable human score starts **PENDING**, not PASS.

**Preparation evidence:** 82 exact factual assertions checked across 38 cases;
two cases specify controlled error behavior from source. All **40** now have
source-grounded expectations and approved intended labels; **0 PARTIAL** remain.
The other 34 case definitions and all 82 original factual assertions are
unchanged. K02's definition is explicitly evaluation-only; K04's 71.1% is
verified arithmetic from tool outputs 59/83, not an agent prediction.
Known routing gaps remain in the application. No golden request has been run.
