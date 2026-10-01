import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_export_final_project_snapshot(tmp_path):
    output = tmp_path / "final_project_snapshot.json"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "export_final_project_snapshot.py"),
            "--output",
            str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert output.exists()
    snapshot = json.loads(output.read_text(encoding="utf-8"))
    assert snapshot["project_name"] == "LexiBridge AI"
    assert snapshot["core_capabilities"]
    assert snapshot["known_limitations"]
    assert snapshot["pilot_package_files"]
    serialized = json.dumps(snapshot, ensure_ascii=False)
    assert "api_key" not in serialized.lower()
    assert not re.search(r"\bsk-[A-Za-z0-9_-]{8,}\b", serialized)
    assert not re.search(r"\bBearer\s+[A-Za-z0-9._-]{20,}\b", serialized, re.IGNORECASE)
