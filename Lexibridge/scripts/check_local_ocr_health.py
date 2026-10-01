#!/usr/bin/env python3
"""Print a redacted local OCR health result.

The command only reads server process environment discovery inputs and never
prints executable paths, tessdata paths, or environment values.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from services.ocr import check_tesseract_health  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-output", default="")
    parser.add_argument("--provider", choices=["tesseract"], default="tesseract")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = check_tesseract_health().to_safe_dict()
    payload = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2)
    if args.json_output:
        path = Path(args.json_output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0 if result.get("ready") else 2


if __name__ == "__main__":
    raise SystemExit(main())
