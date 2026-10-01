from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _load(relative_path: str, name: str):
    path = ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_runtime_venv_defaults_outside_desktop_repository():
    runtime = _load("scripts/runtime_environment.py", "runtime_environment_14a_default")

    path = runtime.default_runtime_venv(
        environ={},
        platform_name="darwin",
        home=Path("/pilot-home"),
    )

    assert path == Path("/pilot-home/Library/Application Support/LexiBridge-AI/runtime")
    assert "Desktop" not in path.parts


def test_runtime_interpreter_selection_prefers_explicit_then_external_venv(tmp_path):
    runtime = _load("scripts/runtime_environment.py", "runtime_environment_14a_selection")
    explicit = tmp_path / "explicit-python"
    external = tmp_path / "external" / "bin" / "python"
    repository = tmp_path / "repo" / "backend" / ".venv" / "bin" / "python"
    for candidate in (explicit, external, repository):
        candidate.parent.mkdir(parents=True, exist_ok=True)
        candidate.write_text("", encoding="utf-8")

    candidates = runtime.candidate_interpreters(
        root=tmp_path / "repo",
        environ={
            "LEXIBRIDGE_PYTHON": str(explicit),
            "LEXIBRIDGE_RUNTIME_VENV": str(external.parents[1]),
        },
        platform_name="darwin",
        home=tmp_path,
        current_python="/usr/bin/python3",
    )
    assert candidates[:3] == [explicit, external, repository]

    selected, diagnostics = runtime.select_interpreter(
        candidates,
        probe=lambda path: (path == external, "healthy" if path == external else "unhealthy"),
    )
    assert selected == external
    assert diagnostics[0]["healthy"] is False
    assert diagnostics[1]["healthy"] is True
    assert all("credential" not in item for item in diagnostics)


def test_runtime_requirements_are_exactly_pinned_and_split_by_purpose():
    base = (ROOT / "backend" / "requirements.txt").read_text(encoding="utf-8")
    assert "-r requirements-runtime.lock.txt" in base
    assert "-r requirements-dev.lock.txt" in base

    for relative_path in (
        "backend/requirements-runtime.lock.txt",
        "backend/requirements-dev.lock.txt",
        "requirements-e2e.txt",
    ):
        lines = (ROOT / relative_path).read_text(encoding="utf-8").splitlines()
        requirements = [
            line.strip()
            for line in lines
            if line.strip() and not line.lstrip().startswith(("#", "-r"))
        ]
        assert requirements
        assert all("==" in line for line in requirements), (relative_path, requirements)

    runtime_lock = (ROOT / "backend" / "requirements-runtime.lock.txt").read_text(
        encoding="utf-8"
    )
    assert "gunicorn==" in runtime_lock.lower()


