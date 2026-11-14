# Public Week4 evaluation export

This branch starts from GitHub main and preserves its existing history.
No local Replit checkpoint history was merged. All changes are additions under
`evaluation/` and `docs/week4/`; existing runtime/UI, synthetic CSVs, dependencies,
tests and deployment files at the repository root remain unchanged.

## Layout

- `evaluation/`: unchanged reviewed harness, frozen datasets/rubric and reports.
- `docs/week4/01-submission/`: final four-page PDF plus HTML.
- `docs/week4/02-evaluation-evidence/`: original baseline/improved scored outputs,
  original unseen holdout and separately labeled remediation, traces and logs.
- `docs/week4/03-author-review/`: final author report, sanitized completed15-row
  CSV, agreement and supporting provisional predictions.
- `docs/week4/04-methods/`: evaluator and prompt documentation.
- `docs/week4/05-reproducibility/`: exact reviewed source versions, environment
  lock and synthetic fixtures, with no checkpoint or database files.
- `docs/week4/regression-test-sources/`: three verbatim reviewed `.py.txt`
  regression sources. Copy into tests/ in a NEW isolated Week4 source-version
  workspace and rename to `.py` for an explicitly authorized future test run.
  They are NOT activated against the deliberately unchanged Week3 application.

The GitHub main runtime does not include the reviewed Week4 graph/renderer
changes. Those changes are archived in the source versions rather than installed
here, honoring the instruction not to alter the application. To reproduce the
saved improved/remediation evidence, use the appropriate archived source version
and matching evaluator in an isolated workspace as described in REPRODUCE.md.
Do not expect the unchanged Week3 runtime to produce the improved scores.

## Privacy

Public copies with reviewer_alias fields use “Author (private identifier
withheld)”; any matching private reviewer names were removed from public text.
Human decisions, source facts, expected behavior, rubric and saved responses are
unchanged. Original private worksheets, validation material and all original
evidence remain local. Internal integrity lists containing private-file hashes
were omitted. Public source/result checksums are regenerated below.

Archived manifests may reference local paths that are not exported. Treat them
as historical provenance, not working links. Only this branch's reviewed public
content is intended for GitHub; never push local main or all refs.

## Evidence interpretation

Final author sample:15/15 PASS,100% agreement (7task/5correctness/3memory).
This is author review, not independent third-party review. The remaining100of115
judgments are provisional, not human-approved. Original unseen holdout11/14 is
separate from post-remediation14/14. Live-model performance is unverified.
No evaluations, tests, models or production changes were executed for this push.
