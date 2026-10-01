#!/usr/bin/env python3
"""Verify the formal workflow through the real teacher UI."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from scripts import run_browser_e2e as base_e2e  # noqa: E402
from scripts.formal_document_alignment_api_e2e_support import (  # noqa: E402
    block_external_network,
    run_quiet_e2e_setup,
)
from scripts.formal_workflow_frontend_e2e_support import (  # noqa: E402
    SENTINEL,
    assert_safe_browser_state,
    attach_request_log,
    current_run_uid,
    open_teacher_upload,
    prepare_visible_formal_source,
    request_count,
    start_source_from_ui,
    wait_for_request_count,
)


PAGINATION_TERMS = (
    "Abstraction", "Approximation", "Calibration", "Classification", "Computation",
    "Correlation", "Definition", "Demodulation", "Differentiation", "Estimation",
    "Formation", "Generation", "Integration", "Interpolation", "Modulation",
    "Normalization", "Optimization", "Prediction", "Quantization", "Regularization",
    "Representation", "Segmentation", "Simulation", "Synchronization", "Transformation",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def build_result(
    *,
    verdict: str,
    scenarios: list[dict[str, Any]],
    console_errors: list[str],
    page_errors: list[str],
    external_requests: list[dict[str, Any]],
    formal_posts: int,
    legacy_requests: int,
    duplicate_posts: int,
    blocking_failures: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "verdict": verdict,
        "scenarios": scenarios,
        "formal_post_count": formal_posts,
        "legacy_alignment_requests": legacy_requests,
        "duplicate_formal_posts": duplicate_posts,
        "console_errors": list(console_errors),
        "page_errors": list(page_errors),
        "actual_external_dependency_requests": len(external_requests),
        "timeouts": [],
        "blocking_failures": list(blocking_failures or []),
        "generated_at": utc_now(),
    }


def _run_scenario(
    page,
    module,
    source,
    records,
    *,
    expected_status: str,
    expected_label: str,
    minimum_items: int,
    duplicate_click: bool = False,
) -> dict[str, Any]:
    before = request_count(records, "/api/document-alignment-runs", "POST")
    start_source_from_ui(page, source, duplicate_click=duplicate_click)
    wait_for_request_count(
        page,
        records,
        "/api/document-alignment-runs",
        before + 1,
        method="POST",
    )
    with module.app.app_context():
        run_uid = current_run_uid(module, source.source_uid)
        worker = module.run_formal_worker_once(worker_id=f"formal-ui-{expected_status}")
        assert worker.outcome == "completed", worker
        run = module.DocumentAlignmentWorkflowRun.query.filter_by(run_uid=run_uid).one()
        job = module.BackgroundJob.query.filter(
            module.BackgroundJob.input_json.like(f"%{run_uid}%")
        ).one()
        actual_items = int(run.total_items or 0)
        assert run.status == expected_status
        assert job.status == "completed"
        assert actual_items >= minimum_items
    page.get_by_test_id("formal-alignment-status").filter(
        has_text=expected_label
    ).wait_for(state="visible", timeout=30000)
    items = page.locator('[data-testid="formal-alignment-items"] .formal-alignment-item')
    page.wait_for_function(
        "expected => document.querySelectorAll('[data-testid=\"formal-alignment-items\"] .formal-alignment-item').length === expected",
        arg=min(20, actual_items),
        timeout=10000,
    )
    if actual_items > 20:
        assert items.count() == 20
        page.get_by_test_id("formal-alignment-next").click()
        page.wait_for_function(
            "expected => document.querySelectorAll('[data-testid=\"formal-alignment-items\"] .formal-alignment-item').length === expected",
            arg=min(20, actual_items - 20),
            timeout=10000,
        )
        assert page.get_by_test_id("formal-alignment-prev").is_enabled()
    return {
        "name": expected_status,
        "status": "PASS",
        "run_uid": run_uid,
        "terminal_status": expected_status,
        "item_count": actual_items,
    }


def run_browser_checks(*, database: Path, uploads: Path, headed: bool = False) -> dict[str, Any]:
    base_e2e.assert_playwright_available()
    from playwright.sync_api import sync_playwright

    runtime = run_quiet_e2e_setup(base_e2e, database, uploads, "formal_frontend_9c5h")
    module = runtime["app_module"]
    summary = runtime["summary"]
    with module.app.app_context():
        success = prepare_visible_formal_source(
            module,
            summary,
            suffix="ui-success",
            terms=PAGINATION_TERMS,
            bilingual_terms={term: f"课程术语{index:02d}" for index, term in enumerate(PAGINATION_TERMS)},
        )
        partial = prepare_visible_formal_source(
            module,
            summary,
            suffix="ui-partial",
            terms=("Fourier Transform", "Unmapped Course Term"),
            bilingual_terms={"Fourier Transform": "傅里叶变换"},
        )
        blocked = prepare_visible_formal_source(
            module,
            summary,
            suffix="ui-blocked",
            terms=("Unmapped Term Alpha", "Unmapped Term Beta"),
            bilingual_terms={},
        )

    port = base_e2e.find_free_port()
    server, thread = base_e2e.start_server(module, port)
    flow = base_e2e.flow_result("formal_frontend")
    flow["status"] = "RUNNING"
    external_requests: list[dict[str, Any]] = []
    scenarios: list[dict[str, Any]] = []
    records: list[dict[str, str]] = []
    try:
        with block_external_network(external_requests), sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=not headed)
            context = browser.new_context()
            capture = base_e2e.FlowCapture(flow, external_requests, port)
            context.route("**/*", capture.route)
            page = context.new_page()
            capture.attach_page(page)
            records = attach_request_log(page)
            try:
                open_teacher_upload(
                    base_e2e,
                    page,
                    port,
                    flow,
                    summary["users"]["teacher"],
                )
                scenarios.append(_run_scenario(
                    page,
                    module,
                    success,
                    records,
                    expected_status="ready_for_review",
                    expected_label="Ready for review",
                    minimum_items=len(PAGINATION_TERMS),
                    duplicate_click=True,
                ))
                scenarios.append(_run_scenario(
                    page,
                    module,
                    partial,
                    records,
                    expected_status="completed_with_warnings",
                    expected_label="Completed with warnings",
                    minimum_items=2,
                ))
                assert "system processing failed" not in page.locator("body").inner_text().casefold()
                scenarios.append(_run_scenario(
                    page,
                    module,
                    blocked,
                    records,
                    expected_status="blocked",
                    expected_label="Blocked",
                    minimum_items=0,
                ))
                assert_safe_browser_state(page, sentinel=SENTINEL)
            finally:
                context.close()
                browser.close()
    finally:
        server.shutdown()
        thread.join(timeout=5)

    formal_posts = request_count(records, "/api/document-alignment-runs", "POST")
    legacy_requests = request_count(records, "/api/alignment/run")
    duplicate_posts = max(0, formal_posts - len(scenarios))
    unexpected_external = [item for item in external_requests if item.get("source") in {"page", "python"}]
    verdict = "PASS" if (
        len(scenarios) == 3
        and not flow["console_errors"]
        and not flow["page_errors"]
        and not unexpected_external
        and legacy_requests == 0
        and duplicate_posts == 0
    ) else "FAIL"
    return build_result(
        verdict=verdict,
        scenarios=scenarios,
        console_errors=flow["console_errors"],
        page_errors=flow["page_errors"],
        external_requests=unexpected_external,
        formal_posts=formal_posts,
        legacy_requests=legacy_requests,
        duplicate_posts=duplicate_posts,
        blocking_failures=[] if verdict == "PASS" else ["FORMAL_FRONTEND_UI_E2E_FAILED"],
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-output", required=True)
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args(argv)
    base_dir = Path(tempfile.mkdtemp(prefix="lexibridge-formal-frontend-e2e-"))
    uploads = base_dir / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    try:
        try:
            result = run_browser_checks(
                database=base_dir / "formal-frontend.db",
                uploads=uploads,
                headed=args.headed,
            )
        except Exception:
            result = build_result(
                verdict="FAIL",
                scenarios=[],
                console_errors=[],
                page_errors=[],
                external_requests=[],
                formal_posts=0,
                legacy_requests=0,
                duplicate_posts=0,
                blocking_failures=["FORMAL_FRONTEND_UI_E2E_FAILED"],
            )
        Path(args.json_output).write_text(
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result["verdict"] == "PASS" else 1
    finally:
        shutil.rmtree(base_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
