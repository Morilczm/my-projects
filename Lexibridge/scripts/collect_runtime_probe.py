#!/usr/bin/env python3
"""Record one payload-free health sample from a loopback LexiBridge runtime."""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence
from urllib.parse import ParseResult, urlparse


SCHEMA_VERSION = "runtime-probe-v1"
LOOPBACK_HOSTS = {"127.0.0.1", "::1"}
SAFE_TARGET_LABEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")


def validate_local_endpoint(value: str) -> ParseResult:
    parsed = urlparse(str(value or "").strip())
    if parsed.scheme != "http" or parsed.hostname not in LOOPBACK_HOSTS:
        raise ValueError("Runtime probe endpoint must use an HTTP loopback IP literal.")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Runtime probe endpoint must not contain credentials, query, or fragment.")
    if parsed.path != "/api/test":
        raise ValueError("Runtime probe endpoint must use the payload-free /api/test path.")
    return parsed


def validate_target_label(value: str) -> str:
    label = str(value or "").strip()
    if not SAFE_TARGET_LABEL.fullmatch(label):
        raise ValueError("Runtime probe target label must use a non-sensitive stable identifier.")
    return label


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def build_record(
    *,
    target_label: str,
    endpoint_path: str,
    status_code: int,
    latency_ms: float,
    outcome: str,
    error_code: str,
    observed_at: str,
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "observed_at": observed_at,
        "target_label": validate_target_label(target_label),
        "endpoint_path": endpoint_path,
        "outcome": outcome,
        "status_code": max(0, int(status_code or 0)),
        "latency_ms": round(max(0.0, float(latency_ms or 0.0)), 3),
        "error_code": str(error_code or "")[:80],
    }


def collect(endpoint: str, target_label: str, timeout_seconds: float) -> dict[str, object]:
    parsed = validate_local_endpoint(endpoint)
    started = time.monotonic()
    status_code = 0
    outcome = "unhealthy"
    error_code = "RUNTIME_PROBE_FAILED"
    try:
        with urllib.request.urlopen(endpoint, timeout=timeout_seconds) as response:
            status_code = int(response.status or 0)
            # Read only a bounded health envelope and never retain it.
            payload = json.loads(response.read(2048).decode("utf-8"))
            if status_code == 200 and payload.get("status") == "success":
                outcome = "healthy"
                error_code = ""
            else:
                error_code = "RUNTIME_HEALTH_CONTRACT_FAILED"
    except urllib.error.HTTPError as exc:
        status_code = int(exc.code or 0)
        error_code = "RUNTIME_HTTP_ERROR"
    except (OSError, ValueError, json.JSONDecodeError):
        error_code = "RUNTIME_CONNECTION_OR_PAYLOAD_FAILED"
    latency_ms = (time.monotonic() - started) * 1000
    return build_record(
        target_label=target_label,
        endpoint_path=parsed.path,
        status_code=status_code,
        latency_ms=latency_ms,
        outcome=outcome,
        error_code=error_code,
        observed_at=utc_now(),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default="http://127.0.0.1:5000/api/test")
    parser.add_argument("--target-label", default="pilot-local")
    parser.add_argument("--timeout-seconds", type=float, default=5.0)
    parser.add_argument("--jsonl-output", default="")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        record = collect(args.endpoint, args.target_label, args.timeout_seconds)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    rendered = json.dumps(record, ensure_ascii=True, sort_keys=True)
    print(rendered)
    if args.jsonl_output:
        output = Path(args.jsonl_output)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("a", encoding="utf-8") as handle:
            handle.write(rendered + "\n")
    return 0 if record["outcome"] == "healthy" else 1


if __name__ == "__main__":
    raise SystemExit(main())
