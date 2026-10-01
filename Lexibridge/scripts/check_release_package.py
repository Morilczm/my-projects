#!/usr/bin/env python3
"""Validate that a LexiBridge AI release archive contains no local or secret files."""

import re
import sys
import zipfile
from pathlib import Path


FORBIDDEN_EXACT = {
    ".env",
    ".DS_Store",
}

FORBIDDEN_PARTS = {
    ".git",
    "uploads",
    "derived",
    "venv",
    ".venv",
    ".venv-macos",
    ".venv-1",
    "__pycache__",
    "__MACOSX",
    ".pytest_cache",
    "node_modules",
}

FORBIDDEN_SUFFIXES = {
    ".db",
    ".sqlite",
    ".sqlite3",
    ".pyc",
}

TEXT_SUFFIXES = {
    ".py",
    ".md",
    ".txt",
    ".yaml",
    ".yml",
    ".json",
    ".js",
    ".html",
    ".css",
    ".example",
    ".sh",
}

SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{16,}"),
    re.compile(r"/" + r"Users/" + r"estaraatopos(?:/|\\b)"),
    re.compile(r"DEEPSEEK_API_KEY\\s*=\\s*sk-[A-Za-z0-9]{8,}"),
    re.compile(r"MATHPIX_APP_KEY\\s*=\\s*[^\\s#]+"),
]


def is_text_member(path):
    suffix = Path(path).suffix
    return suffix in TEXT_SUFFIXES or path.endswith(".env.example")


def scan_archive(zip_path):
    issues = []
    with zipfile.ZipFile(zip_path) as archive:
        for info in archive.infolist():
            normalized = info.filename.replace("\\", "/")
            parts = [part for part in normalized.split("/") if part]
            basename = parts[-1] if parts else ""
            suffix = Path(basename).suffix

            if basename in FORBIDDEN_EXACT:
                issues.append(f"forbidden file: {normalized}")
            if suffix in FORBIDDEN_SUFFIXES:
                issues.append(f"forbidden suffix: {normalized}")
            if any(part in FORBIDDEN_PARTS for part in parts):
                issues.append(f"forbidden path component: {normalized}")

            if info.file_size > 2_000_000 or not is_text_member(normalized):
                continue

            try:
                content = archive.read(info).decode("utf-8", errors="ignore")
            except Exception:
                continue
            for pattern in SECRET_PATTERNS:
                if pattern.search(content):
                    issues.append(f"sensitive content pattern {pattern.pattern!r}: {normalized}")
    return issues


def main(argv):
    if len(argv) != 2:
        print("usage: python scripts/check_release_package.py <release.zip>", file=sys.stderr)
        return 2
    zip_path = Path(argv[1]).expanduser().resolve()
    if not zip_path.exists():
        print(f"release archive not found: {zip_path}", file=sys.stderr)
        return 2
    if zip_path.suffix.lower() != ".zip":
        print(f"release archive must be a .zip file: {zip_path}", file=sys.stderr)
        return 2

    issues = scan_archive(zip_path)
    if issues:
        print("Release package check failed:", file=sys.stderr)
        for issue in issues:
            print(f"- {issue}", file=sys.stderr)
        return 1

    print(f"Release package check passed: {zip_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
