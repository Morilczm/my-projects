#!/usr/bin/env python3
"""Validate AI provider, prompt logging, and quota configuration."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from services.ai_registry import validate_ai_config  # noqa: E402


def load_env_file(path):
    data = {}
    path = Path(path)
    if not path.exists():
        return data
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip().strip('"').strip("'")
    return data


def merged_env(path=None):
    env = dict(os.environ)
    if path:
        env.update(load_env_file(path))
    elif (ROOT / ".env").exists():
        env.update(load_env_file(ROOT / ".env"))
    return env


def main(argv=None):
    parser = argparse.ArgumentParser(description="Check LexiBridge AI provider configuration.")
    parser.add_argument("--env", choices=["development", "staging", "production"], default="development")
    parser.add_argument("--file", help="Optional env file to validate.")
    args = parser.parse_args(argv)
    errors, warnings = validate_ai_config(args.env, merged_env(args.file))
    status = "FAIL" if errors else "PASS"
    print(f"AI config check ({args.env}): {status}")
    for warning in warnings:
        print(f"WARNING: {warning}")
    for error in errors:
        print(f"- {error}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
