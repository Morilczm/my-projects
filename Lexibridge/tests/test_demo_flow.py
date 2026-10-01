import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def env_for_demo(tmp_path):
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{tmp_path / 'demo-flow.db'}"
    env["UPLOAD_FOLDER"] = str(tmp_path / "uploads")
    env["AI_PROVIDER"] = "none"
    env["ALLOW_MOCK_AI"] = "True"
    env["OCR_PROVIDER"] = "none"
    env["FORMULA_OCR_PROVIDER"] = "none"
    return env


def parse_flow_summary(output):
    for line in output.splitlines():
        if line.startswith("DEMO_FLOW_JSON="):
            return json.loads(line.split("=", 1)[1])
    raise AssertionError(f"DEMO_FLOW_JSON missing from output:\n{output}")


def test_run_demo_flow_minimum_closed_loop(tmp_path):
    env = env_for_demo(tmp_path)
    subprocess.run([sys.executable, str(ROOT / "scripts/migrate_db.py"), "--apply"], cwd=ROOT, env=env, check=True)
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/run_demo_flow.py"), "--summary-json"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    summary = parse_flow_summary(result.stdout)
    assert summary["document_ingestion"] == "PASS"
    assert summary["alignment_run"] == "PASS"
    assert summary["cards_generated"] > 0
    assert summary["qc_cards"] > 0
    assert summary["auto_approved_cards"] == 0
    assert summary["student_search"] == "PASS"
    assert summary["student_feedback"] == "PASS"
    assert summary["admin_jobs"] == "PASS"
    assert summary["evaluation_run"] == "PASS"
    assert summary["no_evidence_forced_alignment_rate"] == 0
