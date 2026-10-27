from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from agents.graph import invoke_sprint_graph, restore_conversation
from agents.memory import new_conversation_key
from reports.publisher import save_approved_report
from tools.sprint_data import available_sprints, load_sprint_data
from tools.sprint_metrics import risk_flags, sprint_metrics

load_dotenv()
ROOT = Path(__file__).parent

st.set_page_config(page_title="SprintPulse AI", page_icon="SP", layout="wide")


@st.cache_data
def get_sprints() -> dict[str, pd.DataFrame]:
    return load_sprint_data(ROOT / "data")


def get_thread_id() -> str:
    if "thread_id" not in st.session_state:
        st.session_state.thread_id = new_conversation_key()
    return st.session_state.thread_id


try:
    sprints = get_sprints()
except (FileNotFoundError, ValueError) as exc:
    st.error(f"Could not load the sample sprint snapshots: {exc}")
    st.stop()

ordered_sprints = available_sprints(sprints)
latest_name = ordered_sprints[-1]

st.title("SprintPulse AI")
st.caption("A grounded sprint intelligence workspace · Synthetic Jira-style sample data")

with st.sidebar:
    st.subheader("Conversation")
    st.caption(
        "Save your private key to resume after a refresh or in a new session. "
        "Anyone with the key can access this conversation. Keep it private."
    )
    st.text_input("Current private key", value=get_thread_id(), type="password", disabled=True)
    st.download_button(
        "Download resume key", data=get_thread_id(),
        file_name="sprintpulse-conversation-key.txt", mime="text/plain",
    )
    st.caption(
        "Switching conversations clears unsaved report drafts, not saved history. "
        "Local storage is not guaranteed to survive production restarts or republishing."
    )
    with st.form("resume_conversation"):
        resume_key = st.text_input("Private resume key", type="password")
        resume_submitted = st.form_submit_button("Resume conversation")
    if resume_submitted:
        try:
            restored = restore_conversation(resume_key.strip())
        except ValueError as exc:
            st.error(str(exc))
        else:
            st.session_state.thread_id = resume_key.strip()
            st.session_state.last_answer = restored
            st.session_state.conversation_restored = True
            # Keep restoration separate from widget state across the early rerun.
            st.session_state.restored_sprint = restored["sprint_name"]
            st.session_state.pop("assistant_question", None)
            st.session_state.pending_report = None
            st.session_state.approved_report = None
            st.rerun()
    if st.button("New conversation"):
        st.session_state.thread_id = new_conversation_key()
        for name in (
            "last_answer", "pending_report", "approved_report", "conversation_restored",
            "assistant_question", "restored_sprint",
        ):
            st.session_state.pop(name, None)
        st.rerun()

dashboard_tab, assistant_tab, reports_tab = st.tabs(
    ["Sprint Dashboard", "AI Assistant", "Weekly Reports"]
)

with dashboard_tab:
    selected_name = st.selectbox(
        "Sprint snapshot",
        options=ordered_sprints,
        index=len(ordered_sprints) - 1,
        key="dashboard_sprint",
    )
    selected_df = sprints[selected_name]
    metrics = sprint_metrics(selected_df)

    metric_columns = st.columns(4)
    metric_columns[0].metric("Completion", f"{metrics['completion_rate']:.1f}%")
    metric_columns[1].metric("Completed", f"{metrics['done_count']} / {metrics['total_tickets']}")
    metric_columns[2].metric("Open blockers", metrics["blocked_count"])
    metric_columns[3].metric("Overdue", metrics["overdue_count"])

    st.subheader("Completion across snapshots")
    trend = pd.DataFrame(
        [
            {
                "Sprint": name,
                "Completion rate (%)": sprint_metrics(sprints[name])["completion_rate"],
            }
            for name in ordered_sprints
        ]
    ).set_index("Sprint")
    st.bar_chart(trend, y="Completion rate (%)", color="#4477aa")

    left, right = st.columns([1, 1])
    with left:
        st.subheader("Risk flags")
        risks = risk_flags(selected_df)
        if risks:
            for risk in risks:
                st.warning(f"**{risk['level']} · {risk['category']}** — {risk['detail']}")
        else:
            st.success("No risk flags triggered by the configured deterministic rules.")
    with right:
        st.subheader("Sprint scope")
        st.write(
            f"**{metrics['sprint_name']}** · {metrics['sprint_start']} to {metrics['sprint_end']}"
        )
        st.write(
            f"{metrics['story_points_completed']} of {metrics['story_points_scope']} story points completed."
        )
        st.caption("Risk rules: any open blocker, any overdue open ticket, or completion below 70%.")

    st.subheader("Tickets")
    visible_columns = [
        "ticket_id",
        "summary",
        "assignee",
        "status",
        "priority",
        "story_points",
        "due_date",
        "is_blocker",
    ]
    st.dataframe(
        selected_df[visible_columns].rename(
            columns={
                "ticket_id": "Ticket",
                "summary": "Summary",
                "assignee": "Assignee",
                "status": "Status",
                "priority": "Priority",
                "story_points": "Points",
                "due_date": "Due",
                "is_blocker": "Blocker",
            }
        ),
        width="stretch",
        hide_index=True,
    )

