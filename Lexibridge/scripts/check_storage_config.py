#!/usr/bin/env python3
import argparse
import importlib.util
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from services.storage import validate_storage_config


def load_env_file(path):
    env = {}
    if not path or not Path(path).exists():
        return env
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", default=os.environ.get("APP_ENV", "development"), choices=["development", "staging", "production"])
    parser.add_argument("--file", default=".env")
    args = parser.parse_args(argv)
    env = os.environ.copy()
    env.update(load_env_file(ROOT / args.file))
    errors, warnings = validate_storage_config(env, app_env=args.env)
    status = "FAIL" if errors else "WARN" if warnings else "PASS"
    print(f"Storage config check: {status}")
    for warning in warnings:
        print(f"- warning: {warning}")
    for error in errors:
        print(f"- error: {error}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
