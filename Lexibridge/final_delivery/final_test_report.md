# LexiBridge AI Final Test Report

## Basic Information

- Test time: 2026-06-23T22:11:27
- Operating system: macOS-26.5.1-arm64-arm-64bit
- Python version: 3.9.6
- Database type: SQLite local MVP database
- OCR Provider: local configuration
- Formula OCR Provider: none/local configuration
- AI Provider: none/mock/local unless live provider is configured
- Retrieval Backend: lexical default with vector/hybrid-ready interfaces
- Source demo-test-report: present

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
