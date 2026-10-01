#!/usr/bin/env python3
"""Run the controlled Provider Chinese-candidate evaluation harness.

The script defaults to dry-run mode. Live execution requires --execute-live and
still fails closed unless all controlled gates pass.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from services import controlled_provider_evaluation as cpe  # noqa: E402


DEFAULT_PROVIDER = "loopback-provider"
DEFAULT_MODEL = "candidate-model"


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("Manifest must be a JSON object.")
    return data


def _git_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def _load_inputs(manifest: dict[str, Any], max_items: int | None) -> list[cpe.ControlledProviderEvaluationInput]:
    raw_items = manifest.get("items")
    if not isinstance(raw_items, list):
        raise ValueError("Manifest must contain an items array.")
    selected = raw_items[:max_items] if max_items else raw_items
    return [cpe.build_evaluation_input(item) for item in selected]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, help="Controlled evaluation manifest JSON.")
    parser.add_argument("--json-output", required=True, help="Sanitized evaluation artifact output path.")
    parser.add_argument("--dry-run", action="store_true", help="Validate gates and write artifact without network calls.")
    parser.add_argument("--execute-live", action="store_true", help="Attempt live execution after all gates pass.")
    parser.add_argument("--max-items", type=int, default=None, help="Limit evaluated items.")
    parser.add_argument("--provider", default=DEFAULT_PROVIDER, help="Provider safe id from allowlist.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Model safe id from allowlist.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    manifest_path = Path(args.manifest)
    output_path = Path(args.json_output)
    execute_live = bool(args.execute_live)
    dry_run = bool(args.dry_run or not execute_live)
    try:
        manifest = _read_json(manifest_path)
        items = _load_inputs(manifest, args.max_items)
    except Exception as exc:
        safe_message = cpe.redact_sensitive_text(str(exc))
        output_path.write_text(json.dumps({
            "artifact_schema_version": cpe.ARTIFACT_SCHEMA_VERSION,
            "stop_code": "MANIFEST_INVALID",
            "safe_error_message": safe_message,
            "actual_external_provider_requests": 0,
            "private_course_provider_requests": 0,
        }, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        print(f"MANIFEST_INVALID: {safe_message}", file=sys.stderr)
        return 2

    run = cpe.run_controlled_provider_evaluation(
        items,
        provider_name=args.provider,
        model_name=args.model,
        credential_loader=cpe.EnvironmentCredentialLoader("LEXIBRIDGE_PROVIDER_EVAL_API_KEY"),
        pricing=cpe.test_pricing_config(),
        budget=cpe.test_budget_config(max_items_per_batch=args.max_items or 50),
        execute_live=execute_live,
        dry_run=dry_run,
        evaluation_id=str(manifest.get("evaluation_id") or "controlled-provider-evaluation"),
    )
    cpe.write_evaluation_artifact(run, output_path, git_commit=_git_commit())
    if run.stop_code:
        print(run.stop_code, file=sys.stderr)
        return 2
    print(json.dumps({
        "evaluation_id": run.evaluation_id,
        "dry_run": run.dry_run,
        "status_counts": run.status_counts(),
        "actual_external_provider_requests": run.actual_external_provider_requests,
        "private_course_provider_requests": run.private_course_provider_requests,
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
