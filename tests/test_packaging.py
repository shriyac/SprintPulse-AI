from pathlib import Path
import tomllib

from packaging.requirements import Requirement

ROOT = Path(__file__).parents[1]


def test_local_requirements_and_uv_manifest_have_the_same_dependencies():
    manifest = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project_requirements = list(manifest["project"]["dependencies"])
    project_requirements.extend(manifest["dependency-groups"]["dev"])
    local_requirements = [
        line.strip()
        for line in (ROOT / "local" / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert {Requirement(value).name for value in project_requirements} == {
        Requirement(value).name for value in local_requirements
    }


def test_root_requirements_cannot_trigger_system_pip_during_publish():
    # The publish dependency detector sees root manifests before .replitignore
    # filters the image. Keep local pip instructions without selecting pip there.
    assert not (ROOT / "requirements.txt").exists()
    assert (ROOT / "local" / "requirements.txt").is_file()
    assert (ROOT / "uv.lock").is_file()


def test_published_root_service_runs_streamlit_with_a_health_probe():
    path = ROOT / "artifacts" / "sprintpulse-ai" / ".replit-artifact" / "artifact.toml"
    artifact = tomllib.loads(path.read_text(encoding="utf-8"))
    assert artifact["previewPath"] == "/"
    service = artifact["services"][0]
    assert "/" in service["paths"]
    assert service["production"]["build"]["args"] == [
        "uv", "sync", "--frozen", "--no-dev", "--extra", "semantic-memory",
    ]
    assert "streamlit run app.py" in " ".join(service["production"]["run"]["args"])
    assert "--server.address 0.0.0.0" in " ".join(service["production"]["run"]["args"])
    assert "--server.port $PORT" in " ".join(service["production"]["run"]["args"])
    assert int(service["production"]["run"]["env"]["PORT"]) == service["localPort"]
    assert service["production"]["health"]["startup"]["path"] == "/_stcore/health"


def test_built_python_environment_is_included_in_the_publish_image():
    exclusions = {
        line.strip().rstrip("/")
        for line in (ROOT / ".replitignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    assert not {".pythonlibs", ".venv"} & exclusions
    git_ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".pythonlibs/" in git_ignore
    assert ".venv/" in git_ignore


def test_only_streamlit_has_a_production_web_service():
    production_services = []
    for path in (ROOT / "artifacts").glob("*/.replit-artifact/artifact.toml"):
        artifact = tomllib.loads(path.read_text(encoding="utf-8"))
        production_services.extend(
            (artifact["title"], service["localPort"])
            for service in artifact.get("services", [])
            if "production" in service
        )
    assert production_services == [("SprintPulse AI", 20155)]
