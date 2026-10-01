#!/usr/bin/env python3
"""Verify refresh recovery for the formal workflow teacher UI."""

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


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def build_result(
    *,
    verdict: str,
    run_uid: str,
    formal_posts_before_reload: int,
    formal_posts_after_reload: int,
    storage_fields: list[str],
    console_errors: list[str],
    page_errors: list[str],
    external_requests: list[dict[str, Any]],
    blocking_failures: list[str] | None = None,
) -> dict[str, Any]:
    duplicate_posts = max(0, formal_posts_after_reload - formal_posts_before_reload)
    return {
        "verdict": verdict,
        "run_uid": run_uid,
        "same_run_restored": bool(run_uid) and duplicate_posts == 0,
        "formal_posts_before_reload": formal_posts_before_reload,
        "formal_posts_after_reload": formal_posts_after_reload,
        "duplicate_formal_posts": duplicate_posts,
        "stored_field_count": len(storage_fields),
        "console_errors": list(console_errors),
        "page_errors": list(page_errors),
        "actual_external_dependency_requests": len(external_requests),
        "timeouts": [],
        "blocking_failures": list(blocking_failures or []),
        "generated_at": utc_now(),
    }


def run_browser_checks(*, database: Path, uploads: Path, headed: bool = False) -> dict[str, Any]:
    base_e2e.assert_playwright_available()
    from playwright.sync_api import sync_playwright

    runtime = run_quiet_e2e_setup(base_e2e, database, uploads, "formal_frontend_resume_9c5h")
    module = runtime["app_module"]
    summary = runtime["summary"]
    with module.app.app_context():
        source = prepare_visible_formal_source(
            module,
            summary,
            suffix="ui-resume",
            terms=("Encapsulation", "Coordination"),
            bilingual_terms={"Encapsulation": "封装", "Coordination": "协调"},
        )

    port = base_e2e.find_free_port()
    server, thread = base_e2e.start_server(module, port)
    flow = base_e2e.flow_result("formal_frontend_resume")
    flow["status"] = "RUNNING"
    external_requests: list[dict[str, Any]] = []
    records: list[dict[str, str]] = []
    run_uid = ""
    post_count_before_reload = 0
    post_count_after_reload = 0
    storage_fields: list[str] = []
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
                start_source_from_ui(page, source)
                wait_for_request_count(
                    page,
                    records,
                    "/api/document-alignment-runs",
                    1,
                    method="POST",
                )
                with module.app.app_context():
                    run_uid = current_run_uid(module, source.source_uid)
                post_count_before_reload = request_count(
                    records, "/api/document-alignment-runs", "POST"
                )
                stored_run_uid = page.evaluate(
                    "() => JSON.parse(sessionStorage.getItem('lexibridge.formalAlignment.activeRun.v1')).run_uid"
                )
                assert stored_run_uid == run_uid
                page.reload(wait_until="domcontentloaded")
                page.get_by_test_id("formal-alignment-status").wait_for(
                    state="visible", timeout=10000
                )
                post_count_after_reload = request_count(
                    records, "/api/document-alignment-runs", "POST"
                )
                assert post_count_after_reload == post_count_before_reload
                restored_run_uid = page.evaluate(
                    "() => JSON.parse(sessionStorage.getItem('lexibridge.formalAlignment.activeRun.v1')).run_uid"
                )
                assert restored_run_uid == run_uid
                with module.app.app_context():
                    worker = module.run_formal_worker_once(worker_id="formal-ui-resume")
                    assert worker.outcome == "completed", worker
                page.get_by_test_id("formal-alignment-status").filter(
                    has_text="Ready for review"
                ).wait_for(state="visible", timeout=30000)
                page.wait_for_function(
                    "() => document.querySelectorAll('[data-testid=\"formal-alignment-items\"] .formal-alignment-item').length === 2",
                    timeout=10000,
                )
                storage_fields = assert_safe_browser_state(page, sentinel=SENTINEL)
            finally:
                context.close()
                browser.close()
    finally:
        server.shutdown()
        thread.join(timeout=5)

    unexpected_external = [item for item in external_requests if item.get("source") in {"page", "python"}]
    verdict = "PASS" if (
        bool(run_uid)
        and post_count_before_reload == post_count_after_reload == 1
        and not flow["console_errors"]
        and not flow["page_errors"]
        and not unexpected_external
        and request_count(records, "/api/alignment/run") == 0
    ) else "FAIL"
    return build_result(
        verdict=verdict,
        run_uid=run_uid,
        formal_posts_before_reload=post_count_before_reload,
        formal_posts_after_reload=post_count_after_reload,
        storage_fields=storage_fields,
        console_errors=flow["console_errors"],
        page_errors=flow["page_errors"],
        external_requests=unexpected_external,
        blocking_failures=[] if verdict == "PASS" else ["FORMAL_FRONTEND_RESUME_E2E_FAILED"],
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-output", required=True)
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args(argv)
    base_dir = Path(tempfile.mkdtemp(prefix="lexibridge-formal-frontend-resume-e2e-"))
    uploads = base_dir / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    try:
        try:
            result = run_browser_checks(
                database=base_dir / "formal-frontend-resume.db",
                uploads=uploads,
                headed=args.headed,
            )
        except Exception:
            result = build_result(
                verdict="FAIL",
                run_uid="",
                formal_posts_before_reload=0,
                formal_posts_after_reload=0,
                storage_fields=[],
                console_errors=[],
                page_errors=[],
                external_requests=[],
                blocking_failures=["FORMAL_FRONTEND_RESUME_E2E_FAILED"],
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
