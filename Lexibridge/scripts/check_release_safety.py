#!/usr/bin/env python3
"""Scan repository or release outputs for local files and secret leaks."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAX_TEXT_BYTES = 2_000_000
MAX_RELEASE_FILE_BYTES = 25_000_000

ALLOWED_ENV_EXAMPLES = {
    ".env.example",
    ".env.development.example",
    ".env.production.example",
}

FORBIDDEN_FILENAMES = {
    ".DS_Store",
    "lexibridge.db",
}

FORBIDDEN_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    ".venv-1",
    ".venv-macos",
    "__MACOSX",
    "__pycache__",
    ".pytest_cache",
    "node_modules",
    "model_cache",
    "models",
    "uploads",
}

FORBIDDEN_SUFFIXES = {
    ".db",
    ".sqlite",
    ".sqlite3",
    ".pyc",
    ".pyo",
    ".log",
    ".tmp",
    ".temp",
    ".bak",
    ".gguf",
    ".onnx",
    ".pt",
    ".pth",
    ".safetensors",
    ".swp",
}

ARCHIVE_SUFFIXES = {
    ".zip",
    ".tar",
    ".tgz",
    ".7z",
    ".rar",
}

TEXT_SUFFIXES = {
    "",
    ".cfg",
    ".conf",
    ".css",
    ".env",
    ".example",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".jsonl",
    ".md",
    ".py",
    ".sh",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}

PLACEHOLDER_TOKENS = {
    "",
    "change-me",
    "change-me-in-local-dev",
    "change-me-in-local-token-hash-secret",
    "change-this-local-token-hash-secret",
    "placeholder",
    "replace-with-strong-secret",
    "replace_me",
    "your-api-key",
    "your-api-key-here",
    "your-app-id",
    "your-app-key",
    "your-deepseek-api-key",
    "your-deepseek-api-key-here",
    "your-openai-api-key-here",
    "your-secret-key",
    "your-token-here",
    "your-latex-ocr-command",
    "your_mATHPIX_APP_KEY_HERE".lower(),
    "your_deepseek_api_key_here",
    "your_openai_api_key_here",
    "your_mathpix_app_id_here",
    "your_mathpix_app_key_here",
    "not-for-release",
    "secret1234",
    "sk-xxx",
}

ENV_SECRET_VALUE_RE = re.compile(
    r"(?m)^\s*([A-Z0-9_]*(?:API_KEY|SECRET|TOKEN|PASSWORD|APP_KEY|ACCESS_KEY|PRIVATE_KEY)[A-Z0-9_]*)"
    r"\s*=\s*([^\s#]+)"
)

QUOTED_SECRET_VALUE_RE = re.compile(
    r"(?i)\b(api[_-]?key|secret|token|password|app[_-]?key|access[_-]?key|private[_-]?key)\b"
    r"\s*[:=]\s*['\"]([^'\"]{12,})['\"]"
)

SECRET_PATTERNS = [
    ("OpenAI/DeepSeek-style API key", re.compile(r"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{24,}\b")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[0-9A-Za-z_]{24,}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{20,}\b")),
]

LOCAL_PATH_PATTERNS = [
    re.compile(r"/Users/[A-Za-z0-9._-]+/"),
    re.compile(r"/home/[A-Za-z0-9._-]+/"),
    re.compile(r"/private/var/folders/[A-Za-z0-9._-]+/"),
    re.compile(r"[A-Za-z]:\\Users\\[A-Za-z0-9._-]+\\"),
]

MIGRATION_CLI_CALL_RE = re.compile(r"(?:scripts/|scripts\\)migrate_db\.py")

GENERIC_SECRET_SUFFIXES = {
    ".cfg",
    ".conf",
    ".env",
    ".example",
    ".ini",
    ".json",
    ".jsonl",
    ".md",
    ".sh",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}


@dataclass(frozen=True)
class ScanItem:
    display_path: str
    parts: tuple[str, ...]
    data: bytes | None = None
    size_bytes: int = 0


def is_allowed_placeholder(value: str) -> bool:
    normalized = value.strip().strip("'\"").lower()
    if normalized in PLACEHOLDER_TOKENS:
        return True
    return normalized.startswith("your_") or normalized.startswith("your-")


def is_probably_binary(data: bytes) -> bool:
    return b"\0" in data[:4096]


def is_text_path(path: str) -> bool:
    suffixes = Path(path).suffixes
    suffix = suffixes[-1].lower() if suffixes else ""
    return suffix in TEXT_SUFFIXES or path.endswith(tuple(ALLOWED_ENV_EXAMPLES))


def should_scan_generic_secret(path: str) -> bool:
    suffixes = Path(path).suffixes
    suffix = suffixes[-1].lower() if suffixes else ""
    return suffix in GENERIC_SECRET_SUFFIXES or path.endswith(tuple(ALLOWED_ENV_EXAMPLES))


def split_parts(path: str) -> tuple[str, ...]:
    normalized = path.replace("\\", "/").strip("/")
    if not normalized:
        return tuple()
    return tuple(part for part in normalized.split("/") if part and part != ".")


def archive_suffix(path: str) -> str:
    lowered = path.lower()
    if lowered.endswith(".tar.gz"):
        return ".tar.gz"
    return Path(lowered).suffix


def iter_git_candidates(root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return []
    paths = []
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        paths.append(root / raw.decode("utf-8", errors="surrogateescape"))
    return paths


def iter_directory_items(root: Path, use_git_candidates: bool) -> list[ScanItem]:
    if use_git_candidates:
        candidates = iter_git_candidates(root)
        if candidates:
            paths = candidates
        else:
            paths = [path for path in root.rglob("*") if ".git" not in path.parts]
    else:
        paths = [path for path in root.rglob("*") if ".git" not in path.parts]

    items = []
    for path in paths:
        try:
            rel = path.relative_to(root)
        except ValueError:
            rel = path
        display = rel.as_posix()
        parts = split_parts(display)
        if not parts:
            continue
        if path.is_dir():
            items.append(ScanItem(display, parts))
            continue
        if not path.is_file():
            continue
        data = None
        if is_text_path(display) and path.stat().st_size <= MAX_TEXT_BYTES:
            try:
                data = path.read_bytes()
            except OSError:
                data = None
        items.append(ScanItem(display, parts, data, path.stat().st_size))
    return items


def iter_zip_items(path: Path) -> list[ScanItem]:
    items = []
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            display = info.filename.replace("\\", "/")
            parts = split_parts(display)
            if not parts:
                continue
            data = None
            if not info.is_dir() and is_text_path(display) and info.file_size <= MAX_TEXT_BYTES:
                try:
                    data = archive.read(info)
                except (OSError, zipfile.BadZipFile):
                    data = None
            items.append(ScanItem(display, parts, data, info.file_size))
    return items


def iter_tar_items(path: Path) -> list[ScanItem]:
    items = []
    with tarfile.open(path) as archive:
        for member in archive.getmembers():
            display = member.name.replace("\\", "/")
            parts = split_parts(display)
            if not parts:
                continue
            data = None
            if member.isfile() and is_text_path(display) and member.size <= MAX_TEXT_BYTES:
                extracted = archive.extractfile(member)
                if extracted:
                    data = extracted.read(MAX_TEXT_BYTES + 1)
            items.append(ScanItem(display, parts, data, member.size))
    return items


def load_items(target: Path, repo_mode: bool) -> list[ScanItem]:
    if target.is_dir():
        return iter_directory_items(target, use_git_candidates=repo_mode)
    suffix = archive_suffix(str(target))
    if suffix == ".zip":
        return iter_zip_items(target)
    if suffix in {".tar", ".tar.gz", ".tgz"}:
        return iter_tar_items(target)
    raise ValueError(f"unsupported scan target: {target}")


def check_path(item: ScanItem) -> list[str]:
    issues = []
    basename = item.parts[-1]
    suffix = archive_suffix(basename)

    if basename.startswith(".env") and basename not in ALLOWED_ENV_EXAMPLES:
        issues.append(f"forbidden env file: {item.display_path}")
    if basename in FORBIDDEN_FILENAMES:
        issues.append(f"forbidden local file: {item.display_path}")
    if suffix in FORBIDDEN_SUFFIXES:
        issues.append(f"forbidden runtime suffix: {item.display_path}")
    if suffix in ARCHIVE_SUFFIXES or suffix == ".tar.gz":
        issues.append(f"nested archive/release package: {item.display_path}")
    if item.size_bytes > MAX_RELEASE_FILE_BYTES:
        issues.append(f"oversized release file: {item.display_path}")
    for part in item.parts[:-1]:
        if part in FORBIDDEN_DIRS:
            issues.append(f"forbidden path component '{part}': {item.display_path}")
    if basename in FORBIDDEN_DIRS:
        issues.append(f"forbidden path component '{basename}': {item.display_path}")
    return issues


def check_content(item: ScanItem) -> list[str]:
    if item.data is None or is_probably_binary(item.data):
        return []
    text = item.data.decode("utf-8", errors="ignore")
    issues = []

    for label, pattern in SECRET_PATTERNS:
        for match in pattern.finditer(text):
            if is_allowed_placeholder(match.group(0)):
                continue
            issues.append(f"{label}: {item.display_path}")
            break

    if should_scan_generic_secret(item.display_path):
        for match in ENV_SECRET_VALUE_RE.finditer(text):
            value = match.group(2)
            if is_allowed_placeholder(value):
                continue
            if len(value) < 12 and not any(ch.isdigit() for ch in value):
                continue
            issues.append(f"secret-like assignment for {match.group(1)}: {item.display_path}")
            break

        for match in QUOTED_SECRET_VALUE_RE.finditer(text):
            value = match.group(2)
            if is_allowed_placeholder(value):
                continue
            if len(value) < 12 and not any(ch.isdigit() for ch in value):
                continue
            issues.append(f"secret-like hard-coded value for {match.group(1)}: {item.display_path}")
            break

    for pattern in LOCAL_PATH_PATTERNS:
        if pattern.search(text):
            issues.append(f"local absolute path: {item.display_path}")
            break
    issues.extend(check_migration_cli_apply_contract(item, text))
    return issues


def check_migration_cli_apply_contract(item: ScanItem, text: str) -> list[str]:
    if not item.parts or item.parts[0] not in {"scripts", "tests"}:
        return []
    if item.display_path in {
        "tests/test_migrate_db_cli.py",
        "tests/test_release_safety.py",
        "scripts/evaluations/open_source_parser_eval/docling_failure_attribution_runner.py",
    }:
        return []
    suffix = Path(item.display_path).suffix.lower()
    if suffix not in {".py", ".sh"}:
        return []

    issues = []
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if not MIGRATION_CLI_CALL_RE.search(line):
            continue
        window = "\n".join(lines[max(0, index - 3): min(len(lines), index + 4)])
        if "py_compile" in window:
            continue
        if "--apply" not in window:
            issues.append(f"migration CLI call missing explicit --apply: {item.display_path}:{index + 1}")
    return issues


def scan(target: Path, repo_mode: bool) -> list[str]:
    items = load_items(target, repo_mode=repo_mode)
    issues = []
    for item in items:
        issues.extend(check_path(item))
        issues.extend(check_content(item))
    return sorted(set(issues))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "targets",
        nargs="*",
        help="Repository root, release directory, .zip, .tar, or .tar.gz to scan. Defaults to this repository.",
    )
    parser.add_argument(
        "--all-files",
        action="store_true",
        help="When scanning the repository root, include ignored local files such as .env.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    targets = [Path(path).expanduser().resolve() for path in args.targets] or [ROOT]
    all_issues = []

    for target in targets:
        if not target.exists():
            print(f"scan target not found: {target}", file=sys.stderr)
            return 2
        repo_mode = target == ROOT and not args.all_files
        try:
            issues = scan(target, repo_mode=repo_mode)
        except (OSError, ValueError, zipfile.BadZipFile, tarfile.TarError) as exc:
            print(f"could not scan {target}: {exc}", file=sys.stderr)
            return 2
        all_issues.extend(f"{target}: {issue}" for issue in issues)

    if all_issues:
        print("Release safety check failed:", file=sys.stderr)
        for issue in all_issues:
            print(f"- {issue}", file=sys.stderr)
        return 1

    print("Release safety check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
