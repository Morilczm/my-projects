import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_isolated_shutdown_rehearsal_passes(tmp_path):
    output = tmp_path / "legacy-shutdown-rehearsal.json"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_legacy_alignment_shutdown_rehearsal.py",
            "--json-output",
            str(output),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["verdict"] == "PASS"
    assert payload["environment"] == "isolated_temporary_sqlite"
    assert all(payload["checks"].values())
    assert payload["drained_snapshot"]["active_total"] == 0
    assert payload["checks"]["freeze_http_created_no_legacy_records"] is True
    assert payload["checks"]["rollback_http_creation_restored"] is True
    assert payload["rollback_http_status"] == 200
