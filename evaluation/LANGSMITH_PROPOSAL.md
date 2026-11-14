# Optional LangSmith proposal — approval required, NOT enabled

## Smallest integration

The existing environment already contains `langsmith==0.14.12` transitively
through LangChain. The current graph and LangChain model support native tracing.
No Streamlit redesign or new agent framework is necessary.

After explicit approval:

1. Check whether a supported Replit integration is available before requesting
   credentials; otherwise use the secure development-secrets flow, never chat.
2. Choose the account/workspace and data region, private project
   `SprintPulse-AI-eval-dev-v1`, retention, sampling, access roles and budget.
3. Set development-only `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT`, the appropriate
   region endpoint if required, and `LANGSMITH_TRACING=true`.
4. Add an **explicitly opt-in evaluation-only** tracing mode. The shipped runner
   intentionally forces tracing OFF; setting an environment flag alone will
   not override that safeguard.
5. Use synthetic cases only. Attach case ID, dataset/application/prompt hashes,
   mode and scenario; redact/omit all thread/configurable data, capabilities,
   credentials, actual ownership metadata and private memories **before upload**.
6. Approve a small synthetic tracing test, validate recorded content/access,
   and establish deletion/retention procedures before a full traced baseline.

Do not enable tracing on the production Streamlit process. Do not upload the
existing checkpoint database, private conversations, mem0 records, local
validation evidence or the whole environment. Local result redaction is not
enough: native tracing can capture inputs/configuration **before** the local
serializer, so a separate pre-upload review/redaction layer is required.
Do not assume hiding just model inputs also hides graph state/tool outputs.

## Costs and privacy

The official pricing page inspected during preparation describes a Developer
allowance of **5,000 base traces/month**; base traces retain data for **14 days**,
extended traces for **180 days**, with paid usage/retention beyond included
allowances. These are provider terms, not a promise about the user's account.
Verify current plan, regional options, overage rates and billing settings
before approval: <https://www.langchain.com/pricing>.

A trace can contain many nested events; do not assume each graph node is a
separate billable root trace or that every evaluation/setup request is free.
LangSmith charges are separate from the application's live LLM token charges.
Local deterministic tests have no hosted tracing/provider-call cost; they still
consume the development workspace's normal compute.

Prompts, generated answers, tool JSON, historical context, metadata and failures
can leave Replit when tracing is enabled. Obtain data-owner approval, restrict
project visibility, avoid public trace links, verify provider handling/retention
and record a deletion policy. Minimize payloads; never rely only on a regex to
guarantee absence of secrets.

## Rollback

Disable the evaluation tracing flag and development tracing settings. Retain
local-only results, revoke the tracing credential if appropriate, and request
exact-scoped provider deletion separately if needed. Disabling tracing does
not retroactively delete remote traces. No setup, tracing upload or account
creation has been performed as part of this phase.
