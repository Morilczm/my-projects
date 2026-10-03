"""Compare one BYR Docs Archive snapshot with a local resource directory."""

import argparse
import csv
import json
import re
import subprocess
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

import yaml


SOURCE_EXTENSIONS = {".pdf", ".zip"}
PREVIEW_EXTENSIONS = {".jpg", ".webp"}
FIELDS = [
    "id", "status", "action", "type", "title_or_course", "metadata_yaml",
    "expected_source", "local_source", "source_bytes", "jpg", "webp",
    "pdf_title_hint", "pdf_pages", "original_url",
]


def pdf_hints(path: Path, pdfinfo: Path | None) -> tuple[str, str]:
    if not pdfinfo or not pdfinfo.is_file():
        return "", ""
    try:
        result = subprocess.run(
            [str(pdfinfo), str(path)], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=20, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "", ""
    values = dict(re.findall(r"^([^:\r\n]+):\s*(.*)$", result.stdout, re.MULTILINE))
    return values.get("Title", "").strip(), values.get("Pages", "").strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=Path(r"E:\byrdocs-archive"))
    parser.add_argument("--resources", type=Path, default=Path(r"E:\byrdocs"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pdfinfo", type=Path)
    args = parser.parse_args()

    metadata_dir = args.archive / "metadata"
    if not metadata_dir.is_dir() or not args.resources.is_dir():
        parser.error("Archive metadata or resource directory does not exist")

    files: dict[str, dict[str, Path]] = {}
    for path in args.resources.iterdir():
        if path.is_file() and path.suffix.lower() in SOURCE_EXTENSIONS | PREVIEW_EXTENSIONS:
            files.setdefault(path.stem.lower(), {})[path.suffix.lower()] = path

    entries = {}
    errors = []
    for path in sorted(metadata_dir.iterdir()):
        if path.suffix.lower() not in {".yml", ".yaml"}:
            continue
        try:
            entry = yaml.safe_load(path.read_text(encoding="utf-8"))
            file_id = str(entry["id"]).lower()
            url = str(entry["url"])
            expected = Path(urlparse(url).path).name.lower()
            if file_id != path.stem.lower() or Path(expected).stem != file_id:
                errors.append(f"ID / URL mismatch: {path.name}")
            if file_id in entries:
                errors.append(f"Duplicate metadata ID: {file_id}")
            entries[file_id] = (entry, path, expected)
        except (OSError, ValueError, TypeError, KeyError, yaml.YAMLError) as exc:
            errors.append(f"Cannot parse {path.name}: {exc}")
    if errors:
        raise SystemExit("\n".join(errors))

    rows = []
    for file_id in sorted(set(entries) | set(files)):
        entry, yaml_path, expected = entries.get(file_id, (None, None, ""))
        local = files.get(file_id, {})
        sources = [path for ext, path in local.items() if ext in SOURCE_EXTENSIONS]
        expected_source = local.get(Path(expected).suffix.lower()) if expected else None
        if entry and expected_source:
            status, action = "ready", "include_after_storage_upload"
        elif entry and sources:
            status, action = "extension_mismatch", "review_filename_and_metadata"
        elif entry:
            status, action = "missing_source", "find_original_or_exclude_from_site_index"
        elif sources:
            status, action = "missing_metadata", "inspect_pdf_and_write_reviewed_yaml"
        else:
            status, action = "preview_only", "find_original_or_hold_preview"

        source = expected_source or (sources[0] if sources else None)
        data = entry.get("data", {}) if entry else {}
        course = data.get("course", "")
        if isinstance(course, dict):
            course = course.get("name", "")
        elif isinstance(course, list):
            course = "; ".join(str(item.get("name", "")) if isinstance(item, dict) else str(item) for item in course)
        title = data.get("title", "") or course
        hint, pages = pdf_hints(source, args.pdfinfo) if source and not entry and source.suffix.lower() == ".pdf" else ("", "")
        rows.append({
            "id": file_id,
            "status": status,
            "action": action,
            "type": entry.get("type", "") if entry else "",
            "title_or_course": title,
            "metadata_yaml": str(yaml_path) if yaml_path else "",
            "expected_source": expected,
            "local_source": str(source) if source else "",
            "source_bytes": source.stat().st_size if source else "",
            "jpg": str(local.get(".jpg", "")),
            "webp": str(local.get(".webp", "")),
            "pdf_title_hint": hint,
            "pdf_pages": pages,
            "original_url": entry.get("url", "") if entry else "",
        })

    args.output.mkdir(parents=True, exist_ok=True)
    for name, selected in [
        ("all_resources.csv", rows),
        ("ready.csv", [row for row in rows if row["status"] == "ready"]),
        ("missing_source.csv", [row for row in rows if row["status"] == "missing_source"]),
        ("missing_metadata.csv", [row for row in rows if row["status"] == "missing_metadata"]),
        ("preview_only.csv", [row for row in rows if row["status"] == "preview_only"]),
        ("extension_mismatch.csv", [row for row in rows if row["status"] == "extension_mismatch"]),
    ]:
        with (args.output / name).open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(selected)

    summary = {
        "archive": str(args.archive),
        "resources": str(args.resources),
        "metadata_records": len(entries),
        "local_resource_ids": len(files),
        "status_counts": dict(Counter(row["status"] for row in rows)),
        "missing_source_types": dict(Counter(row["type"] for row in rows if row["status"] == "missing_source")),
    }
    (args.output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
