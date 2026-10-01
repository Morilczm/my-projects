#!/usr/bin/env python3
"""Build and validate the final local-pilot release."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def py() -> str:
    if sys.prefix != sys.base_prefix:
        return sys.executable
    candidate = ROOT / "backend" / ".venv-macos" / "bin" / "python"
    return str(candidate) if candidate.exists() else sys.executable


def run(cmd: list[str], allow_not_ready: bool = False) -> tuple[int, str]:
    env = dict(os.environ)
    env.setdefault("PYTHONPYCACHEPREFIX", str(Path(tempfile.gettempdir()) / "lexibridge-pycache"))
    result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=False, env=env)
    output = result.stdout + result.stderr
    print("$ " + " ".join(cmd))
    print(output.rstrip())
    if result.returncode != 0 and not allow_not_ready:
        raise SystemExit(result.returncode)
    return result.returncode, output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true", help="Run compile and material checks without packaging.")
    args = parser.parse_args()

    python = py()
    status = "PASS"
    run([python, "-m", "py_compile", "backend/app.py", "scripts/migrate_db.py", "scripts/run_worker.py"])
    run([python, "-m", "py_compile", "scripts/check_final_delivery.py", "scripts/check_release_safety.py", "scripts/generate_final_release_manifest.py", "scripts/build_final_release.py", "scripts/generate_final_demo_report.py", "scripts/collect_final_screenshots_checklist.py"])
    run([python, "scripts/check_pilot_package.py"])
    run([python, "scripts/check_final_delivery.py"])

    if not args.check_only:
        run(["bash", "scripts/package_release.sh"])

    release_zip = ROOT / "dist" / "LexiBridge-AI-Local-MVP-v0.8-20260623.zip"
    if args.check_only:
        with tempfile.TemporaryDirectory(prefix="lexibridge-final-release-") as tmp_dir:
            manifest_output = str(Path(tmp_dir) / "final_release_manifest.json")
            run([python, "scripts/generate_final_release_manifest.py", "--output", manifest_output, "--release-zip", str(release_zip)])
    else:
        run([python, "scripts/generate_final_release_manifest.py", "--output", "final_delivery/final_release_manifest.json", "--release-zip", str(release_zip)])
    if release_zip.exists():
        run([python, "scripts/check_release_package.py", str(release_zip)])

    _, readiness = run([python, "scripts/check_production_readiness.py"], allow_not_ready=True)
    if "NOT READY" in readiness:
        status = "PASS_WITH_WARNINGS"

    print(f"Final release result: {status}")
    if release_zip.exists():
        print(f"release_zip={release_zip}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
