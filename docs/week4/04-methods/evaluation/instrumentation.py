"""Evaluation-only observers and redaction. Never register these with Streamlit."""
from __future__ import annotations

from contextlib import ExitStack
from dataclasses import dataclass, field
import hashlib
import re
import threading
import time
from unittest.mock import patch

from langchain_core.callbacks import BaseCallbackHandler

TOOL_NAMES = (
    "sprint_metrics", "overdue_tasks", "risk_flags", "blocker_durations",
    "recurring_blockers", "historical_comparison",
)
NODE_NAMES = {
    "recall_conversation", "route_request", "retrieve_sprint_data", "detect_risk",
    "compare_sprint_history", "gather_report_evidence", "retrieve_question_context",
    "remember_findings", "answer", "report",
}


def redact(value):
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if key.lower() in {
                "api_key", "password", "authorization", "thread_id", "owner_scope",
            } else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    if isinstance(value, str):
        value = re.sub(
            r"(?:sk-[\w-]{20,}|gh[pousr]_[\w]{20,}|github_pat_[\w]{20,}|"
            r"\bsp_[A-Za-z0-9_-]{43}\b|eyJ[\w-]{15,}\.[\w-]{15,}\.[\w-]{15,})",
            "[REDACTED]", value,
        )
        return re.sub(r"(https?://|postgres(?:ql)?://)[^\s/@]+:[^\s/@]+@", r"\1[REDACTED]@", value)
    return value


@dataclass
class Capture:
    phase: str = "evaluation"
    nodes: list = field(default_factory=list)
    tools: list = field(default_factory=list)
    model_calls: list = field(default_factory=list)
    fail_overdue: bool = False
    llm_outage: bool = False
    lock: threading.RLock = field(default_factory=threading.RLock)
    local: threading.local = field(default_factory=threading.local)

    def wrap_tool(self, name, original):
        def observed(*args, **kwargs):
            started = time.perf_counter()
            stack = getattr(self.local, "stack", [])
            with self.lock:
                entry = {
                    "call_id": len(self.tools), "parent_call_id": stack[-1] if stack else None,
                    "tool": name, "phase": self.phase, "status": "started",
                    "latency_ms": None,
                }
                self.tools.append(entry)
            self.local.stack = [*stack, entry["call_id"]]
            try:
                if name == "overdue_tasks" and self.fail_overdue:
                    self.fail_overdue = False
                    raise RuntimeError("Controlled evaluation tool outage")
                result = original(*args, **kwargs)
                entry.update(status="ok", output=redact(result))
                return result
            except Exception as exc:
                entry.update(status="error", exception_type=type(exc).__name__)
                raise
            finally:
                entry["latency_ms"] = round((time.perf_counter() - started) * 1000, 3)
                self.local.stack = stack
        return observed


class NodeObserver(BaseCallbackHandler):
    """Capture actual LangGraph node callbacks, not inferred route labels."""
    raise_error = True

    def __init__(self, capture):
        self.capture = capture

    def on_chain_start(self, serialized, inputs, *, run_id, name=None, metadata=None, **kwargs):
        if name in NODE_NAMES and (metadata or {}).get("langgraph_node") == name:
            with self.capture.lock:
                self.capture.nodes.append({"node": name, "phase": self.capture.phase})


class ObservedGraph:
    def __init__(self, compiled, observer):
        self.compiled, self.observer = compiled, observer

    def invoke(self, state, config=None, **kwargs):
        config = dict(config or {})
        config["callbacks"] = [*(config.get("callbacks") or []), self.observer]
        return self.compiled.invoke(state, config=config, **kwargs)


def instrument(stack: ExitStack, capture: Capture, mode: str):
    """Patch only this isolated CLI process; restore all originals on exit."""
    from agents import graph
    from tools import sprint_metrics as metrics

    observer = NodeObserver(capture)
    original_build = graph.build_sprint_graph
    original_generate = graph.generate_grounded_text
    originals = {name: getattr(metrics, name) for name in TOOL_NAMES}
    for name, original in originals.items():
        wrapper = capture.wrap_tool(name, original)
        # Both aliases are needed: risk_flags and historical_comparison also
        # call sprint_metrics internally. Parent IDs distinguish those calls.
        stack.enter_context(patch.object(metrics, name, wrapper))
        stack.enter_context(patch.object(graph, name, wrapper))

    def build(*args, **kwargs):
        return ObservedGraph(original_build(*args, **kwargs), observer)

    def generate(task, facts):
        call = {
            "phase": capture.phase, "evidence": redact(facts),
            "task_sha256": hashlib.sha256(task.encode()).hexdigest(),
            "simulated": mode == "deterministic" or capture.llm_outage,
            "live_llm_executed": False,
        }
        capture.model_calls.append(call)
        if capture.llm_outage:
            call["exception_type"] = "RuntimeError"
            raise RuntimeError("Controlled evaluation LLM outage")
        if mode == "deterministic":
            call["mode"] = "evaluation forced deterministic fallback"
            return None, call["mode"]
        try:
            text, generation_mode = original_generate(task, facts)
            call["mode"] = generation_mode
            call["live_llm_executed"] = generation_mode == "LangChain LLM grounded in tool outputs"
            return text, generation_mode
        except Exception as exc:
            call["exception_type"] = type(exc).__name__
            raise

    stack.enter_context(patch.object(graph, "build_sprint_graph", build))
    stack.enter_context(patch.object(graph, "generate_grounded_text", generate))
