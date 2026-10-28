# SprintPulse AI

**An agentic sprint intelligence assistant for project status, delivery risks, and weekly reporting.**

SprintPulse AI helps project managers and engineering leads understand sprint progress, identify recurring blockers, and produce evidence-backed status reports. Built with **Streamlit, LangGraph, and LangChain** as a Gen Academy Agentic AI certification project.

**[Live app](https://sprint-pulse-ai.replit.app/)** · **[Source code](https://github.com/shriyac/SprintPulse-AI)**

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

---

*Built for The Gen Academy Agentic AI certification as a portfolio demonstration of tool orchestration, historical analysis, persistent state, error handling, and human-in-the-loop reporting.*
