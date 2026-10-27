# SprintPulse AI

Streamlit sprint intelligence workspace for synthetic Jira-style snapshots, deterministic risk analysis, grounded LangGraph/LLM answers, and human-approved weekly reports.

## Run & Operate

- `uv sync --frozen` — install the locked Replit Python environment
- `uv run --frozen streamlit run app.py --server.port 5000` — run SprintPulse AI
- `uv run --frozen pytest -q` — run the Python test suite
- `python data/generate_sample_data.py` — regenerate the synthetic CSV snapshots
- `python -m pip install -r local/requirements.txt` — install Python dependencies outside Replit
- Optional LLM env: `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`; Replit AI Integration variables are also supported
- No database server, Jira credentials, or mem0 setup is required

## Stack

- Python 3.11+, Streamlit, pandas
- LangGraph StateGraph with SQLite checkpointing
- LangChain OpenAI-compatible chat model; deterministic fallback when no LLM credentials are configured
- Pytest

## Where things live

- `app.py` — dashboard, assistant, and weekly report UI
- `agents/` — typed graph state, conditional routing, and LLM calls
- `tools/` — CSV loading and deterministic sprint calculations
- `data/` — generated sprint snapshots and generator
- `reports/approved/` — reports saved after explicit approval
- `tests/` — tests for metrics, routing, checkpoints, and approval
- `pyproject.toml` / `uv.lock` — locked dependencies used for Replit publishing
- `local/requirements.txt` — standard local pip setup
- `artifacts/sprintpulse-ai/` — root service registration; runs the existing Python app, not a JavaScript frontend

## Architecture decisions

- Synthetic sample data is the only sprint source; Jira is intentionally not connected.
- Sprint calculations are deterministic and the model only receives tool-produced facts.
- SQLite stores LangGraph checkpoints under `data/`; keep raw DataFrames outside checkpoint state because the SQLite saver serializer does not encode pandas DataFrames.
- Draft reports are session-only until an explicit approval action saves a Markdown file.

## Product

SprintPulse AI summarizes delivery, detects overdue work and blockers, compares three historical snapshots, answers sprint questions, and drafts weekly status updates.

## User preferences

- Build incrementally and verify the application and tests; do not claim checks passed unless run.

## Gotchas

- Keep the same ticket IDs in every sample snapshot so blocker history remains comparable.
- Use the configured UV-based workflow for Replit; standard local pip setup is documented in README.md.

## Pointers

- See `README.md` for local setup and run instructions.