with assistant_tab:
    if "restored_sprint" in st.session_state:
        restored_sprint = st.session_state.pop("restored_sprint")
        st.session_state.assistant_sprint = (
            restored_sprint if restored_sprint in ordered_sprints else latest_name
        )
    if "assistant_sprint" not in st.session_state:
        st.session_state.assistant_sprint = latest_name
    if st.session_state.get("conversation_restored"):
        st.info("Restored the last successful answer. It is historical; ask again for fresh metrics.")
    st.subheader("Ask about the sprint history")
    st.caption(
        "Answers are grounded in deterministic sprint tools. If an LLM is configured, "
        "it can only use those tool results."
    )
    with st.form("assistant_form"):
        assistant_sprint = st.selectbox(
            "Sprint context",
            ordered_sprints,
            index=None,
            key="assistant_sprint",
        )
        question = st.text_input(
            "Your question",
            placeholder="What changed in blockers over the last three sprints?",
            key="assistant_question",
        )
        submitted = st.form_submit_button("Ask SprintPulse", type="primary")

    if submitted:
        if not question.strip():
            st.warning("Enter a question first.")
        else:
            with st.spinner("Gathering sprint facts and preparing a grounded answer…"):
                result = invoke_sprint_graph(
                    question=question.strip(),
                    sprint_name=assistant_sprint,
                    sprints=sprints,
                    thread_id=get_thread_id(),
                )
            st.session_state.last_answer = result
            st.session_state.conversation_restored = False

    if "last_answer" in st.session_state:
        answer = st.session_state.last_answer
        if answer.get("error"):
            st.error(answer["error"])
        else:
            st.markdown(answer.get("response", "No response was returned."))
            st.caption(
                f"Route: {answer.get('route', 'unknown')} · "
                f"Draft source: {answer.get('generation_mode', 'deterministic tools')} · "
                f"Recalled turns: {answer.get('recalled_turns', 0)}"
            )
            if answer.get("errors"):
                st.info("A model request was unavailable; the answer uses deterministic tool output.")
            with st.expander("Inspect tool outputs"):
                st.json(answer.get("tool_outputs", {}))

with reports_tab:
    st.subheader("Weekly sprint report")
    st.write(
        "Generate a report from the selected snapshot and its history. Nothing is saved "
        "or published until you approve it."
    )
    with st.form("report_form"):
        report_sprint = st.selectbox(
            "Report sprint",
            ordered_sprints,
            index=len(ordered_sprints) - 1,
            key="report_sprint",
        )
        report_submitted = st.form_submit_button("Generate draft", type="primary")

    if report_submitted:
        with st.spinner("Building a report from sprint tool outputs…"):
            draft = invoke_sprint_graph(
                question="Write the weekly sprint status report.",
                sprint_name=report_sprint,
                sprints=sprints,
                thread_id=get_thread_id(),
                route_override="report",
            )
        st.session_state.pending_report = draft
        st.session_state.approved_report = None

    pending = st.session_state.get("pending_report")
    if pending:
        st.markdown("### Draft for review")
        st.caption(f"Draft source: {pending.get('generation_mode', 'deterministic tools')}")
        st.markdown(pending.get("report", "No report was returned."))
        if pending.get("errors"):
            st.info("The LLM was unavailable; this draft was assembled from deterministic tool results.")
        approval_col, discard_col = st.columns([1, 5])
        with approval_col:
            if st.button("Approve and save", type="primary"):
                saved_path = save_approved_report(
                    pending["report"],
                    report_sprint=pending.get("sprint_name", report_sprint),
                    reports_dir=ROOT / "reports" / "approved",
                )
                st.session_state.approved_report = {
                    "path": str(saved_path),
                    "content": pending["report"],
                    "sprint_name": pending.get("sprint_name", report_sprint),
                }
                st.session_state.pending_report = None
                st.rerun()
        with discard_col:
            if st.button("Discard draft"):
                st.session_state.pending_report = None
                st.rerun()

    approved = st.session_state.get("approved_report")
    if approved:
        st.success(f"Approved report saved: {Path(approved['path']).name}")
        st.download_button(
            "Download approved report",
            data=approved["content"],
            file_name=Path(approved["path"]).name,
            mime="text/markdown",
        )
