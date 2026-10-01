#!/usr/bin/env python3
"""Summarize structured Legacy alignment observation logs without raw payloads."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from services.legacy_alignment_observation import summarize_events  # noqa: E402


def _parse_time(value):
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", action="append", required=True, dest="logs")
    parser.add_argument("--environment", required=True)
    parser.add_argument("--database", required=True, dest="database_label")
    parser.add_argument("--window-start", required=True)
    parser.add_argument("--window-end", default="")
    parser.add_argument("--active-days", type=int, default=0)
    parser.add_argument("--external-consumer-status", default="UNKNOWN_EXTERNAL_LEGACY_CONSUMER")
    parser.add_argument("--json-output", required=True)
    args = parser.parse_args(argv)

    lines = []
    for path_text in args.logs:
        path = Path(path_text)
        lines.extend(path.read_text(encoding="utf-8").splitlines())
    summary = summarize_events(lines)
    started = _parse_time(args.window_start)
    ended = _parse_time(args.window_end)
    elapsed_seconds = (ended - started).total_seconds() if started and ended else 0
    duration_days = max(0.0, elapsed_seconds / 86400)
    gates = {
        "fourteen_continuous_days": duration_days >= 14,
        "five_active_days": args.active_days >= 5,
        "legacy_creation_signals_zero": summary["legacy_creation_signal_count"] == 0,
        "external_consumer_boundary_supported": (
            args.external_consumer_status == "NO_KNOWN_EXTERNAL_LEGACY_CONSUMER"
        ),
    }
    complete = all(gates.values())
    payload = {
        "status": (
            "OBSERVATION_WINDOW_EVIDENCE_RECORDED" if complete else "OBSERVATION_WINDOW_PENDING"
        ),
        "environment": args.environment,
        "database": args.database_label,
        "window_start": args.window_start,
        "window_end": args.window_end,
        "duration_days": round(duration_days, 3),
        "active_days": max(0, args.active_days),
        "external_consumer_status": args.external_consumer_status,
        "gates": gates,
        "metrics": summary,
    }
    rendered = json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True)
    Path(args.json_output).write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
