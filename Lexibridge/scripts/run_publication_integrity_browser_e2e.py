#!/usr/bin/env python3
"""Run 11D browser E2E checks for publication integrity and provenance."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import run_browser_e2e as base_e2e  # noqa: E402

E2E_ENVIRONMENT_UNAVAILABLE = base_e2e.E2E_ENVIRONMENT_UNAVAILABLE


def _build_result(
    *,
    scenario: dict[str, Any] | None = None,
    blocked_external_requests: list[dict[str, Any]] | None = None,
    artifacts_directory: str | None = None,
    browser_version: str = "",
    status: str | None = None,
    message: str = "",
) -> dict[str, Any]:
    scenario = scenario or base_e2e.flow_result("publication_integrity")
    blocked_external_requests = blocked_external_requests or []
    external_dependencies = [item for item in blocked_external_requests if item.get("source") == "page"]
    if status is None:
        status = "PASS" if scenario.get("status") == "PASS" and not external_dependencies else "FAIL"
    return {
        "status": status,
        "message": message,
        "browser": {
            "name": "chromium",
            "version": browser_version,
            "playwright_version": base_e2e.playwright_version(),
        },
        "scenario": scenario,
        "blocked_external_requests": blocked_external_requests,
        "external_dependency_requests": external_dependencies,
        "artifacts_directory": artifacts_directory,
        "generated_at": base_e2e.utc_now(),
    }


def _browser_fetch(page, path: str, *, method: str = "GET", body: dict[str, Any] | None = None) -> dict[str, Any]:
    return page.evaluate(
        """async ([path, method, body]) => {
            const token = localStorage.getItem('lexibridge_token') || '';
            const response = await fetch(path, {
                method,
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`,
                    'X-Request-ID': `browser-11d-${Math.random().toString(16).slice(2)}`
                },
                body: body ? JSON.stringify(body) : undefined
            });
            let payload = {};
            try { payload = await response.json(); } catch (error) { payload = { message: response.statusText }; }
            return { status: response.status, payload };
        }""",
        arg=[path, method, body],
    )


def _local_api_request(
    *,
    port: int,
    token: str,
    path: str,
    method: str = "GET",
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=payload,
        method=method,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "X-Request-ID": "browser-11d-local-api-check",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            response_body = response.read().decode("utf-8")
            return {"status": response.status, "payload": json.loads(response_body)}
    except urllib.error.HTTPError as exc:
        response_body = exc.read().decode("utf-8")
        try:
            payload_obj: dict[str, Any] = json.loads(response_body)
        except json.JSONDecodeError:
            payload_obj = {"message": response_body}
        return {"status": exc.code, "payload": payload_obj}


def _run_checks(*, base_dir: Path, artifact_dir: Path, headed: bool = False) -> dict[str, Any]:
    base_e2e.assert_playwright_available()
    from playwright.sync_api import sync_playwright

    database = base_dir / "publication-integrity.db"
    uploads = base_dir / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    runtime = base_e2e.run_setup(database, uploads, "publication_integrity")
    port = base_e2e.find_free_port()
    server, thread = base_e2e.start_server(runtime["app_module"], port)
    blocked_external_requests: list[dict[str, Any]] = []
    flow = base_e2e.flow_result("publication_integrity")
    flow["status"] = "RUNNING"
    browser_version = ""

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=not headed)
        except Exception as exc:
            server.shutdown()
            thread.join(timeout=5)
            raise RuntimeError(
                "E2E_ENVIRONMENT_UNAVAILABLE: Playwright Chromium runtime is not installed. "
                "Run `python -m playwright install chromium` in the project environment."
            ) from exc
        browser_version = browser.version
        teacher_context = None
        admin_context = None
        student_context = None
        try:
            teacher_context = browser.new_context(accept_downloads=True)
            admin_context = browser.new_context(accept_downloads=True)
            student_context = browser.new_context(accept_downloads=True)
            teacher_capture = base_e2e.FlowCapture(flow, blocked_external_requests, port)
            admin_capture = base_e2e.FlowCapture(flow, blocked_external_requests, port)
            student_capture = base_e2e.FlowCapture(flow, blocked_external_requests, port)
            teacher_context.route("**/*", teacher_capture.route)
            admin_context.route("**/*", admin_capture.route)
            student_context.route("**/*", student_capture.route)
            teacher_page = teacher_context.new_page()
            admin_page = admin_context.new_page()
            student_page = student_context.new_page()
            teacher_capture.attach_page(teacher_page)
            admin_capture.attach_page(admin_page)
            student_capture.attach_page(student_page)
            summary = runtime["summary"]
            teacher = summary["users"]["teacher"]
            admin = summary["users"]["admin"]
            student = summary["users"]["student"]

            base_e2e.open_frontend(teacher_page, port, flow)
            base_e2e.login(teacher_page, teacher["email"], teacher["password"], flow)
            teacher_page.locator('[data-testid="concept-review-nav"]').first.click()
            base_e2e.expect_visible(teacher_page, '[data-testid="review-queue"]', "teacher review queue visible", flow)
            teacher_page.locator('[data-testid="review-filter-course"]').fill("DEMO Signals and Systems")
            teacher_page.locator("form").filter(has=teacher_page.locator('[data-testid="review-filter-course"]')).locator("button").first.click()
            base_e2e.expect_visible(teacher_page, '[data-testid="review-card-row"]', "teacher review row visible", flow)
            teacher_page.locator('[data-testid="review-card-row"]', has_text="Fourier transform").first.click()
            base_e2e.expect_visible(teacher_page, '[data-testid="review-card-detail"]', "teacher review detail visible", flow)
            base_e2e.expect_visible(teacher_page, '[data-testid="evidence-provenance"]', "teacher provenance visible", flow)
            assert "bbox" in teacher_page.locator('[data-testid="english-evidence-list"]').inner_text()
            base_e2e.add_step(flow, "teacher evidence provenance shows page/bbox availability")

            queue_response = _browser_fetch(
                teacher_page,
                "/api/concept-cards/review-queue?course=DEMO%20Signals%20and%20Systems&page=1&per_page=20",
            )
            assert queue_response["status"] == 200, queue_response
            stale_card = next(
                item for item in queue_response["payload"]["data"]["items"]
                if item.get("english_term") == "Fourier transform"
            )
            stale_token = stale_card.get("review_token") or stale_card.get("version")
            patch = _browser_fetch(
                teacher_page,
                f"/api/concept-cards/{stale_card['card_uid']}",
                method="PATCH",
                body={
                    "expected_version": stale_token,
                    "english_explanation": "Browser client B updated this card before stale approval.",
                },
            )
            assert patch["status"] == 200, patch
            approve = teacher_page.locator('[data-testid="review-action-approve"]').first
            approve.locator('textarea[name="review_comment"]').fill("Browser stale approve should fail.")
            approve.locator('[data-testid="review-submit"]').click()
            base_e2e.expect_visible(teacher_page, '[data-testid="review-error"]', "stale review error visible", flow)
            teacher_page.wait_for_function(
                """() => document.querySelector('[data-testid="review-error"]')?.innerText.includes('CONCEPT_CARD_STALE_REVIEW')
                    || document.querySelector('[data-testid="review-error"]')?.innerText.includes('concept_card_stale_review')""",
                timeout=10000,
            )
            base_e2e.add_step(flow, "stale review conflict surfaced in browser")

            base_e2e.open_frontend(admin_page, port, flow)
            base_e2e.login(admin_page, admin["email"], admin["password"], flow)
            admin_page.locator('[data-testid="concept-review-nav"]').first.click()
            base_e2e.expect_visible(admin_page, '[data-testid="review-queue"]', "admin review queue visible", flow)
            admin_page.locator('[data-testid="review-filter-course"]').fill("DEMO Signals and Systems")
            admin_page.locator("form").filter(has=admin_page.locator('[data-testid="review-filter-course"]')).locator("button").first.click()
            base_e2e.expect_visible(admin_page, '[data-testid="review-card-row"]', "admin review row visible", flow)
            admin_page.evaluate("uid => window.Lexi.selectReviewCard(uid)", arg=stale_card["card_uid"])
            base_e2e.expect_visible(admin_page, '[data-testid="review-card-detail"]', "admin card detail visible", flow)
            admin_detail = _browser_fetch(admin_page, f"/api/concept-cards/{stale_card['card_uid']}")
            assert admin_detail["status"] == 200, admin_detail
            current_token = str(admin_detail["payload"]["data"]["card"].get("review_token") or "")
            approve = admin_page.locator('[data-testid="review-action-approve"]').first
            hidden_token = approve.locator('[data-testid="review-expected-version"]').input_value()
            base_e2e.add_step(
                flow,
                "admin current review token loaded",
                "PASS" if hidden_token == current_token else "FAIL",
                f"api_token={current_token}; hidden_token={hidden_token}",
            )
            approve.locator('textarea[name="review_comment"]').fill("Browser admin approves after stale conflict reload.")
            override = approve.locator('input[name="allow_risk_override"]')
            if override.count():
                override.check()
                approve.locator('textarea[name="override_reason"]').fill("Browser E2E admin verified synthetic evidence.")
                approve.locator('input[name="resolved_risk_labels"]').fill("bilingual_alignment_not_verified")
            with admin_page.expect_response(
                lambda response: response.url.endswith(f"/api/concept-cards/{stale_card['card_uid']}/review")
                and response.request.method == "POST"
            ) as review_response_info:
                approve.locator('[data-testid="review-submit"]').click()
            review_response = review_response_info.value
            review_payload = review_response.json()
            base_e2e.add_step(
                flow,
                "admin approve response",
                "PASS" if review_response.status == 200 else "FAIL",
                f"status={review_response.status}; error_code={review_payload.get('error_code', '')}",
            )
            base_e2e.expect_visible(admin_page, '[data-testid="review-success"]', "approval after reload succeeds", flow)
            approved_uid = stale_card["card_uid"]
            base_e2e.add_step(flow, "teacher approval succeeds after reload")

            base_e2e.open_frontend(student_page, port, flow)
            base_e2e.login(student_page, student["email"], student["password"], flow)
            student_page.locator('[data-testid="student-concept-card-nav"]').first.click()
            base_e2e.expect_visible(student_page, '[data-testid="student-concept-card-page"]', "student card page visible", flow)
            base_e2e.expect_visible(student_page, '[data-testid="student-card-row"]', "student approved card visible", flow)
            student_page.evaluate("uid => window.Lexi.selectStudentConceptCard(uid)", arg=approved_uid)
            base_e2e.expect_visible(student_page, '[data-testid="student-card-detail"]', "student approved detail visible", flow)
            base_e2e.expect_visible(student_page, '[data-testid="student-english-evidence-items"] [data-testid="evidence-provenance"]', "student provenance visible", flow)
            feedback = student_page.locator('[data-testid="student-feedback-form"]')
            feedback.locator('textarea[name="message"]').fill("Publication integrity browser feedback.")
            feedback.locator('[data-testid="student-feedback-submit"]').click()
            base_e2e.expect_visible(student_page, '[data-testid="student-card-success"]', "student feedback submitted", flow)
            base_e2e.add_step(flow, "student feedback submitted through page")

            detail_response = _browser_fetch(student_page, f"/api/student/concept-cards/{approved_uid}")
            assert detail_response["status"] == 200, detail_response
            card_detail = detail_response["payload"]["data"]["card"]
            source_uid = (card_detail.get("chinese_evidence") or card_detail.get("english_evidence") or [{}])[0].get("source_uid")
            assert source_uid, card_detail
            withdrawn = _browser_fetch(admin_page, f"/api/knowledge-sources/{source_uid}", method="PATCH", body={"status": "deprecated"})
            assert withdrawn["status"] == 200, withdrawn
            student_page.locator('[data-testid="student-concept-card-page"] button', has_text="刷新").first.click()
            student_page.wait_for_function(
                """cardUid => !Array.from(document.querySelectorAll('[data-testid="student-card-row"]'))
                    .some(row => row.getAttribute('onclick')?.includes(cardUid))""",
                arg=approved_uid,
                timeout=10000,
            )
            student_token = student_page.evaluate("() => localStorage.getItem('lexibridge_token') || ''")
            detail_after_withdrawal = _local_api_request(
                port=port,
                token=student_token,
                path=f"/api/student/concept-cards/{approved_uid}",
            )
            assert detail_after_withdrawal["status"] == 404, detail_after_withdrawal
            feedback_after_withdrawal = _local_api_request(
                port=port,
                token=student_token,
                path=f"/api/student/concept-cards/{approved_uid}/feedback",
                method="POST",
                body={"feedback_type": "other", "message": "Should be rejected after source withdrawal."},
            )
            assert feedback_after_withdrawal["status"] == 404, feedback_after_withdrawal
            base_e2e.add_step(flow, "withdrawn source hides card and blocks feedback")

            admin_page.locator('[data-testid="review-filter-status"]').select_option("approved")
            admin_page.locator('[data-testid="review-filter-course"]').fill("DEMO Signals and Systems")
            admin_page.locator("form").filter(has=admin_page.locator('[data-testid="review-filter-course"]')).locator("button").first.click()
            base_e2e.expect_visible(admin_page, '[data-testid="review-card-row"]', "approved history row visible after withdrawal", flow)
            admin_page.evaluate("uid => window.Lexi.selectReviewCard(uid)", arg=approved_uid)
            base_e2e.expect_visible(admin_page, '[data-testid="source-unavailable-warning"]', "teacher source unavailable warning visible", flow)
            base_e2e.add_step(flow, "teacher historical card shows unavailable source warning")
        except Exception as exc:
            base_e2e.add_step(flow, "publication integrity browser flow failed", "FAIL", str(exc))
            artifact_dir.mkdir(parents=True, exist_ok=True)
            try:
                teacher_page.screenshot(path=str(artifact_dir / "publication-integrity-failure.png"), full_page=True)
            except Exception:
                pass
        finally:
            if teacher_context is not None:
                teacher_context.close()
            if admin_context is not None:
                admin_context.close()
            if student_context is not None:
                student_context.close()
            browser.close()
            server.shutdown()
            thread.join(timeout=5)

    external_dependencies = [item for item in blocked_external_requests if item.get("source") == "page"]
    flow["status"] = "FAIL" if base_e2e.flow_has_failures(flow, external_dependencies) else "PASS"
    return _build_result(
        scenario=flow,
        blocked_external_requests=blocked_external_requests,
        artifacts_directory=str(artifact_dir),
        browser_version=browser_version,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run 11D publication integrity browser E2E checks.")
    parser.add_argument("--json-output", help="Write machine-readable result JSON.")
    parser.add_argument("--headed", action="store_true", help="Run Chromium headed for local debugging.")
    parser.add_argument("--keep-artifacts", action="store_true", help="Keep temp DB/uploads/downloads/screenshots after success.")
    parser.add_argument("--artifacts", help="Optional artifact directory for screenshots.")
    args = parser.parse_args(argv)

    base_dir = Path(tempfile.mkdtemp(prefix="lexibridge-publication-integrity-browser-e2e-"))
    artifact_dir = Path(args.artifacts).resolve() if args.artifacts else base_dir / "artifacts"
    try:
        try:
            result = _run_checks(base_dir=base_dir, artifact_dir=artifact_dir, headed=args.headed)
            exit_code = 0 if result["status"] == "PASS" else 1
        except RuntimeError as exc:
            if str(exc).startswith("E2E_ENVIRONMENT_UNAVAILABLE"):
                result = _build_result(
                    status="E2E_ENVIRONMENT_UNAVAILABLE",
                    message=str(exc),
                    artifacts_directory=str(artifact_dir),
                )
                exit_code = E2E_ENVIRONMENT_UNAVAILABLE
            else:
                result = _build_result(status="FAIL", message=str(exc), artifacts_directory=str(artifact_dir))
                exit_code = 1
        except Exception as exc:
            result = _build_result(status="FAIL", message=str(exc), artifacts_directory=str(artifact_dir))
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
