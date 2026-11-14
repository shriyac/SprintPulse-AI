# Loom demonstration — 4 minutes 50 seconds maximum

Use saved synthetic evidence; no live LLM calls or new evaluation during recording.
Close environment/Secrets panels, private checkpoints, mem0 evidence and keys.
Prepare the four-page PDF, chronological report and saved case diffs beforehand.

| Time | Show | Say / demonstrate |
|---|---|---|
| 0:00-0:25 | Submission page 1 | Existing Streamlit/LangGraph app; Week 4 evaluates, not rebuilds. Synthetic data, no live LLM or hosted mem0 in the reported runs. |
| 0:25-1:05 | Dataset/rubric and saved manifest | Golden 40 = 20 happy/12 edge/6 known failure/2 adversarial. Separate frozen holdout 14. Show hashes and source-grounded requirements; N/A differs from pending. |
| 1:05-1:40 | One saved per-case trace | Show actual recall -> route -> tool-evidence node -> remember -> answer/report; actual tools, final answer, bounded failure scenario. Explain that generation was stubbed. Do not execute a command. |
| 1:40-2:20 | Chronological score table | Golden task 60% ->100%, correctness52.63% ->100%, routing85% ->100%. Original unseen improved holdout11/14, not14/14. Offline p95 is exploratory. |
| 2:20-3:20 | Original vs repaired G01/G06/G10 answers | Unfinished != overdue; missing predecessor cannot be invented; TEST-122-only must exclude others. Show actual archived failures then repaired outputs. Final14/14 is known-case remediation; no scored golden regressions. |
| 3:20-4:00 | Saved final test log and worksheet | 252passed/1skipped/27warnings from recorded run; not rerun now. Blank independent-review decisions; provisional agent grades are not human approval. |
| 4:00-4:35 | Readiness/live-safety review | Live model not tested, current client lacks token/spend gates; proposed43attempts/$1 requires controls, current pricing and explicit approval. No production or semantic-memory certification. |
| 4:35-4:50 | Submission page 4 | Key learning: correct tools do not ensure complete answers; freeze expectations; holdout reveals scope defects; remediation is not unseen generalization. State pending human sign-off clearly. |

Do not claim a dashboard screenshot proves end-to-end model correctness. Keep
on-screen artifacts local/synthetic. Uploading or sharing the recording is the
user's decision; no recording/upload has been performed.
