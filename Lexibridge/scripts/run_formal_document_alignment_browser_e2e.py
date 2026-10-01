#!/usr/bin/env python3
"""Verify the formal workflow API from authenticated browser sessions."""

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
    assert_safe_public_payload,
    block_external_network,
    create_formal_source,
    poll_until_terminal,
    run_quiet_e2e_setup,
)


E2E_ENVIRONMENT_UNAVAILABLE = 2


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def build_browser_result(
    *,
    verdict: str,
    scenarios: list[dict[str, Any]],
    browser_version: str,
    console_errors: list[str],
    page_errors: list[str],
    external_requests: list[dict[str, Any]],
    blocking_failures: list[str] | None = None,
    message: str = "",
) -> dict[str, Any]:
    return {
        "verdict": verdict,
        "message": message,
        "browser": {
            "name": "chromium",
            "version": browser_version,
            "playwright_version": base_e2e.playwright_version(),
        },
        "scenarios": scenarios,
        "console_errors": console_errors,
        "page_errors": page_errors,
        "actual_external_dependency_requests": len(external_requests),
        "timeouts": [],
        "blocking_failures": list(blocking_failures or []),
        "generated_at": utc_now(),
    }


def _browser_fetch(page, path, *, method="GET", body=None, headers=None):
    return page.evaluate(
        """async ({path, method, body, headers}) => {
            const response = await fetch(path, {
                method,
                headers: {"Content-Type": "application/json", ...(headers || {})},
                body: body === null ? undefined : JSON.stringify(body)
            });
            let payload = {};
            try { payload = await response.json(); } catch (error) {}
            return {
                status: response.status,
                body: payload,
                headers: {
                    location: response.headers.get("Location"),
                    retry_after: response.headers.get("Retry-After"),
                    request_id: response.headers.get("X-Request-ID")
                }
            };
        }""",
        {"path": path, "method": method, "body": body, "headers": headers or {}},
    )


def _authenticated_headers(page, **headers):
    token = page.evaluate("() => localStorage.getItem('lexibridge_token') || ''")
    assert token
    return {"Authorization": f"Bearer {token}", **headers}


