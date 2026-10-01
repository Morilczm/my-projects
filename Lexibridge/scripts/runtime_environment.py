#!/usr/bin/env python3
"""Resolve and diagnose a reproducible LexiBridge runtime interpreter."""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_DISTRIBUTIONS = (
    "Flask",
    "flask-cors",
    "Flask-SQLAlchemy",
    "gunicorn",
    "PyMuPDF",
    "PyYAML",
    "python-docx",
    "python-pptx",
    "reportlab",
)


def default_runtime_venv(
    *,
    environ: Mapping[str, str] | None = None,
    platform_name: str | None = None,
    home: Path | None = None,
) -> Path:
    env = dict(os.environ if environ is None else environ)
    explicit = str(env.get("LEXIBRIDGE_RUNTIME_VENV") or "").strip()
    if explicit:
        return Path(explicit).expanduser()
    user_home = Path.home() if home is None else Path(home)
    system_name = (platform_name or platform.system()).strip().lower()
    if system_name == "darwin":
        return user_home / "Library" / "Application Support" / "LexiBridge-AI" / "runtime"
    state_root = str(env.get("XDG_STATE_HOME") or "").strip()
    if state_root:
        return Path(state_root).expanduser() / "lexibridge-ai" / "runtime"
    return user_home / ".local" / "state" / "lexibridge-ai" / "runtime"


def candidate_interpreters(
    *,
    root: Path = ROOT,
    environ: Mapping[str, str] | None = None,
    platform_name: str | None = None,
    home: Path | None = None,
    current_python: str | Path | None = None,
) -> list[Path]:
    env = dict(os.environ if environ is None else environ)
    candidates: list[Path] = []
    explicit = str(env.get("LEXIBRIDGE_PYTHON") or "").strip()
    if explicit:
        candidates.append(Path(explicit).expanduser())
    candidates.extend(
        [
            default_runtime_venv(
                environ=env,
                platform_name=platform_name,
                home=home,
            )
            / "bin"
            / "python",
            Path(root) / "backend" / ".venv" / "bin" / "python",
            # Compatibility only. New installations use the external runtime above.
            Path(root) / "backend" / ".venv-macos" / "bin" / "python",
        ]
    )
    if current_python:
        candidates.append(Path(current_python))

    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key not in seen:
            unique.append(candidate)
            seen.add(key)
    return unique


def probe_interpreter(path: Path) -> tuple[bool, str]:
    if not path.is_file():
        return False, "not_found"
    script = (
        "import json, sys; from importlib.metadata import version; "
        f"names={REQUIRED_DISTRIBUTIONS!r}; "
        "print(json.dumps({'python': sys.version.split()[0], "
        "'versions': {name: version(name) for name in names}}, sort_keys=True))"
    )
    try:
        completed = subprocess.run(
            [str(path), "-c", script],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return False, "interpreter_unreadable"
    if completed.returncode != 0:
        return False, "runtime_dependencies_unavailable"
    return True, "healthy"


def select_interpreter(
    candidates: Iterable[Path],
    *,
    probe: Callable[[Path], tuple[bool, str]] = probe_interpreter,
) -> tuple[Path | None, list[dict[str, object]]]:
    diagnostics: list[dict[str, object]] = []
    selected: Path | None = None
    for path in candidates:
        healthy, reason = probe(path)
        diagnostics.append({"path": str(path), "healthy": bool(healthy), "reason": reason})
        if healthy:
            selected = path
            break
    return selected, diagnostics


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--print-venv", action="store_true")
    action.add_argument("--resolve-python", action="store_true")
    action.add_argument("--diagnose", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.print_venv:
        print(default_runtime_venv())
        return 0

    selected, diagnostics = select_interpreter(
        candidate_interpreters(current_python=sys.executable)
    )
    if args.diagnose:
        print(
            json.dumps(
                {
                    "status": "RUNTIME_READY" if selected else "RUNTIME_UNAVAILABLE",
                    "selected_python": str(selected or ""),
                    "candidates": diagnostics,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0 if selected else 2
    if selected is None:
        print(
            "No healthy LexiBridge Python runtime was found. "
            "Run scripts/bootstrap_runtime.sh first.",
            file=sys.stderr,
        )
        for item in diagnostics:
            print(f"- {item['path']}: {item['reason']}", file=sys.stderr)
        return 2
    print(selected)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
