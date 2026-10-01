#!/usr/bin/env python3
"""Run the Task 14B parser comparison in isolated local runtimes."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


# The retrieval backend uses Hugging Face tokenizers before the runner makes
# small local Git subprocess calls for audit metadata.  Declare the safe fork
# behavior in the parent too, not only in parser probe children.
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluations.open_source_parser_eval import controlled_benchmark_14b as benchmark  # noqa: E402


PROBE = ROOT / "scripts" / "evaluations" / "open_source_parser_eval" / "candidate_probe_14b.py"


def _run(
    command: list[str],
    *,
    env: dict[str, str],
    timeout: int,
) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            cwd=str(ROOT),
            env=env,
            check=False,
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "ok": completed.returncode == 0,
            "returncode": completed.returncode,
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            "stdout": str(benchmark.sanitize_artifact(completed.stdout))[-1200:],
            "stderr": str(benchmark.sanitize_artifact(completed.stderr))[-1200:],
        }
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "returncode": None,
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            "stdout": "",
            "stderr": "timeout",
        }


def _probe_command(
    parser_id: str,
    fixture: benchmark.BenchmarkFixture,
    output_path: Path,
    args: argparse.Namespace,
) -> tuple[list[str], dict[str, str]]:
    common = [
        str(PROBE),
        "--parser",
        parser_id,
        "--input",
        str(fixture.path),
        "--fixture-id",
        fixture.fixture_id,
        "--output",
        str(output_path),
        "--runtime-root",
        str(Path(args.runtime_root) / "probe-runtime" / parser_id),
    ]
    env = os.environ.copy()
    env.update(
        {
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "TOKENIZERS_PARALLELISM": "false",
            "PYTHONHASHSEED": "0",
        }
    )
    if parser_id == "baseline_native_tesseract_formula_region":
        return [args.project_python, *common], env
    if parser_id == "docling":
        env.update(
            {
                "HOME": str(Path(args.runtime_root) / "docling-home"),
                "XDG_CACHE_HOME": str(Path(args.runtime_root) / "docling-cache"),
            }
        )
        return [
            args.conda,
            "run",
            "-n",
            args.docling_env,
            "python",
            *common,
            "--model-root",
            args.docling_model_root,
        ], env
    env.update(
        {
            "HOME": args.mineru_home,
            "XDG_CACHE_HOME": args.mineru_cache,
            "HF_HOME": str(Path(args.mineru_cache) / "huggingface"),
            "MINERU_MODEL_SOURCE": "local",
            "MINERU_DEVICE_MODE": "cpu",
        }
    )
    return [args.conda, "run", "-n", args.mineru_env, "python", *common], env


def run_probe(
    parser_id: str,
    fixture: benchmark.BenchmarkFixture,
    args: argparse.Namespace,
) -> dict[str, Any]:
    output_path = Path(args.runtime_root) / "normalized" / parser_id / f"{fixture.fixture_id}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command, env = _probe_command(parser_id, fixture, output_path, args)
    process = _run(command, env=env, timeout=args.timeout_seconds)
    if output_path.exists():
        try:
            payload = json.loads(output_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            payload = {
                "parser_id": parser_id,
                "fixture_id": fixture.fixture_id,
                "blocks": [],
                "errors": [{"code": "PROBE_OUTPUT_INVALID", "message": str(exc)}],
            }
    else:
        payload = {
            "parser_id": parser_id,
            "fixture_id": fixture.fixture_id,
            "blocks": [],
            "errors": [
                {
                    "code": "PROBE_PROCESS_FAILED",
                    "message": process.get("stderr") or process.get("stdout") or "missing output",
                }
            ],
        }
    payload.setdefault("parse_duration_ms", process["duration_ms"])
    payload.setdefault("peak_rss_mb", 0)
    payload.setdefault("warnings", [])
    payload.setdefault("network", {"external_request_count": 0, "external_hosts": []})
    if int(payload["network"].get("external_request_count") or 0) > 0:
        payload.setdefault("errors", []).append(
            {"code": "EXTERNAL_NETWORK_OBSERVED", "message": "Parser emitted an external network endpoint."}
        )
    return payload


def _license_gate(parser_id: str) -> str:
    if parser_id in {"baseline_native_tesseract_formula_region", "docling"}:
        return "pass"
    if parser_id == "mineru":
        return "blocked_nonstandard_license"
    return "unknown"


def _fixture_manifest(fixtures: list[benchmark.BenchmarkFixture]) -> list[dict[str, Any]]:
    return [
        {
            "fixture_id": fixture.fixture_id,
            "filename": fixture.filename,
            "privacy_classification": fixture.privacy_classification,
            "language": fixture.language,
            "purpose": fixture.purpose,
            "page_count": _page_count(fixture.path),
            "source_hash": benchmark.sha256_file(fixture.path),
        }
        for fixture in fixtures
    ]


def _page_count(path: Path) -> int:
    import fitz

    with fitz.open(path) as document:
        return len(document)


def run_benchmark(args: argparse.Namespace) -> dict[str, Any]:
    runtime_root = Path(args.runtime_root)
    runtime_root.mkdir(parents=True, exist_ok=True)
    fixtures = benchmark.build_controlled_fixture_set(runtime_root / "fixtures")
    results: dict[tuple[str, str], dict[str, Any]] = {}
    document_scores: list[dict[str, Any]] = []
    for parser_id in benchmark.PARSER_IDS:
        for fixture in fixtures:
            result = run_probe(parser_id, fixture, args)
            results[(parser_id, fixture.fixture_id)] = result
            document_scores.append(benchmark.score_document(fixture, result))
            print(
                json.dumps(
                    {
                        "parser_id": parser_id,
                        "fixture_id": fixture.fixture_id,
                        "success": not bool(result.get("errors")),
                        "duration_ms": result.get("parse_duration_ms"),
                    },
                    sort_keys=True,
                ),
                flush=True,
            )

    retrieval: dict[str, dict[str, Any]] = {}
    for parser_id in benchmark.PARSER_IDS:
        english = results[(parser_id, "retrieval_english")]
        chinese = results[(parser_id, "retrieval_chinese")]
        parser_version = str(english.get("parser_version") or chinese.get("parser_version") or "")
        if english.get("errors") or chinese.get("errors"):
            retrieval[parser_id] = {
                **benchmark.rank_metrics({item.concept_id: [] for item in benchmark.RETRIEVAL_CONCEPTS}),
                "parser_id": parser_id,
                "parser_version": parser_version,
                "rankings": {item.concept_id: [] for item in benchmark.RETRIEVAL_CONCEPTS},
                "error": "retrieval_parse_input_unavailable",
                "external_api_used": False,
            }
            continue
        retrieval[parser_id] = benchmark.evaluate_downstream_retrieval(
            parser_id=parser_id,
            parser_version=parser_version,
            english_result=english,
            chinese_result=chinese,
            model_cache_dir=args.embedding_cache,
        )

    aggregates = [
        benchmark.aggregate_parser(
            parser_id,
            document_scores,
            retrieval[parser_id],
            license_gate=_license_gate(parser_id),
        )
        for parser_id in benchmark.PARSER_IDS
    ]
    selection = benchmark.select_candidate(aggregates)
    external_requests = sum(
        int((result.get("network") or {}).get("external_request_count") or 0)
        for result in results.values()
    )
    summary = {
        "task": "14B",
        "schema_version": benchmark.SCHEMA_VERSION,
        "created_at": benchmark.utc_now(),
        "baseline_commit": _git("rev-parse", "HEAD"),
        "branch": _git("branch", "--show-current"),
        "platform": {
            "system": platform.system(),
            "machine": platform.machine(),
            "python": sys.version.split()[0],
        },
        "fixture_count": len(fixtures),
        "fixtures": _fixture_manifest(fixtures),
        "document_scores": document_scores,
        "retrieval": retrieval,
        "aggregates": aggregates,
        "selection": selection,
        "safety": {
            "fixtures_private": False,
            "external_api_used": False,
            "external_parser_request_count": external_requests,
            "real_provider_requests": 0,
            "real_credentials_read": False,
            "production_parser_changed": False,
            "production_adapter_changed": False,
            "incident_database_accessed": False,
        },
    }
    output = Path(args.json_output)
    benchmark.write_json(output, summary)
    benchmark.write_metric_csv(Path(args.csv_output), document_scores)
    benchmark.write_json(
        Path(args.selection_output),
        {
            "task": "14B",
            "schema_version": "parser-selection-manifest-14b@1.0.0",
            "baseline_commit": summary["baseline_commit"],
            "parsers": [
                {
                    "parser_id": aggregate["parser_id"],
                    "parser_version": next(
                        (
                            result.get("parser_version")
                            for (candidate, _), result in results.items()
                            if candidate == aggregate["parser_id"] and result.get("parser_version")
                        ),
                        "",
                    ),
                    "license_gate": aggregate["license_gate"],
                }
                for aggregate in aggregates
            ],
            "selection": selection,
            "production_adapter_authorized": selection["production_adapter_authorized"],
        },
    )
    return summary


def _git(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=str(ROOT), check=True, capture_output=True, text=True
    )
    return completed.stdout.strip()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Task 14B controlled parser benchmark")
    parser.add_argument("--runtime-root", required=True)
    parser.add_argument("--project-python", required=True)
    parser.add_argument("--conda", default=shutil.which("conda") or "conda")
    parser.add_argument("--docling-env", default="lexibridge-eval-docling")
    parser.add_argument("--docling-model-root", required=True)
    parser.add_argument("--mineru-env", default="lexibridge-eval-mineru")
    parser.add_argument("--mineru-home", required=True)
    parser.add_argument("--mineru-cache", required=True)
    parser.add_argument("--embedding-cache", required=True)
    parser.add_argument("--json-output", required=True)
    parser.add_argument("--csv-output", required=True)
    parser.add_argument("--selection-output", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=300)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = run_benchmark(args)
    print(
        json.dumps(
            {
                "schema_version": summary["schema_version"],
                "fixture_count": summary["fixture_count"],
                "selected_parser_id": summary["selection"]["selected_parser_id"],
                "external_api_used": summary["safety"]["external_api_used"],
                "real_provider_requests": summary["safety"]["real_provider_requests"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