def _run_browser_checks(
    *,
    database: Path,
    uploads: Path,
    headed: bool,
    external_requests: list[dict[str, Any]],
) -> dict[str, Any]:
    base_e2e.assert_playwright_available()
    from playwright.sync_api import sync_playwright

    runtime = run_quiet_e2e_setup(
        base_e2e,
        database,
        uploads,
        "formal_browser_api_9c5g_v3",
    )
    module = runtime["app_module"]
    summary = runtime["summary"]
    with module.app.app_context():
        source = create_formal_source(
            module,
            suffix="browser",
            terms=("Encapsulation", "Coordination"),
            bilingual_terms={"Encapsulation": "封装", "Coordination": "协调"},
            owner_email=summary["users"]["teacher"]["email"],
            course_name=summary["course"],
        )

    port = base_e2e.find_free_port()
    server, thread = base_e2e.start_server(module, port)
    scenarios: list[dict[str, Any]] = []
    flow = base_e2e.flow_result("formal_browser_api")
    flow["status"] = "RUNNING"
    browser_version = ""
    contexts = []
    try:
        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch(headless=not headed)
            except Exception as exc:
                raise RuntimeError(
                    "E2E_ENVIRONMENT_UNAVAILABLE: Playwright Chromium runtime is not installed."
                ) from exc
            browser_version = browser.version
            try:
                teacher_context = browser.new_context()
                contexts.append(teacher_context)
                teacher_capture = base_e2e.FlowCapture(flow, external_requests, port)
                teacher_context.route("**/*", teacher_capture.route)
                teacher_page = teacher_context.new_page()
                teacher_capture.attach_page(teacher_page)
                base_e2e.open_frontend(teacher_page, port, flow)
                teacher = summary["users"]["teacher"]
                base_e2e.login(teacher_page, teacher["email"], teacher["password"], flow)
                headers = _authenticated_headers(
                    teacher_page,
                    **{
                        "Idempotency-Key": "browser-formal-api-9c5g-v3",
                        "X-Request-ID": "browser-formal-api-request-9c5g-v3",
                    },
                )
                started = _browser_fetch(
                    teacher_page,
                    "/api/document-alignment-runs",
                    method="POST",
                    body={"source_uid": source.source_uid},
                    headers=headers,
                )
                assert started["status"] == 202, started
                assert started["headers"]["location"] == started["body"]["data"]["status_url"]
                assert started["headers"]["retry_after"] == "2"
                assert started["headers"]["request_id"]
                run_uid = started["body"]["data"]["run_uid"]
                initial = _browser_fetch(
                    teacher_page,
                    started["headers"]["location"],
                    headers=_authenticated_headers(teacher_page),
                )
                assert initial["status"] == 200
                with module.app.app_context():
                    worker = module.run_formal_worker_once(worker_id="formal-browser-api-worker")
                    assert worker.outcome == "completed", worker

                pending = [initial["body"]]

                def fetch_run():
                    if pending:
                        return pending.pop()
                    response = _browser_fetch(
                        teacher_page,
                        started["headers"]["location"],
                        headers=_authenticated_headers(teacher_page),
                    )
                    assert response["status"] == 200
                    return response["body"]

                polled = poll_until_terminal(
                    fetch_run,
                    timeout_seconds=10,
                    poll_interval_seconds=0.05,
                )
                terminal = _browser_fetch(
                    teacher_page,
                    started["headers"]["location"],
                    headers=_authenticated_headers(teacher_page),
                )
                items = _browser_fetch(
                    teacher_page,
                    started["body"]["data"]["items_url"],
                    headers=_authenticated_headers(teacher_page),
                )
                assert terminal["status"] == items["status"] == 200
                assert terminal["body"]["data"]["status"] == "ready_for_review"
                assert {item["status"] for item in items["body"]["data"]["items"]} == {
                    "needs_review"
                }
                assert_safe_public_payload(started["body"])
                assert_safe_public_payload(terminal["body"])
                assert_safe_public_payload(items["body"])
                scenarios.append({
                    "name": "teacher_browser_api",
                    "status": "PASS",
                    "run_uid": run_uid,
                    "status_timeline": list(polled.timeline),
                    "terminal_status": terminal["body"]["data"]["status"],
                    "item_count": len(items["body"]["data"]["items"]),
                    "request_id_present": True,
                })

                student_context = browser.new_context()
                contexts.append(student_context)
                student_capture = base_e2e.FlowCapture(flow, external_requests, port)
                student_context.route("**/*", student_capture.route)
                student_page = student_context.new_page()
                student_capture.attach_page(student_page)
                base_e2e.open_frontend(student_page, port, flow)
                student = summary["users"]["student"]
                base_e2e.login(student_page, student["email"], student["password"], flow)
                student_headers = _authenticated_headers(student_page)
                student_denial_console_start = len(flow["console_errors"])
                denied = (
                    _browser_fetch(
                        student_page,
                        "/api/document-alignment-runs",
                        method="POST",
                        body={"source_uid": source.source_uid},
                        headers={**student_headers, "Idempotency-Key": "browser-student-denied"},
                    ),
                    _browser_fetch(
                        student_page,
                        f"/api/document-alignment-runs/{run_uid}",
                        headers=student_headers,
                    ),
                    _browser_fetch(
                        student_page,
                        f"/api/document-alignment-runs/{run_uid}/items",
                        headers=student_headers,
                    ),
                )
                assert [response["status"] for response in denied] == [403, 403, 403]
                for response in denied:
                    assert_safe_public_payload(response["body"])
                student_denial_console = flow["console_errors"][student_denial_console_start:]
                unexpected_student_console = [
                    message
                    for message in student_denial_console
                    if "403 (FORBIDDEN)" not in message
                ]
                flow["console_errors"] = (
                    flow["console_errors"][:student_denial_console_start]
                    + unexpected_student_console
                )
                scenarios.append({
                    "name": "student_browser_denial",
                    "status": "PASS",
                    "http_statuses": [403, 403, 403],
                })
            finally:
                for context in reversed(contexts):
                    context.close()
                browser.close()
    finally:
        server.shutdown()
        thread.join(timeout=5)

    external_dependency_requests = [
        item for item in external_requests if item.get("source") in {"page", "python"}
    ]
    verdict = (
        "PASS"
        if scenarios
        and not flow["console_errors"]
        and not flow["page_errors"]
        and not external_dependency_requests
        else "FAIL"
    )
    result = build_browser_result(
        verdict=verdict,
        scenarios=scenarios,
        browser_version=browser_version,
        console_errors=flow["console_errors"],
        page_errors=flow["page_errors"],
        external_requests=external_dependency_requests,
        blocking_failures=[] if verdict == "PASS" else ["FORMAL_BROWSER_API_E2E_FAILED"],
    )
    assert_safe_public_payload(result)
    return result


def run_browser_checks(
    *,
    database: Path,
    uploads: Path,
    headed: bool = False,
    external_requests: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    external_requests = external_requests if external_requests is not None else []
    with block_external_network(external_requests):
        return _run_browser_checks(
            database=database,
            uploads=uploads,
            headed=headed,
            external_requests=external_requests,
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-output", required=True)
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args(argv)

    base_dir = Path(tempfile.mkdtemp(prefix="lexibridge-formal-browser-api-e2e-"))
    uploads = base_dir / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    try:
        external_requests: list[dict[str, Any]] = []
        try:
            result = run_browser_checks(
                database=base_dir / "formal-browser-api.db",
                uploads=uploads,
                headed=args.headed,
                external_requests=external_requests,
            )
            exit_code = 0 if result["verdict"] == "PASS" else 1
        except RuntimeError as exc:
            unavailable = str(exc).startswith("E2E_ENVIRONMENT_UNAVAILABLE")
            result = build_browser_result(
                verdict="E2E_ENVIRONMENT_UNAVAILABLE" if unavailable else "FAIL",
                scenarios=[],
                browser_version="",
                console_errors=[],
                page_errors=[],
                external_requests=external_requests,
                blocking_failures=[type(exc).__name__],
                message=(
                    "Playwright Chromium runtime is unavailable."
                    if unavailable
                    else "Formal document alignment browser API E2E failed."
                ),
            )
            exit_code = E2E_ENVIRONMENT_UNAVAILABLE if unavailable else 1
        except Exception as exc:
            result = build_browser_result(
                verdict="FAIL",
                scenarios=[],
                browser_version="",
                console_errors=[],
                page_errors=[],
                external_requests=external_requests,
                blocking_failures=[type(exc).__name__],
                message="Formal document alignment browser API E2E failed.",
            )
            exit_code = 1
        assert_safe_public_payload(result)
        Path(args.json_output).write_text(
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return exit_code
    finally:
        shutil.rmtree(base_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
