# Week4 merge readiness

**Ready to merge as an evaluation-only branch.**

The required harness, frozen40-case golden dataset and unchanged rubric,
baseline/improved scored runs, original14-case paired holdout, separately labeled
remediation, final PDF, sanitized author-review evidence and regression sources
are included. Detailed record counts are in MERGE-READINESS.json.

## Small packaging gap closed

The three reviewed regression sources previously existed only as `.py.txt`
archives to avoid collecting Week4 tests against the unchanged Week3 runtime.
`regression-test-sources/week4-regression-tests.zip` now contains the exact
original Python sources under `tests/`:

- `test_evaluation_framework.py`
- `test_answer_completeness.py`
- `test_holdout_remediation.py`

No tests, labels or application logic were rewritten. ZIP integrity, byte-for-
byte source equality and Python syntax were checked; tests were NOT rerun.
The original text archives, evidence, datasets and SHA256SUMS remain unchanged.
The additional files are covered by MERGE-READINESS-SHA256SUMS.

## Future isolated regression run (not executed for this review)

From the repository root, prepare a NEW scratch directory:

    WORKDIR="$(mktemp -d)"
    cp -R docs/week4/05-reproducibility/source-versions/post-holdout-remediation/. "$WORKDIR/"
    cp -R evaluation "$WORKDIR/evaluation"
    python -m zipfile -e docs/week4/regression-test-sources/week4-regression-tests.zip "$WORKDIR"

Use the pinned dependencies from that scratch directory's pyproject.toml and
uv.lock in an explicitly authorized development environment. Keep credentials
unavailable, MEM0_ENABLED=false and tracing disabled; block external network
access for the test process. Never use a production database or checkpoint.
Once dependencies are available, the target command is:

    cd "$WORKDIR"
    uv run --frozen --no-sync python -m pytest -q tests

These commands are instructions, not evidence of a fresh successful test run.
Use an existing prepared environment or run `uv sync --frozen` separately if
dependency downloads are authorized. Inspect the reproduction guide for
historical source-path limitations. Existing repository pytest discovery is
unchanged because regression sources remain inside the ZIP, not active tests/.

## Boundaries before merging

- Runtime/UI and deployment files are unchanged from GitHub main. Only the
  README, evaluation files and public Week4 documentation/evidence differ.
- Merging this branch DOES NOT install the archived improved/remediation graph
  and renderer as the active application. That would require separate approval.
- Original unseen improved holdout remains11/14; remediation14/14 is known-case
  replay. Full-dataset qualitative scores remain provisional.
- Fifteen author-reviewed judgments all PASS,100% sample agreement; not
  independent review and not approval of all115 judgments.
- No new model, production, durability or fresh-test claims are made.
- The Loom link is still a placeholder. It is a submission task, not a Git
  merge conflict or a missing evaluation artifact.

Prior public security reports describe earlier publication snapshots; the new
checklist supplements them rather than rewriting historical claims.
