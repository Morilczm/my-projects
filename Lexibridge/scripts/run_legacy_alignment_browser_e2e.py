#!/usr/bin/env python3
"""Run browser checks for the legacy alignment compatibility endpoint."""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / "backend" / ".venv-macos" / "bin" / "python"
E2E_ENVIRONMENT_UNAVAILABLE = 2


def load_browser_runner():
    spec = importlib.util.spec_from_file_location("lexibridge_browser_e2e_base", ROOT / "scripts" / "run_browser_e2e.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


base_e2e = load_browser_runner()


def build_alignment_result(
    *,
    browser_version: str = "",
    local_flow: dict[str, Any] | None = None,
    external_blocked_flow: dict[str, Any] | None = None,
    blocked_external_requests: list[dict[str, Any]] | None = None,
    artifacts_directory: str | None = None,
    status: str | None = None,
    message: str = "",
) -> dict[str, Any]:
    local_flow = local_flow or base_e2e.flow_result("legacy_alignment_local")
    external_blocked_flow = external_blocked_flow or base_e2e.flow_result("legacy_alignment_external_blocked")
    blocked_external_requests = blocked_external_requests or []
    external_dependencies = [item for item in blocked_external_requests if item.get("source") == "page"]
    if status is None:
        requested_flows = [local_flow, external_blocked_flow]
        status = (
            "PASS"
            if all(flow.get("status") == "PASS" and not base_e2e.flow_has_failures(flow, external_dependencies) for flow in requested_flows)
            and not external_dependencies
            else "FAIL"
        )
    return {
        "status": status,
        "message": message,
        "browser": {
            "name": "chromium",
            "version": browser_version,
            "playwright_version": base_e2e.playwright_version(),
        },
        "legacy_alignment_local_flow": local_flow,
        "legacy_alignment_external_blocked_flow": external_blocked_flow,
        "blocked_external_requests": blocked_external_requests,
        "external_dependency_requests": external_dependencies,
        "artifacts_directory": artifacts_directory,
        "generated_at": base_e2e.utc_now(),
    }


def fetch_json(page, path: str, *, token: str | None = None, payload: dict[str, Any] | None = None, method: str = "GET") -> dict[str, Any]:
    return page.evaluate(
        """async ({path, token, payload, method}) => {
            const headers = {"Content-Type": "application/json"};
            if (token) headers.Authorization = `Bearer ${token}`;
            const response = await fetch(path, {
                method,
                headers,
                body: payload === null ? undefined : JSON.stringify(payload)
            });
            let body = null;
            try {
                body = await response.json();
            } catch (error) {
                body = {parse_error: String(error)};
            }
            return {status: response.status, body};
        }""",
        {"path": path, "token": token, "payload": payload, "method": method},
    )


def login_for_token(page, summary: dict[str, Any], flow: dict[str, Any]) -> str:
    teacher = summary["users"]["teacher"]
    login = fetch_json(
        page,
        "/api/auth/login",
        method="POST",
        payload={"email": teacher["email"], "password": teacher["password"]},
    )
    assert login["status"] == 200, login
    token = str(login["body"]["token"])
    base_e2e.add_step(flow, "login")
    return token


def run_local_flow(page, runtime: dict[str, Any], flow: dict[str, Any], port: int) -> None:
    app_module = runtime["app_module"]
    summary = runtime["summary"]
    with app_module.app.app_context():
        course = app_module.Course.query.filter_by(name=summary["course"]).first()
        assert course is not None
        course_id = course.id
    page.goto(f"http://127.0.0.1:{port}/e2e", wait_until="domcontentloaded")
    base_e2e.add_step(flow, "open page")
    token = login_for_token(page, summary, flow)
    response = fetch_json(
        page,
        "/api/alignment/run",
        token=token,
        method="POST",
        payload={
            "scope_type": "course",
            "course_id": course_id,
            "english_term": "Legacy alignment browser local flow",
            "courseware_sentence": "Local deterministic compatibility flow remains queued.",
            "provider": "mock",
        },
    )
    assert response["status"] == 200, response
    body = response["body"]
    assert body["status"] == "success", body
    job_id = body["data"]["job_id"]
    assert body["data"]["job_status"] == "queued", body
    base_e2e.add_step(flow, "local route returned queued job")
    with app_module.app.app_context():
        processed = app_module.run_background_job(job_id, worker_id="legacy-alignment-browser-e2e")
        assert processed.status == "completed"
    job_response = fetch_json(page, f"/api/jobs/{job_id}", token=token)
    assert job_response["status"] == 200, job_response
    assert job_response["body"]["data"]["job"]["status"] == "completed", job_response
    base_e2e.add_step(flow, "local worker completed job")


def run_external_blocked_flow(page, runtime: dict[str, Any], flow: dict[str, Any], port: int) -> None:
    app_module = runtime["app_module"]
    summary = runtime["summary"]
    with app_module.app.app_context():
        course = app_module.Course.query.filter_by(name=summary["course"]).first()
        assert course is not None
        course_id = course.id
        before = {
            "alignment_runs": app_module.AlignmentRun.query.count(),
            "background_jobs": app_module.BackgroundJob.query.count(),
            "terminology_cards": app_module.TerminologyCard.query.count(),
            "usage_records": app_module.UsageRecord.query.count(),
            "ai_call_logs": app_module.AICallLog.query.count(),
        }
    page.goto(f"http://127.0.0.1:{port}/e2e", wait_until="domcontentloaded")
    base_e2e.add_step(flow, "open page")
    token = login_for_token(page, summary, flow)
    response = fetch_json(
        page,
        "/api/alignment/run",
        token=token,
        method="POST",
        payload={
            "scope_type": "course",
            "course_id": course_id,
            "english_term": "Legacy alignment browser external blocked flow",
            "courseware_sentence": "External compatibility path must be blocked.",
            "provider": "deepseek",
            "provider_mode": "live",
            "base_url": "https://example.invalid/browser-e2e-legacy-alignment",
        },
    )
    assert response["status"] == 422, response
    body = response["body"]
    assert body["status"] == "error", body
    assert body["error_code"] == "LEGACY_ALIGNMENT_EXTERNAL_EXECUTION_DISABLED", body
    assert "LEGACY_ALIGNMENT_RUN_DEPRECATED" not in json.dumps(body)
    page.wait_for_timeout(100)
    flow["console_errors"] = [
        message
        for message in flow["console_errors"]
        if "422" not in message and "UNPROCESSABLE ENTITY" not in message
    ]
    base_e2e.add_step(flow, "external route returned safe blocked result")
    with app_module.app.app_context():
        after = {
            "alignment_runs": app_module.AlignmentRun.query.count(),
            "background_jobs": app_module.BackgroundJob.query.count(),
            "terminology_cards": app_module.TerminologyCard.query.count(),
            "usage_records": app_module.UsageRecord.query.count(),
            "ai_call_logs": app_module.AICallLog.query.count(),
        }
    assert after == before, (before, after)
    base_e2e.add_step(flow, "external blocked path created no legacy records")


def run_browser_checks(*, base_dir: Path, artifact_dir: Path, headed: bool = False) -> dict[str, Any]:
    base_e2e.assert_playwright_available()
    from playwright.sync_api import sync_playwright

    database = base_dir / "legacy-alignment-e2e.db"
    uploads = base_dir / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    runtime = base_e2e.run_setup(database, uploads, "legacy_alignment")
    port = base_e2e.find_free_port()
    server, thread = base_e2e.start_server(runtime["app_module"], port)
    blocked_external_requests: list[dict[str, Any]] = []
    local_flow = base_e2e.flow_result("legacy_alignment_local")
    external_blocked_flow = base_e2e.flow_result("legacy_alignment_external_blocked")
    local_flow["status"] = "RUNNING"
    external_blocked_flow["status"] = "RUNNING"
    browser_version = ""
    try:
        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch(headless=not headed)
            except Exception as exc:
                raise RuntimeError(
                    "E2E_ENVIRONMENT_UNAVAILABLE: Playwright Chromium runtime is not installed. "
                    "Run `python -m playwright install chromium` in the project environment."
                ) from exc
            browser_version = browser.version
            context = browser.new_context()
            capture = base_e2e.FlowCapture(local_flow, blocked_external_requests, port)
            context.route("**/*", capture.route)
            try:
                page = context.new_page()
                capture.attach_page(page)
                try:
                    run_local_flow(page, runtime, local_flow, port)
                except Exception as exc:
                    base_e2e.add_step(local_flow, "local flow failed", "FAIL", str(exc))
                    try:
                        artifact_dir.mkdir(parents=True, exist_ok=True)
                        page.screenshot(path=str(artifact_dir / "legacy-alignment-local-failure.png"), full_page=True)
                    except Exception:
                        pass
                local_flow["status"] = "FAIL" if base_e2e.flow_has_failures(local_flow, []) else "PASS"

                external_blocked_capture = base_e2e.FlowCapture(external_blocked_flow, blocked_external_requests, port)
                context.unroute("**/*", capture.route)
                context.route("**/*", external_blocked_capture.route)
                page = context.new_page()
                external_blocked_capture.attach_page(page)
                try:
                    run_external_blocked_flow(page, runtime, external_blocked_flow, port)
                except Exception as exc:
                    base_e2e.add_step(external_blocked_flow, "external blocked flow failed", "FAIL", str(exc))
                    try:
                        artifact_dir.mkdir(parents=True, exist_ok=True)
                        page.screenshot(path=str(artifact_dir / "legacy-alignment-external-blocked-failure.png"), full_page=True)
                    except Exception:
                        pass
                external_blocked_flow["status"] = "FAIL" if base_e2e.flow_has_failures(external_blocked_flow, []) else "PASS"
            finally:
                context.close()
                browser.close()
    finally:
        server.shutdown()
        thread.join(timeout=5)

    return build_alignment_result(
        browser_version=browser_version,
        local_flow=local_flow,
        external_blocked_flow=external_blocked_flow,
        blocked_external_requests=blocked_external_requests,
        artifacts_directory=str(artifact_dir),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run legacy alignment browser compatibility checks.")
    parser.add_argument("--json-output", help="Write machine-readable result JSON.")
    parser.add_argument("--headed", action="store_true", help="Run Chromium headed for local debugging.")
    parser.add_argument("--keep-artifacts", action="store_true", help="Keep temp DB/uploads/screenshots after success.")
    parser.add_argument("--artifacts", help="Optional artifact directory for screenshots.")
    args = parser.parse_args(argv)

    base_dir = Path(tempfile.mkdtemp(prefix="lexibridge-legacy-alignment-e2e-"))
    artifact_dir = Path(args.artifacts).resolve() if args.artifacts else base_dir / "artifacts"
    try:
        try:
            result = run_browser_checks(base_dir=base_dir, artifact_dir=artifact_dir, headed=args.headed)
            exit_code = 0 if result["status"] == "PASS" else 1
        except RuntimeError as exc:
            if str(exc).startswith("E2E_ENVIRONMENT_UNAVAILABLE"):
                result = build_alignment_result(
                    status="E2E_ENVIRONMENT_UNAVAILABLE",
                    message=str(exc),
                    artifacts_directory=str(artifact_dir),
                )
                exit_code = E2E_ENVIRONMENT_UNAVAILABLE
            else:
                result = build_alignment_result(status="FAIL", message=str(exc), artifacts_directory=str(artifact_dir))
                exit_code = 1
        except Exception as exc:
            result = build_alignment_result(status="FAIL", message=str(exc), artifacts_directory=str(artifact_dir))
            exit_code = 1

        if result["status"] == "PASS" and not args.keep_artifacts:
            result["artifacts_directory"] = None
        if args.json_output:
            Path(args.json_output).write_text(
                json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return exit_code
    finally:
        if not args.keep_artifacts:
            if "result" not in locals() or result.get("status") == "PASS":
                shutil.rmtree(base_dir, ignore_errors=True)
                if args.artifacts:
                    shutil.rmtree(artifact_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
