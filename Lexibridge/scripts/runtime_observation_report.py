#!/usr/bin/env python3
"""Aggregate payload-free local runtime samples without inventing elapsed time."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence


def parse_time(value: str) -> datetime:
    text = str(value or "").strip()
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError("Observation timestamps must include a timezone.")
    return parsed


def summarize_records(
    records: Iterable[dict[str, object]],
    *,
    window_start: str,
    window_end: str,
    minimum_days: int = 14,
    minimum_active_days: int = 5,
    evaluated_at: str | None = None,
) -> dict[str, object]:
    started = parse_time(window_start)
    ended = parse_time(window_end)
    if ended <= started:
        raise ValueError("Observation window end must be after its start.")
    evaluated = parse_time(evaluated_at) if evaluated_at else datetime.now(timezone.utc)
    source_records = list(records)
    safe_records: list[dict[str, object]] = []
    for record in source_records:
        if record.get("schema_version") != "runtime-probe-v1":
            continue
        try:
            observed = parse_time(str(record.get("observed_at") or ""))
        except (TypeError, ValueError):
            continue
        if started <= observed <= ended:
            safe_records.append(record)
    duration_days = max(0.0, (ended - started).total_seconds() / 86400)
    healthy = [record for record in safe_records if record.get("outcome") == "healthy"]
    active_dates = sorted(
        {
            parse_time(str(record.get("observed_at") or "")).date().isoformat()
            for record in healthy
            if record.get("observed_at")
        }
    )
    sample_count = len(safe_records)
    success_ratio = len(healthy) / sample_count if sample_count else 0.0
    gates = {
        "window_elapsed": evaluated >= ended,
        "minimum_duration_met": duration_days >= max(1, minimum_days),
        "minimum_active_days_met": len(active_dates) >= max(1, minimum_active_days),
        "samples_present": sample_count > 0,
        "all_samples_healthy": sample_count > 0 and len(healthy) == sample_count,
    }
    return {
        "status": (
            "RUNTIME_OBSERVATION_COMPLETE"
            if all(gates.values())
            else "RUNTIME_OBSERVATION_PENDING"
        ),
        "window_start": window_start,
        "window_end": window_end,
        "evaluated_at": evaluated.isoformat().replace("+00:00", "Z"),
        "duration_days": round(duration_days, 3),
        "active_days": len(active_dates),
        "active_dates": active_dates,
        "gates": gates,
        "metrics": {
            "sample_count": sample_count,
            "healthy_samples": len(healthy),
            "unhealthy_samples": sample_count - len(healthy),
            "success_ratio": round(success_ratio, 6),
            "excluded_or_invalid_samples": len(source_records) - sample_count,
        },
    }


def load_records(paths: Sequence[str]) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for path_text in paths:
        for line in Path(path_text).read_text(encoding="utf-8").splitlines():
            try:
                payload = json.loads(line)
            except (TypeError, ValueError):
                continue
            if isinstance(payload, dict):
                records.append(payload)
    return records


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", action="append", required=True, dest="logs")
    parser.add_argument("--window-start", required=True)
    parser.add_argument("--window-end", required=True)
    parser.add_argument("--minimum-days", type=int, default=14)
    parser.add_argument("--minimum-active-days", type=int, default=5)
    parser.add_argument("--json-output", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = summarize_records(
        load_records(args.logs),
        window_start=args.window_start,
        window_end=args.window_end,
        minimum_days=args.minimum_days,
        minimum_active_days=args.minimum_active_days,
    )
    rendered = json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True)
    Path(args.json_output).write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["status"] == "RUNTIME_OBSERVATION_COMPLETE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
