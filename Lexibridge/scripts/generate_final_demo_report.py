#!/usr/bin/env python3
"""Generate the final test report from existing validation records."""

from __future__ import annotations

import argparse
import platform
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def build_report() -> str:
    demo_report = ROOT / "docs" / "demo-test-report.md"
    demo_status = "present" if demo_report.exists() else "missing"
    return f"""# LexiBridge AI Final Test Report

## Basic Information

- Test time: {datetime.now().isoformat(timespec='seconds')}
- Operating system: {platform.platform()}
- Python version: {platform.python_version()}
- Database type: SQLite local MVP database
- OCR Provider: local configuration
- Formula OCR Provider: none/local configuration
- AI Provider: none/mock/local unless live provider is configured
- Retrieval Backend: lexical default with vector/hybrid-ready interfaces
- Source demo-test-report: {demo_status}

## Executed Command Summary

- `check_pilot_package.py`: validates PR-15 pilot package.
- `check_final_delivery.py`: validates PR-16 final delivery materials.
- `pytest`: validates API contract, permissions, OCR, retrieval, alignment, evaluation, jobs, storage, AI governance, KB versioning, hybrid retrieval, pilot package, and final delivery tests.
- `package_release.sh`: builds the release zip and runs release package checks.
- `check_production_readiness.py`: currently reports NOT READY, which is expected for local pilot-ready status.

## Result Summary

The latest executed results are recorded in `docs/demo-test-report.md`. This generated report does not invent missing metrics; if a source report is missing, it records that state instead.

## Known Warnings

Dependency warnings and SQLAlchemy legacy warnings may appear in pytest output. They do not change the current local pilot-ready status.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(build_report(), encoding="utf-8")
    print(f"Final demo report written: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
