# SprintPulse AI

SprintPulse AI is a Streamlit sprint intelligence app built for an Agentic AI certification project. It uses LangGraph to route sprint questions through deterministic analysis tools, compare history, detect risks, and prepare weekly reports. LangChain can phrase answers from tool outputs when an OpenAI-compatible LLM is configured.

## Included

- Three reproducible Jira-style CSV snapshots, each containing the same 24 ticket IDs.
- Deterministic completion, overdue, blocker duration, recurring blocker, comparison, and risk calculations.
- Typed LangGraph state, conditional intent routing, bounded exception handling, and SQLite checkpointing.
- Streamlit tabs for Sprint Dashboard, AI Assistant, and Weekly Reports.
- A human approval action before an approved report is written to `reports/approved/`.
- No Jira authentication. Optional hosted mem0 semantic memory is disabled by default.

The CSV snapshots are synthetic training data. Sprint end dates are included in each snapshot; overdue calculations are evaluated relative to that snapshot's sprint end date.

## Run locally

Requires Python 3.11 or newer.

```bash
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
python -m pip install -r local/requirements.txt
cp .env.example .env            # Windows PowerShell: Copy-Item .env.example .env
```

For LLM-backed answers, edit `.env` and set `OPENAI_API_KEY` (and optionally `OPENAI_BASE_URL` for an OpenAI-compatible provider). When running in Replit, the Replit AI Integration variables are used automatically. Without an LLM configuration, the app remains usable and returns deterministic tool-based answers and reports.

Start the app:

```bash
streamlit run app.py --server.port 5000
```

Regenerate the same synthetic sample snapshots:

```bash
python data/generate_sample_data.py
```

Run tests:

```bash
pytest -q
```

Replit uses the locked dependencies from `pyproject.toml` and `uv.lock` in an isolated environment. The pip requirements file is kept at `local/requirements.txt`, not the repository root: a root `requirements.txt` selects system pip during the initial publishing dependency step, even when listed in `.replitignore`. Use the command above for local pip-based setup.

The `artifacts/sprintpulse-ai/` service registration maps the published root URL to this same Python application. Checkpoints and approved reports currently use local files; published files can reset on republish, so download important reports. Durable shared storage is a separate production enhancement.

The build-installed Python environment must be included in the publish image: startup uses `uv run --frozen --no-sync`, so listing `.pythonlibs/` or `.venv/` in `.replitignore` would remove its runtime dependencies. These directories remain excluded from Git. Only Streamlit is enabled in production; scaffold API/canvas services are development-only.

To check production startup without relying on development dependencies, stop the preview (port 20155 must be free), then run `python scripts/verify_production.py`. This creates a temporary, secret-free environment from the lockfile, checks imports/data/tabs, runs the exact artifact production command, verifies `0.0.0.0:20155` and repeated health responses, and cleans up. It does not publish.

## Project layout

```text
agents/      LangGraph orchestration and LangChain model calls
tools/       CSV loading and deterministic sprint calculations
data/        Sample CSV snapshots and their reproducible generator
reports/     Approved Markdown reports (saved only after human approval)
tests/       Pytest coverage for metrics, routing, checkpointing, and approval
local/       requirements.txt for local pip-based setup
app.py       Streamlit interface
```

## Grounding and approval

The LLM receives fresh deterministic tool outputs plus relevant, explicitly historical
checkpoint findings. Current tool evidence takes precedence over earlier answers.
The app labels whether a response came from the LLM or deterministic fallback.
Weekly report drafts stay in the current session until **Approve and save** is selected.
No Jira data is fetched and no report is sent to an external service.

## Conversation recall and restoration

- Each conversation has a random 256-bit private resume key. Save it with
  **Download resume key** in the sidebar before leaving the session.
- After a browser refresh, a new session, or a development process restart, enter
  that key under **Private resume key** and select **Resume conversation**.
  The retained database must still be present. The last successful answer is
  displayed as historical; submitting a question recomputes current tool outputs.
- Keys are bearer capabilities: anyone holding one can access that conversation.
  Keep downloaded keys private. Keys are not put in URLs or public thread lists.
  There is no account-based recovery for lost keys. Existing UUID4 conversation
  keys remain valid; predictable/shared thread names cannot be resumed in the UI.
- Follow-up questions automatically trigger a `recall_conversation` LangGraph
  node. It reads only that thread's existing checkpoints, filters incomplete/tool-
  failed turns, and selects relevant earlier questions, answers and tool findings.
  Both Assistant requests and new report drafts use the selected conversation.
  Report approval is still a separate, explicit action.
- Recall scans at most 128 checkpoints / 16 successful turns and includes at most
  three relevant turns. It is deterministic lexical/ticket-ID retrieval, not vector
  search. Historical answers are context, not instructions or current evidence.
