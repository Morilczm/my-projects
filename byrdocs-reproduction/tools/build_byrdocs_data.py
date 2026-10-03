"""Build the four public data objects for a BYR Docs mirror."""

import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import yaml


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--resources", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--site-url", required=True)
    args = parser.parse_args()

    site = urlsplit(args.site_url.rstrip("/"))
    if site.scheme != "https" or not site.netloc:
        parser.error("--site-url must be an HTTPS URL")

    records = []
    counts = {"book": 0, "test": 0, "doc": 0}
    missing_files = []
    seen_ids = set()
    for source in sorted((args.archive / "metadata").glob("*.yml")):
        record = yaml.safe_load(source.read_text(encoding="utf-8"))
        if not isinstance(record, dict) or record.get("type") not in counts:
            raise ValueError(f"Unexpected metadata format: {source}")
        file_id = record.get("id")
        if file_id != source.stem or file_id in seen_ids:
            raise ValueError(f"Invalid or duplicate metadata ID: {source}")
        seen_ids.add(file_id)

        original_url = urlsplit(record["url"])
        if original_url.path != f"/files/{file_id}.{record['data']['filetype']}":
            raise ValueError(f"Unexpected file URL: {source}")
        record["url"] = urlunsplit((site.scheme, site.netloc, original_url.path, "", ""))

        resource = args.resources / f"{file_id}.{record['data']['filetype']}"
        if resource.is_file():
            record["data"]["filesize"] = resource.stat().st_size
        else:
            missing_files.append(resource.name)
        counts[record["type"]] += 1
        records.append(record)

    if not records:
        raise ValueError("No metadata records found")

    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "metadata.json").write_text(
        json.dumps(records, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    # These YAML objects are public validation schemas, not category listings.
    host_pattern = re.escape(site.netloc)
    for name in ("book.yaml", "test.yaml", "doc.yaml"):
        source = args.archive / "schema" / name
        schema = yaml.safe_load(source.read_text(encoding="utf-8"))
        schema["properties"]["url"]["pattern"] = (
            f"^https://{host_pattern}/files/"
            r"[0-9A-Za-z]{32}\.(pdf|zip)$"
        )
        (args.output / name).write_text(
            yaml.safe_dump(schema, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

    print(json.dumps({
        "records": len(records),
        "types": counts,
        "missing_source_files": len(missing_files),
        "output": str(args.output),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