def test_backend_launcher_defaults_to_wsgi_and_requires_explicit_development_mode():
    launcher = (ROOT / "scripts" / "run_backend.sh").read_text(encoding="utf-8")

    assert 'LEXIBRIDGE_SERVER_MODE:-pilot' in launcher
    assert "-m gunicorn" in launcher
    assert "wsgi:application" in launcher
    assert "--access-logformat" in launcher
    assert "%(U)s" in launcher
    assert "%(q)s" not in launcher
    assert "x-request-id" not in launcher
    assert '"$PYTHON_BIN" backend/app.py' in launcher
    assert 'if [ "$SERVER_MODE" = "development" ]' in launcher
    assert 'EFFECTIVE_DATABASE_URL="${DATABASE_URL:-sqlite:}"' in launcher
    assert launcher.index("SQLite controlled-pilot runtime requires") < launcher.index(
        'scripts/migrate_db.py --apply'
    )

    completed = subprocess.run(
        ["bash", "-n", "scripts/run_backend.sh"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_wsgi_entrypoint_reuses_existing_application_without_starting_dev_server():
    source = (ROOT / "backend" / "wsgi.py").read_text(encoding="utf-8")
    assert "from app import app as application" in source
    assert "app.run" not in source
    assert "db.create_all" not in source
    assert "seed_demo" not in source


def test_runtime_probe_rejects_external_targets_and_emits_payload_free_record(tmp_path):
    probe = _load("scripts/collect_runtime_probe.py", "runtime_probe_14a")

    assert probe.validate_local_endpoint("http://127.0.0.1:5000/api/test").path == "/api/test"
    try:
        probe.validate_local_endpoint("https://example.com/api/test")
    except ValueError as exc:
        assert "loopback" in str(exc).lower()
    else:
        raise AssertionError("external observation target was accepted")
    with pytest.raises(ValueError, match="IP literal"):
        probe.validate_local_endpoint("http://localhost:5000/api/test")
    with pytest.raises(ValueError, match="target label"):
        probe.build_record(
            target_label="student@example.test",
            endpoint_path="/api/test",
            status_code=200,
            latency_ms=1,
            outcome="healthy",
            error_code="",
            observed_at="2026-08-17T00:00:00Z",
        )

    record = probe.build_record(
        target_label="pilot-local",
        endpoint_path="/api/test",
        status_code=200,
        latency_ms=12.5,
        outcome="healthy",
        error_code="",
        observed_at="2026-08-17T00:00:00Z",
    )
    rendered = json.dumps(record, sort_keys=True)
    assert record["endpoint_path"] == "/api/test"
    assert "request_body" not in rendered
    assert "response_body" not in rendered
    assert "authorization" not in rendered.lower()
    assert "credential" not in rendered.lower()


def test_runtime_observation_report_remains_pending_until_real_window_is_complete(tmp_path):
    report = _load("scripts/runtime_observation_report.py", "runtime_observation_report_14a")
    records = [
        {
            "schema_version": "runtime-probe-v1",
            "observed_at": "2026-08-17T00:00:00Z",
            "target_label": "pilot-local",
            "endpoint_path": "/api/test",
            "outcome": "healthy",
            "status_code": 200,
            "latency_ms": 5.0,
            "error_code": "",
        }
    ]

    pending = report.summarize_records(
        records,
        window_start="2026-08-17T00:00:00Z",
        window_end="2026-08-18T00:00:00Z",
        minimum_days=14,
        minimum_active_days=5,
    )
    assert pending["status"] == "RUNTIME_OBSERVATION_PENDING"
    assert pending["gates"]["minimum_duration_met"] is False
    assert pending["gates"]["minimum_active_days_met"] is False
    assert pending["metrics"]["healthy_samples"] == 1

    completed_records = []
    for day in range(1, 16):
        completed_records.append(
            {
                **records[0],
                "observed_at": f"2026-08-{day:02d}T12:00:00Z",
            }
        )
    complete = report.summarize_records(
        completed_records,
        window_start="2026-08-01T00:00:00Z",
        window_end="2026-08-16T00:00:00Z",
        minimum_days=14,
        minimum_active_days=5,
        evaluated_at="2026-08-17T00:00:00Z",
    )
    assert complete["status"] == "RUNTIME_OBSERVATION_COMPLETE"
    assert all(complete["gates"].values())


def test_runtime_observation_excludes_out_of_window_samples_and_future_window():
    report = _load("scripts/runtime_observation_report.py", "runtime_observation_report_14a_bounds")
    records = [
        {
            "schema_version": "runtime-probe-v1",
            "observed_at": f"2026-07-{day:02d}T12:00:00Z",
            "target_label": "pilot-local",
            "endpoint_path": "/api/test",
            "outcome": "healthy",
            "status_code": 200,
            "latency_ms": 5.0,
            "error_code": "",
        }
        for day in range(1, 16)
    ]

    bounded = report.summarize_records(
        records,
        window_start="2026-08-01T00:00:00Z",
        window_end="2026-08-16T00:00:00Z",
        minimum_days=14,
        minimum_active_days=5,
        evaluated_at="2026-08-17T00:00:00Z",
    )
    assert bounded["status"] == "RUNTIME_OBSERVATION_PENDING"
    assert bounded["metrics"]["sample_count"] == 0

    future = report.summarize_records(
        [
            {
                **records[0],
                "observed_at": f"2026-08-{day:02d}T12:00:00Z",
            }
            for day in range(1, 16)
        ],
        window_start="2026-08-01T00:00:00Z",
        window_end="2026-08-16T00:00:00Z",
        minimum_days=14,
        minimum_active_days=5,
        evaluated_at="2026-08-15T23:59:59Z",
    )
    assert future["status"] == "RUNTIME_OBSERVATION_PENDING"
    assert future["gates"]["window_elapsed"] is False


def test_bootstrap_uses_external_runtime_lock_and_never_activates_legacy_venv():
    source = (ROOT / "scripts" / "bootstrap_runtime.sh").read_text(encoding="utf-8")
    assert "requirements-runtime.lock.txt" in source
    assert "requirements-dev.lock.txt" in source
    assert "backend/.venv-macos/bin/activate" not in source
    assert "LEXIBRIDGE_RUNTIME_VENV" in source
    assert "LEXIBRIDGE_PIP_CERT" in source
    assert "/etc/ssl/cert.pem" in source
    assert "--trusted-host" not in source

    completed = subprocess.run(
        ["bash", "-n", "scripts/bootstrap_runtime.sh"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_operator_docs_use_canonical_runtime_and_explicit_migration_apply():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    runbook = (ROOT / "docs" / "pilot_runbook.md").read_text(encoding="utf-8")

    for text in (readme, runbook):
        assert "bash scripts/bootstrap_runtime.sh" in text
        assert "scripts/migrate_db.py --apply" in text
        assert "bash scripts/run_backend.sh" in text
        assert "bash scripts/run_worker.sh" in text
    assert "Gunicorn" in readme
    assert "RUNTIME_OBSERVATION_PENDING" in runbook


def test_browser_bootstrap_uses_exact_e2e_lock_and_verified_tls():
    source = (ROOT / "scripts" / "bootstrap_e2e.sh").read_text(encoding="utf-8")
    assert "requirements-e2e.txt" in source
    assert "LEXIBRIDGE_PIP_CERT" in source
    assert "/etc/ssl/cert.pem" in source
    assert "playwright install chromium" in source
    assert "--trusted-host" not in source

    completed = subprocess.run(
        ["bash", "-n", "scripts/bootstrap_e2e.sh"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
