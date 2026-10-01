#!/usr/bin/env python3
"""Inspect or safely disposition the isolated legacy alignment runtime."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))


def load_app_module():
    spec = importlib.util.spec_from_file_location("lexibridge_legacy_runtime_tool", BACKEND / "app.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def emit(payload, output_path=""):
    rendered = json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True)
    print(rendered)
    if output_path:
        Path(output_path).write_text(rendered + "\n", encoding="utf-8")


def status_command(args):
    app_module = load_app_module()
    with app_module.app.app_context():
        snapshot = app_module.legacy_alignment_queue_snapshot(limit=args.limit)
    emit(
        {
            "status": "success",
            "runtime_state": app_module.LEGACY_ALIGNMENT_RUNTIME_STATE,
            "creation_allowed": app_module.legacy_alignment_creation_is_allowed(),
            "worker_claim_allowed": app_module.legacy_alignment_worker_claim_is_allowed(),
            "queue": snapshot,
        },
        args.json_output,
    )
    return 0


def safe_fail_command(args):
    app_module = load_app_module()
    service = app_module.legacy_alignment_freeze_service
    if args.apply:
        apply_enabled = os.environ.get("LEGACY_ALIGNMENT_SAFE_FAILURE_APPLY_ENABLED", "false").strip().lower()
        if apply_enabled != "true":
            raise SystemExit(
                "Apply is disabled; set LEGACY_ALIGNMENT_SAFE_FAILURE_APPLY_ENABLED=true after approval."
            )
        if app_module.LEGACY_ALIGNMENT_RUNTIME_STATE not in {
            service.RUNTIME_STATE_FREEZE,
            service.RUNTIME_STATE_DRAINING,
        }:
            raise SystemExit("Apply requires LEGACY_ALIGNMENT_RUNTIME_STATE=freeze or draining.")
        if app_module.legacy_alignment_creation_is_allowed():
            raise SystemExit("Apply requires legacy creation admission to be closed.")

    with app_module.app.app_context():
        try:
            result = service.safe_fail_running_job(
                app_module.db.session,
                app_module.legacy_alignment_runtime_models(),
                job_id=args.job_id,
                expected_locked_by=args.expected_locked_by,
                stale_before=args.stale_before,
                actor_name=args.actor,
                now_fn=app_module.current_time_text,
                apply=args.apply,
            )
        except Exception:
            app_module.db.session.rollback()
            raise
    emit(result, args.json_output)
    return 0


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    status_parser = subparsers.add_parser("status", help="Read legacy queue counts without writes.")
    status_parser.add_argument("--limit", type=int, default=100)
    status_parser.add_argument("--json-output", default="")
    status_parser.set_defaults(handler=status_command)

    safe_fail_parser = subparsers.add_parser(
        "safe-fail",
        help="Dry-run or apply a fenced safe failure to one stale running legacy job.",
    )
    safe_fail_parser.add_argument("--job-id", required=True, type=int)
    safe_fail_parser.add_argument("--expected-locked-by", required=True)
    safe_fail_parser.add_argument("--stale-before", required=True)
    safe_fail_parser.add_argument("--actor", required=True)
    safe_fail_parser.add_argument("--apply", action="store_true")
    safe_fail_parser.add_argument("--json-output", default="")
    safe_fail_parser.set_defaults(handler=safe_fail_command)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
