import json
import subprocess
import sys
from pathlib import Path

from services import controlled_provider_evaluation as cpe


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_controlled_provider_evaluation.py"


def _manifest(tmp_path, privacy="SYNTHETIC"):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({
        "evaluation_id": "cli-eval",
        "items": [{
            "evaluation_item_uid": "cli-item-001",
            "course_or_domain": "computer science",
            "english_term": "time complexity",
            "normalized_english_term": "time complexity",
            "bounded_context": "Time complexity describes algorithm growth.",
            "context_source_type": "synthetic_fixture",
            "privacy_classification": privacy,
        }],
    }), encoding="utf-8")
    return path


def test_cli_dry_run_writes_sanitized_artifact_without_external_requests(tmp_path):
    output = tmp_path / "out.json"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--manifest", str(_manifest(tmp_path)), "--json-output", str(output), "--dry-run"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["dry_run"] is True
    assert data["actual_external_provider_requests"] == 0
    assert data["private_course_provider_requests"] == 0
    assert data["status_counts"]["SUCCEEDED"] == 1


def test_service_live_without_target_fails_closed_before_network():
    item = cpe.build_evaluation_input({
        "evaluation_item_uid": "cli-stop-item-001",
        "course_or_domain": "computer science",
        "english_term": "time complexity",
        "normalized_english_term": "time complexity",
        "bounded_context": "Time complexity describes algorithm growth.",
        "context_source_type": "synthetic_fixture",
        "privacy_classification": "SYNTHETIC",
    })
    run = cpe.run_controlled_provider_evaluation(
        [item],
        provider_name="unconfigured-provider",
        model_name="missing-model",
        credential_loader=cpe.StaticCredentialLoader("runtime-only-test-value"),
        pricing=cpe.test_pricing_config(),
        budget=cpe.test_budget_config(),
        transport=cpe.CountingTransport(),
        execute_live=True,
    )

    assert run.stop_code == "REAL_PROVIDER_TARGET_NOT_CONFIGURED"
    assert run.actual_external_provider_requests == 0
    assert run.results[0].status == "PROVIDER_REJECTED"


def test_cli_without_execute_flag_defaults_to_dry_run(tmp_path):
    output = tmp_path / "blocked.json"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--manifest",
            str(_manifest(tmp_path)),
            "--json-output",
            str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["dry_run"] is True
    assert data["actual_external_provider_requests"] == 0


def test_cli_blocks_private_manifest_in_dry_run_without_sending(tmp_path):
    output = tmp_path / "private.json"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--manifest", str(_manifest(tmp_path, "LOCAL_ONLY_PRIVATE")), "--json-output", str(output), "--dry-run"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["status_counts"]["PRIVACY_BLOCKED"] == 1
    assert data["private_course_provider_requests"] == 0
