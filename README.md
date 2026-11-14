# SprintPulse AI

**An agentic sprint intelligence assistant for project status, delivery risks, and weekly reporting.**

SprintPulse AI helps project managers and engineering leads understand sprint progress, identify recurring blockers, and produce evidence-backed status reports. Built with **Streamlit, LangGraph, and LangChain** as a Gen Academy Agentic AI certification project.

**[Live app](https://sprint-pulse-ai.replit.app/)** · **[Source code](https://github.com/shriyac/SprintPulse-AI)**

## Week 4 — Evaluate Your Agent

The Week 4 submission evaluates the existing LangGraph assistant using **40 frozen golden cases** and a separate **14-case holdout**, with recorded routes, tool calls, answers, errors, latency, and explicit scoring rules.

**Start here:**

- [Final four-page evaluation PDF](docs/week4/01-submission/SprintPulse-AI-Week4.pdf)
- [Chronological comparison and measured improvements](docs/week4/02-evaluation-evidence/chronological-comparison.md)
- [Final author-review report](docs/week4/03-author-review/FINAL-AUTHOR-REVIEW.md)
- [Frozen golden dataset](evaluation/golden/v1.json), [holdout dataset](evaluation/holdout/v1.json), and [scoring rubric](evaluation/RUBRIC.md)
- [Reproducibility instructions](docs/week4/05-reproducibility/REPRODUCE.md) and [public-export scope](docs/week4/PUBLIC-EXPORT.md)

### Saved evaluation results

| Evaluation stage | Task completion | Answer correctness | Tool routing | Memory/context | p95 latency |
| --- | --- | --- | --- | --- | --- |
| Golden baseline | 24/40 | 20/38 | 34/40 | 7/7 | 102.315 ms |
| Golden initial improved | 40/40 | 38/38 | 40/40 | 7/7 | 102.532 ms |
| Original unseen holdout, improved agent | **11/14** | **11/14** | 14/14 | 2/2 | 228.572 ms |
| Post-holdout remediation, golden replay | 40/40 | 38/38 | 40/40 | 7/7 | 93.482 ms |
| Post-holdout remediation, holdout replay | **14/14** | **14/14** | 14/14 | 2/2 | 401.262 ms |

These are **saved deterministic graph evaluations with stubbed/fallback generation**, not live-model benchmarks. Full-dataset qualitative grades remain provisional agent-assisted assessments. N/A judgments are excluded from their metric denominators; latency is exploratory, not a statistically established performance comparison.

The original unseen result remains **11/14**. The later **14/14** follows fixes for unfinished-ticket counts, missing predecessor snapshots, and exact ticket-ID scope; it is a remediation replay, **not a new unseen evaluation**.

### Human spot-check

An author-reviewed sample contains **15/15 PASS judgments and 100% agreement** with provisional automated predictions: **7 task-completion, 5 correctness, and 3 memory/context judgments**. This is **author review, not independent third-party review**. The purposive, all-PASS sample does not establish full-dataset accuracy; the other 100 of 115 applicable qualitative judgments were not human-reviewed by this sample.

**Application boundary:** this branch adds evaluation evidence and documentation without changing the existing Week 3 runtime or deployment configuration. The reviewed improved/remediation implementations and regression-test sources are archived for isolated reproduction; the unchanged runtime is not claimed to produce their scores. No live-model or production validation is implied.

## What it does

- **Sprint Dashboard:** Completion metrics, overdue work, blockers, and delivery risk flags.
- **AI Assistant:** Natural-language sprint questions answered using deterministic analysis tools, with an LLM when configured.
- **Historical insights:** Compares tickets across sprints and identifies recurring blockers and changes in status.
- **Conversation continuity:** LangGraph SQLite checkpoints enable context-aware follow-ups and private-key conversation restoration while the checkpoint database remains available.
- **Weekly Reports:** Generates status summaries and requires **human approval** before saving.
- **Optional semantic memory:** A hosted **mem0** integration stores and retrieves scoped historical findings; it is **disabled in the published application**.

## Architecture

```text
Streamlit (Dashboard | AI Assistant | Weekly Reports)
                         |
               LangGraph workflow
                         |
       +-----------------+-----------------+
       |                 |                 |
  Sprint tools     SQLite checkpoints  Optional mem0
  (current data)   (conversation state) (historical findings)
       |                                   |
  Synthetic CSVs                    PostgreSQL ledger
       +-----------------+-----------------+
                         |
          Grounded answer / draft report
                         |
                Human approval
```

LangGraph routes requests through sprint retrieval, historical comparison, risk analysis, and reporting steps. **Current sprint-tool results take precedence over historical memories.** The agent falls back to deterministic answers when an LLM is unavailable.

## Tech stack

| Layer | Technology |
| --- | --- |
| Interface | Streamlit |
| Orchestration | LangGraph |
| LLM integration | LangChain, OpenAI-compatible model (optional) |
| Sprint analysis | Python, Pandas, deterministic tools |
| Conversation state | SQLite / LangGraph checkpoints |
| Long-term semantic memory | Hosted mem0 (optional, development-validated) |
| Memory ingestion ledger | PostgreSQL (optional integration) |
| Tests and deployment | Pytest, Replit |

## Data

The project includes **three synthetic Jira-style sprint snapshots**, each tracking the same **24 ticket IDs**. Metrics include completion, overdue tasks, blocker duration, recurring blockers, and delivery risks. This demo **does not connect to live Jira, Asana, or Notion**.

## Run locally

Requires **Python 3.11+**.

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install -r local/requirements.txt
cp .env.example .env      # Windows PowerShell: Copy-Item .env.example .env
streamlit run app.py --server.port 5000
```

Set `OPENAI_API_KEY` in `.env` for LLM-generated answers (optionally `OPENAI_BASE_URL` for a compatible provider). Without an LLM, deterministic sprint insights remain available. Never commit credentials.

Run tests:

```bash
pytest -q
```

For locked Replit dependencies, see `pyproject.toml` and `uv.lock`. Optional mem0 dependencies and validation commands are documented in the technical notes.

## Memory and validation

**Conversation memory:** LangGraph checkpoints retain prior turns and enable follow-up questions. A private resume key can restore a conversation **only while its checkpoint database still exists**; the key is a bearer credential and must be kept private.

**Semantic memory:** Hosted mem0 integration was validated in development for live writes, scoped semantic retrieval, and historical context used by LangGraph. The optional PostgreSQL ledger supports deduplication and write reconciliation. **mem0 remains disabled in production** pending durable storage, credential separation, and access-control verification.

The app includes automated tests for sprint analysis, routing, memory isolation, failure recovery, and report approval. Run the test command above for the current result.

## Known limitations

- Published app uses **synthetic CSVs**, not live project-management APIs.
- Local SQLite checkpoints and saved reports **are not guaranteed to survive Replit redeployments or instance replacement**.
- Private resume keys provide conversation-level access, **not authenticated user accounts**.
- Production mem0 storage and security configuration are **not yet enabled or verified**.

## Repository guide

- `app.py` — Streamlit app
- `agents/` — LangGraph orchestration, LLM, and memory integration
- `tools/` — Sprint loading and calculations
- `data/` — Synthetic data and ledger schema
- `tests/` — Automated validation
- `docs/` — Detailed technical and production-readiness notes
- `evaluation/` — Week 4 frozen datasets, scoring rubric, harness, and evaluation reports
- `docs/week4/` — Final submission, sanitized saved results, author review, and versioned reproduction sources

---

*Built for The Gen Academy Agentic AI certification as a portfolio demonstration of tool orchestration, historical analysis, persistent state, error handling, and human-in-the-loop reporting.*
