"""Check the exact configured production command in a fresh, secret-free UV environment.

Stop the preview first: this deliberately uses the configured production port.
No application files, reports, or databases are changed in the workspace.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import tempfile
import time
import tomllib
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    manifest = ROOT / "artifacts/sprintpulse-ai/.replit-artifact/artifact.toml"
    service = tomllib.loads(manifest.read_text())["services"][0]
    production = service["production"]
    port = int(production["run"]["env"]["PORT"])
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        probe.bind(("0.0.0.0", port))  # Fail explicitly instead of testing another server.

    with tempfile.TemporaryDirectory(prefix="sprintpulse-production-") as directory:
        clean = Path(directory)
        for name in ("app.py", "pyproject.toml", "uv.lock"):
            shutil.copy2(ROOT / name, clean / name)
        for name in ("agents", "tools", "reports"):
            (clean / name).mkdir()
            for source in (ROOT / name).glob("*.py"):
                shutil.copy2(source, clean / name / source.name)
        (clean / "data").mkdir()
        for source in (ROOT / "data").glob("sprint_*.csv"):
            shutil.copy2(source, clean / "data" / source.name)
        (clean / "home").mkdir()

        binaries = [shutil.which(name) for name in ("uv", "bash", "python3")]
        if not all(binaries):
            raise RuntimeError("uv, bash, and Python 3 must be installed.")
        path = os.pathsep.join(dict.fromkeys(
            [str(Path(binary).resolve().parent) for binary in binaries] + ["/usr/bin", "/bin"]
        ))
        env = {
            "PATH": path,
            "HOME": str(clean / "home"),
            "UV_PROJECT_ENVIRONMENT": ".pythonlibs",
            "UV_PYTHON_DOWNLOADS": "never",
            "PYTHONNOUSERSITE": "1",
            "LANG": "C.UTF-8",
            "REPLIT_DEPLOYMENT": "1",
            "MEM0_ENABLED": "false",
            "MEM0_TELEMETRY": "false",
            **production["run"].get("env", {}),
        }
        print("Building a fresh locked environment, without development packages or secrets.", flush=True)
        subprocess.run(production["build"]["args"], cwd=clean, env=env, check=True, timeout=180)
        smoke = """
import sys
from importlib.metadata import version
from pathlib import Path
import streamlit, pandas, dotenv, langgraph, langchain_openai
import mem0, psycopg
from langgraph.checkpoint.sqlite import SqliteSaver
from agents.semantic_memory import configured_semantic_memory
from tools.sprint_data import load_sprint_data
from streamlit.testing.v1 import AppTest
assert Path(sys.prefix).resolve() == Path('.pythonlibs').resolve()
assert version('mem0ai') == '2.2.1'
assert configured_semantic_memory().status == 'disabled'
snapshots = load_sprint_data(Path('data'))
assert len(snapshots) == 3
assert all(len(frame) == 24 for frame in snapshots.values())
app = AppTest.from_file('app.py').run(timeout=30)
assert not app.exception, [str(item.value) for item in app.exception]
assert [item.label for item in app.tabs] == ['Sprint Dashboard', 'AI Assistant', 'Weekly Reports']
print('Clean core/mem0/PostgreSQL imports, disabled memory, CSV loading and all three tabs: PASS')
"""
        subprocess.run(
            ["uv", "run", "--frozen", "--no-sync", "python", "-c", smoke],
            cwd=clean, env=env, check=True, timeout=60,
        )
        command = production["run"]["args"]
        print("Exact production command:", command, flush=True)
        with (clean / "startup.log").open("w+") as log:
            process = subprocess.Popen(
                command, cwd=clean, env=env, stdout=log, stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            try:
                deadline = time.monotonic() + 30
                url = f"http://127.0.0.1:{port}{production['health']['startup']['path']}"
                while True:
                    if process.poll() is not None:
                        raise RuntimeError(f"Production process exited with code {process.returncode}")
                    try:
                        with urlopen(url, timeout=2) as response:
                            if response.status == 200 and response.read().strip() == b"ok":
                                break
                    except OSError:
                        pass
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Production health endpoint did not become ready")
                    time.sleep(0.25)
                # A process that answers once and immediately exits is not healthy.
                for _ in range(10):
                    time.sleep(1)
                    assert process.poll() is None, "Production process stopped after readiness"
                    with urlopen(url, timeout=2) as response:
                        assert response.status == 200
                listeners = Path("/proc/net/tcp").read_text().splitlines()[1:]
                assert any(
                    row.split()[1] == f"00000000:{port:04X}" and row.split()[3] == "0A"
                    for row in listeners
                ), "Server is not listening on the configured IPv4 wildcard address"
                print(f"Production stayed alive; 0.0.0.0:{port}; health HTTP 200 for 10 seconds.")
            finally:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait(timeout=5)
                log.seek(0)
                print(log.read())


if __name__ == "__main__":
    main()
