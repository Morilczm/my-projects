import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "run_controlled_multi_student_pilot_14f.py"


def test_controlled_runner_drives_full_personal_flow_in_external_db(tmp_path):
    output_dir = tmp_path / "artifacts"
    env = os.environ.copy()
    env.update(
        {
            "LEXIBRIDGE_SKIP_ENV_FILE": "true",
            "DEEPSEEK_API_KEY": "",
            "OPENAI_API_KEY": "",
            "ANTHROPIC_API_KEY": "",
        }
    )
    completed = subprocess.run(
        [sys.executable, str(RUNNER), "--personas", "5", "--output-dir", str(output_dir)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )

    result = json.loads(
        (output_dir / "14F-multi-student-pilot-results.json").read_text(encoding="utf-8")
    )
    summary = result["summary"]
    assert summary["counts"] == {
        "completed": 5,
        "consented": 5,
        "personas": 5,
        "sessions_started": 5,
    }
    assert summary["participant_mode"] == "self_simulated"
    assert summary["real_participants_claimed"] is False
    assert summary["quality_gate"]["conclusion_gate_open"] is True
    assert summary["privacy"]["isolation_audit"]["cross_account_access_blocked"] is True
    assert summary["privacy"]["isolation_audit"]["external_requests"] == 0
    assert summary["privacy"]["isolation_audit"]["real_provider_requests"] == 0
    assert summary["privacy"]["individual_rows_returned"] is False
    assert (output_dir / "14F-multi-student-pilot-matrix.csv").exists()
    assert (output_dir / "14F-multi-student-pilot-privacy-audit.json").exists()
    assert "private synthetic note" not in completed.stdout


def test_runner_contract_uses_existing_upload_query_and_notebook_routes():
    source = RUNNER.read_text(encoding="utf-8")
    for required in (
        '"/api/documents/upload"',
        '"/api/student/concept-queries"',
        '"/api/student/personal-concept-notebook/',
        "run_background_job",
        "STUDENT_CROSS_LANGUAGE_EMBEDDING_BACKEND",
        "STUDENT_BILINGUAL_RERANKER_BACKEND",
    ):
        assert required in source
    assert "requests." not in source
    assert "httpx" not in source
