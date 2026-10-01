import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def demo_env(tmp_path):
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{tmp_path / 'demo-eval.db'}"
    env["UPLOAD_FOLDER"] = str(tmp_path / "uploads")
    env["AI_PROVIDER"] = "none"
    env["ALLOW_MOCK_AI"] = "True"
    env["OCR_PROVIDER"] = "none"
    env["FORMULA_OCR_PROVIDER"] = "none"
    return env


def parse_json_line(output, prefix):
    for line in output.splitlines():
        if line.startswith(prefix):
            return json.loads(line.split("=", 1)[1])
    raise AssertionError(f"{prefix} missing from output:\n{output}")


def test_demo_evaluation_run_and_report_files(tmp_path):
    env = demo_env(tmp_path)
    subprocess.run([sys.executable, str(ROOT / "scripts/migrate_db.py"), "--apply"], cwd=ROOT, env=env, check=True)
    flow = subprocess.run(
        [sys.executable, str(ROOT / "scripts/run_demo_flow.py"), "--summary-json"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    summary = parse_json_line(flow.stdout, "DEMO_FLOW_JSON=")
    metrics = summary["evaluation_metrics"]
    assert summary["evaluation_run_id"]
    assert "extraction_precision" in metrics
    assert "alignment_accuracy" in metrics
    assert metrics["no_evidence_forced_alignment_rate"] == 0

    report = ROOT / "docs/demo-test-report.md"
    assert report.exists()
    text = report.read_text(encoding="utf-8")
    assert "Demo Test Report" in text
    assert "no_evidence_forced_alignment_rate" in text