- Request routing, errors, retries and tool outputs are reset as before.
  The recall view is recomputed on each turn; earlier checkpoints are not deleted.
  With no LLM, the answer includes clearly labeled historical excerpts alongside
  fresh deterministic results. Optional mem0 complements this checkpoint recall;
  it never replaces the LangGraph checkpoint database.
- **New conversation** creates a new key without deleting the previous history.
  Switching conversations clears session-only report drafts/approval indicators
  to avoid mixing conversations, but does not delete approved report files.
  Unapproved drafts are not automatically reinstated or approved on resume.

### Production durability limitation

SQLite is still stored at `data/checkpoints.sqlite` (or the configured
`SPRINTPULSE_CHECKPOINT_DB` path). No storage migration or checkpoint schema migration
has been performed. Local development process restart persistence can be tested,
but **a private resume key cannot recover a database that has been lost**.

Published Replit filesystem writes must not be relied upon for durable storage
across restarts, replacement instances or redeployment. The development checkpoint
file is excluded from publishing by `.replitignore`. A path override alone is not
a durable-storage solution.

For production conversations, use an external persistent PostgreSQL database and
LangGraph's PostgreSQL checkpointer, with an explicit migration/export plan for
existing SQLite histories. This is a recommendation only: no PostgreSQL
provisioning, connection or storage substitution was performed in this change,
and production durability is **not verified**. See the official
[Replit SQL database documentation](https://docs.replit.com/features/data-and-storage/sql-database).

## Optional mem0 semantic memory — disabled by default

The default app needs no mem0 account, SDK, network call, or new database.
`app.py`, the three-tab layout, private resume keys, sample CSVs and report
approval are unchanged. The LangGraph flow now includes optional historical
search in `recall_conversation` and a `remember_findings` step after successful
sprint tools. Routing and errors still reset each turn.

### What is stored and searched

- Deterministic recurring-blocker and risk observations, with source ticket IDs,
  sprint identifiers, snapshot observation dates, UTC recording timestamps and
  evidence fingerprints. Routine completion metrics are not independent memories.
- Dependencies only from explicit source statements such as “waiting on …” in a
  blocker reason. Decisions/dependencies can also be stated in the existing
  Assistant using `Decision for SP-118: Use the sandbox fallback.` or
  `Dependency for SP-118, SP-122: Await partner approval.` Only known ticket IDs
  are accepted. Generated model suggestions are never stored as decisions.
- Hosted `MemoryClient.add(..., infer=False)` stores the supplied finding, not
  LLM-extracted claims. Only the bounded finding text/metadata and search query
  are sent to mem0, not full conversations or private resume keys.
- Every operation is scoped by configured project, environment and a hashed
  private conversation capability. This is anonymous per-conversation isolation,
  **not authenticated cross-conversation user identity**. New keys do not share
  memories. Returned metadata is checked again even after provider filtering.
- Once a project namespace is configured, checkpoint recall/restoration is also
  namespace-filtered to prevent old semantic answers leaking through saved
  conversation text. Legacy unscoped turns remain usable on first namespace
  adoption; ambiguous mixed-project history is not automatically reassigned.
  Keep project/environment configuration when disabling mem0. History is not
  deleted, and SQLite is not migrated or replaced.
- Up to three relevant semantic results are supplied as historical observations.
  Old findings remain useful history, but cannot establish current ticket status.
  Explicitly expired, low-score, duplicate and cross-scope results are excluded.
  All current metrics/statuses come from the existing fresh sprint-tool execution
  against the selected CSV snapshot. There is no live Jira synchronization.

### Hosted search compatibility and provenance

SDK `mem0ai==2.2.1` posts to `/v3/memories/search/`. The adapter uses the
documented `filters` object (private owner plus project/environment metadata),
`top_k=3`, `show_expired=False`, and an explicit `threshold=0.1` matching the
documented V3 hybrid-search default. An approved live test returned the verified
synthetic paraphrase at 0.2717; the old local 0.45 cutoff rejected it repeatedly.
V3 fused relevance scores must not be treated as cosine similarity.
Search must return an object containing a `results` list.
See the [search contract](https://docs.mem0.ai/api-reference/memory/search-memories).

Hosted exact listings have returned `source_ticket_ids` as a string and
`evidence` as a list despite receiving a list and dictionary. The adapter does
not guess their serialization. For a scoped semantic candidate with changed
provenance types, it reads the original PostgreSQL payload using the exact
finding fingerprint, project, owner, and environment. Queued (undispatched)
entries are excluded. It verifies the original fingerprint and exact provider
text before supplying canonical ticket IDs, evidence, and timestamps.
Mismatched ownership/content, missing provenance, invalid timestamps, or an
expired provider/ledger record fail closed. Ledger failures degrade to normal
sprint answers. This lookup is read-only, never retries ingestion, and never
creates context from a ledger row without a real provider search candidate.

`SemanticMemory.last_recall_diagnostics` resets for each request and contains
only result/acceptance counts and fixed rejection reasons. It does not retain
queries, bodies, private capabilities, or scope identifiers. SQLite conversation
recall remains separate. Existing LangGraph recall/context injection and fresh
sprint-data precedence are preserved.

### Readiness and duplicate prevention

No durable production backend was enabled in this change. The availability probe
found reachable development PostgreSQL but **no production database**, no mem0
integration connection and no configured mem0 API key. A database variable alone
is not proof of production availability.

The optional PostgreSQL outbox/ingestion ledger is separate from checkpoints.
Its unique fingerprint constraint prevents repeat submissions, including
concurrent requests. All findings are queued durably; at most three are dispatched
per turn, and subsequent successful turns drain remaining queued observations.
Atomic, scope-filtered `FOR UPDATE SKIP LOCKED` claims commit before remote calls.

Hosted V3 adds can be asynchronous (`PENDING` with an event ID) or synchronous
with `infer=False` (a nonempty `results` array). With this app's one-message
payload, the adapter accepts exactly one `ADD` result with a nonempty ID and
`data.memory` matching the submitted summary; status must be absent or
`SUCCEEDED`. Unknown/contradictory shapes are quarantined, not assumed successful.
See the [provider response contract](https://docs.mem0.ai/api-reference/memory/add-memories).
The SDK is pinned to `mem0ai==2.2.1` and passes the response JSON through unchanged.

The existing ledger `pending` state means accepted, awaiting reconciliation, **not**
verified semantic-search visibility. For synchronous acknowledgments its event ID
is null; a memory ID is never stored as a polling event ID. Finalization only
updates a reserved row, so uncertain commit acknowledgments cannot erase an
already-recorded pending event. No schema migration was required.
A provider timeout or process exit after claim
leaves `unknown`/`reserved` work quarantined: it is never blindly resubmitted.
An operator must reconcile the provider event/fingerprint before any deliberate
retry. This trades automatic retry of uncertain writes for duplicate prevention;
it does not assert exactly-once delivery inside an external provider.

Missing SDK/configuration/table, unavailable database, search failures and write
failures do not block sprint answers or clear checkpoint history. The adapter
uses three-second HTTP timeouts, no HTTP transport retries and bounded dispatch.
Diagnostics expose only stage/status, never keys, connection strings, user
questions or raw provider exceptions. Programmatic results contain
`semantic_memory_status`; the UI remains unchanged.

### Enabling later, after services are available

1. Approve/configure a hosted mem0 account and a durable PostgreSQL ledger.
   Use the workspace secrets flow for credentials; never put real values in
   `.env.example`, code, chat or logs.
2. Install optional dependencies:
   ```bash
   uv sync --frozen --extra semantic-memory
   # Or, after the normal local setup:
   python -m pip install -r local/semantic-memory-requirements.txt
   ```
3. Review `data/schema/semantic_memory_ledger.sql` and apply it through the
   **approved development schema workflow only**. It is not executed automatically.
   For Replit-managed PostgreSQL, Publish manages the production schema diff.
   Do not run custom production DDL or startup/build-time migrations.
4. Configure `MEM0_ENABLED=true`, a unique `MEM0_PROJECT_ID`, explicit
   `MEM0_ENVIRONMENT=development` or `production`, `MEM0_TELEMETRY=false`, and
   `MEM0_API_KEY`. The ledger uses `MEM0_LEDGER_DATABASE_URL` when supplied,
   otherwise the runtime `DATABASE_URL`. Verify the actual target environment.
5. The validated artifact build now installs the existing locked optional extra:
   `uv sync --frozen --no-dev --extra semantic-memory`. Installing dependencies
   does **not** enable mem0. The running published revision is unchanged until a
   separately approved publish; no backend is provisioned by the build.
6. Namespace configuration must match the actual runtime. Published execution
   (`REPLIT_DEPLOYMENT=1`) requires `MEM0_ENVIRONMENT=production`; editor and local
   execution require `development`. A mismatch fails closed before constructing
   either backend and does not adopt the wrong checkpoint memory namespace.
   Do not use `REPLIT_ENVIRONMENT` to identify the editor. Even if the same project
   ID/private capability is supplied in both environments, owner hashes, finding
   fingerprints and ledger operations include the environment. Use distinct
   production credentials/database targets as well; application-level scoping is
   not a substitute for authenticated tenant accounts or database access control.

No approved production ledger database is currently available. Do not run
startup/build-time DDL, point production at the test database, or enable the flag.
See [the readiness assessment](docs/mem0-production-readiness.md) for remaining
storage, security, verification and exact cleanup requirements.

This does **not** make the existing local SQLite checkpoints production-durable.
Semantic-store durability, event completion and real production restart/redeploy
survival require separate live verification.

### Tests

```bash
uv run --frozen pytest -q
```

Default tests use synthetic provider responses and an atomic test outbox,
including semantic-query forwarding, creation, scoping, duplicate prevention,
stale findings and recovery. They do not claim to verify real mem0 embeddings.
`tests/test_semantic_live.py` is a separate opt-in test, skipped by default.
The development validator uses a **separate** `MEM0_TEST_API_KEY` secret and the
development `DATABASE_URL`. It generates an isolated namespace ending `_test`;
it does not set the running app's `MEM0_ENABLED` or use its production key.
After explicit approval and development-ledger setup, run:

```bash
uv run --frozen --extra semantic-memory python -m scripts.validate_mem0_sandbox --live
```

It bounds the run to one synthetic add and twelve semantic searches, uses real
sprint tools and the existing LLM for the fresh-evidence check, simulates an
outage separately, and attempts exact-ID remote cleanup plus scope-filtered
ledger cleanup. Extra graph-generated memory writes are suppressed in the test
process only. Uncertain ingestion is retained for reconciliation, not retried.
Safe results are written under ignored `.local/validation/`. The validator refuses
published execution using `REPLIT_DEPLOYMENT` and requires an editor dev domain.

Alternatively, explicitly opt in with `SPRINTPULSE_RUN_MEM0_LIVE_TESTS=true` for
`tests/test_semantic_live.py`; the default regression suite skips remote calls.

### Controlled development result

An approved live development run authenticated successfully and created one
synthetic remote memory, but the adapter reported `unavailable`. The exact memory
was found, deleted, and verified absent; its test ledger row was removed. The
run stopped before semantic-search/isolation/LLM/outage validation. This is a
**PARTIAL** result, not production readiness. Investigation confirmed that the
old adapter accepted only asynchronous acknowledgments even though `infer=False`
has a documented synchronous result contract. The adapter now accepts that
strictly validated contract as well. The original response was not retained,
so this is a verified compatibility defect, not conclusive proof of the exact
original failure; ledger-finalization failure remains another possible cause.

The validator now captures allowlisted field types (not values), bounded result
structure, and sanitized ledger-finalization outcomes to distinguish these cases.
The subsequent separately approved one-write run verified live synchronous
acknowledgment, PostgreSQL finalization, deduplication, and exact retrieval, but
failed the paraphrased semantic match. The record was then deleted under separate
approval and exact scoped absence was verified. Its pending ledger row was
intentionally retained; it prevents resubmission and is not proof of remote
storage. A later read-only reconciliation confirmed zero exact and semantic
matches for that deleted finding. No polling was needed for an intentionally
deleted record, and no new memories were written.

Another separately approved one-record test confirmed a concrete relevance-cutoff
defect: the provider returned the verified paraphrase at 0.2717, repeatedly
rejected by the local 0.45 cutoff. The adapter now uses the documented V3 default
of 0.1, with unchanged ownership/provenance checks. Live read-only continuation
verified positive paraphrase retrieval, project/conversation negative checks,
and recovery. Search returned structured ticket IDs/evidence directly; the
previously observed get-all transformations were not the blocker in this run.

A real LangGraph/tools/LLM check incorporated a snapshot of that verified live
finding and correctly separated current 66.7% completion from historical 10%.
This is **PARTIAL end-to-end evidence**: the original private capability was
intentionally not persisted when the first test process ended, so the continuation
replayed verified evidence in a temporary graph rather than demonstrating positive
private-key recall and generation in one uninterrupted request.

The combined run used exactly one add, twelve searches, and one LLM call, with
zero deletions. The remote record and its ledger row remain for diagnostics;
cleanup needs explicit approval. Sanitized evidence is in ignored files
`.local/validation/mem0-retrieval-live-result.json` and
`.local/validation/mem0-retrieval-resume-result.json`.
The reusable `scripts/validate_mem0_retrieval.py --live` runner retains its record,
enforces a ninety-second provider-call deadline and twelve-search/one-add limits,
suppresses graph writes, and uses temporary checkpoints. **Every invocation
creates a new synthetic record and requires separate approval.** Do not rerun it
to diagnose an existing record.
Production mem0 remains disabled. Unknown/reserved rows still require exact
provider-event/fingerprint reconciliation before a deliberate retry; this change
does not automatically retry or requeue them.
