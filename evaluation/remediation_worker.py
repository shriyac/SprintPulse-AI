"""Golden replay worker: isolated imported sources, no network or paid calls."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import socket
import sys
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = args.source.resolve()
    sys.path.insert(0, str(source))
    outbound = []

    def deny_network(*args, **kwargs):
        outbound.append("blocked")
        raise RuntimeError("Network forbidden during post-holdout remediation")

    socket.socket.connect = deny_network
    socket.socket.connect_ex = deny_network
    socket.create_connection = deny_network
    socket.getaddrinfo = deny_network
    from agents import graph, llm
    from evaluation import runner
    assert Path(graph.__file__).resolve().is_relative_to(source)
    dataset = json.loads(args.dataset.read_text())
    case = next(c for c in dataset["cases"] if c["id"] == args.case_id)
    with patch.object(llm, "_client", side_effect=RuntimeError("Live LLM forbidden")):
        row = runner.execute_case(case, dataset, "deterministic")
    assert not outbound
    assert not any(c["live_llm_executed"] for c in row["trace"]["model_calls"])
    row["trace"]["network_attempts_blocked"] = len(outbound)
    args.output.write_text(json.dumps(row, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
