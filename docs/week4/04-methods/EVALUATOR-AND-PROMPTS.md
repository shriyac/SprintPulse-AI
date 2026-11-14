# Evaluator and prompts

Ground truth is frozen in `evaluation/golden/v1.json` and
`evaluation/holdout/v1.json`. Their `prompt`, required-answer/expected-behavior,
checks, N/A and memory fields are authoritative. Do not edit them.

`evaluation/RUBRIC.md` under this methods folder is unchanged. The implementation
`scoring.py` separates qualitative decisions from necessary runtime gates.
`verify.py:lookup/evidence_checks` checks deterministic paths/values; routing
checks actual node order, tool set and evidence keys; p95 is nearest-rank.

`instrumentation.py` records real callbacks and wraps generation. In deterministic
mode it records a simulated generation entry and forces the renderer/fallback,
not a live model answer. Failure cases include deliberate faults. Six holdout
setup requests are distinct from the 28 final baseline/improved requests.

Exact generator system/human prompt templates are preserved in
`05-reproducibility/source-versions/*/agents/llm.py`.
The human template interpolates task plus CURRENT tool outputs, historical
checkpoint context and semantic-memory observations with strict provenance
instructions. Exact weekly-report task construction and routing logic are in
each version's `agents/graph.py`. Prompt-version hashes are retained in run
metadata and source provenance. Saved records preserve each case question.
Do not substitute a modern prompt for archived evidence.

No new LLM-as-judge prompt or judge call was used. The automated report reused
saved provisional agent-assisted rationales, checked necessary gates and left
all original human fields untouched. Fifteen later author decisions are imported
separately; they do not replace all115 qualitative labels.

`03-author-review/automation/import_spotcheck.py` is the unchanged offline
agreement importer. It validates exact immutable evidence, decisions, notes and
attestations, and computes agreement only on completed sampled judgments.
Its old relative-workspace path assumptions are documented in reproduction
instructions; it is source evidence, not a one-click runner from this ZIP.
