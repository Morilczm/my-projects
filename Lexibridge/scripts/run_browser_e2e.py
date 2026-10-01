#!/usr/bin/env python3
"""Run real-browser E2E checks for Student, Instructor, and Reviewer workflows.

Exit codes:
  0: browser E2E passed
  1: browser E2E failed
  2: browser runtime is unavailable
"""

from __future__ import annotations

import argparse
import importlib.metadata
import importlib.util
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
PYTHON = ROOT / "backend" / ".venv-macos" / "bin" / "python"
PYTHON_CMD = str(PYTHON if PYTHON.exists() else sys.executable)
E2E_ENVIRONMENT_UNAVAILABLE = 2
ALLOWED_SCHEMES = ("data:", "blob:", "about:")
SYSTEM_CHROMIUM_CANDIDATES = (
    Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
    Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def playwright_version() -> str:
    try:
        return importlib.metadata.version("playwright")
    except importlib.metadata.PackageNotFoundError:
        return ""


def build_env(database: Path, uploads: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{database}"
    env["UPLOAD_FOLDER"] = str(uploads)
    env["AUTH_REQUIRED"] = "True"
    env["AI_PROVIDER"] = "none"
    env["ALLOW_MOCK_AI"] = "True"
    env["OCR_PROVIDER"] = "none"
    env["FORMULA_OCR_PROVIDER"] = "none"
    env["FORMULA_DETECTION_MODE"] = "off"
    env["LEXIBRIDGE_SKIP_ENV_FILE"] = "true"
    env["DEEPSEEK_API_KEY"] = ""
    env["OPENAI_API_KEY"] = ""
    env["ANTHROPIC_API_KEY"] = ""
    return env


def run_setup(database: Path, uploads: Path, flow_name: str) -> dict[str, Any]:
    env = build_env(database, uploads)
    subprocess.run([PYTHON_CMD, "scripts/migrate_db.py", "--apply"], cwd=ROOT, env=env, check=True, capture_output=False)
    subprocess.run([PYTHON_CMD, "scripts/seed_review_demo.py", "--reset-demo"], cwd=ROOT, env=env, check=True, capture_output=False)

    os.environ.update(env)
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))
    module_name = f"lexibridge_e2e_app_{flow_name}_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, BACKEND / "app.py")
    app_module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(app_module)
    seed_spec = importlib.util.spec_from_file_location(
        f"lexibridge_e2e_seed_{flow_name}_{uuid.uuid4().hex}",
        ROOT / "scripts" / "seed_review_demo.py",
    )
    seed = importlib.util.module_from_spec(seed_spec)
    assert seed_spec.loader is not None
    seed_spec.loader.exec_module(seed)
    with app_module.app.app_context():
        summary = seed.seed_review_demo(app_module, reset_demo=False)
        seed_student_concept_query_demo(app_module, uploads)
    app_module.app.config["STUDENT_CROSS_LANGUAGE_EMBEDDING_BACKEND"] = (
        BrowserWorkflowEmbeddingBackend()
    )
    app_module.app.config["STUDENT_BILINGUAL_RERANKER_BACKEND"] = (
        BrowserWorkflowRerankerBackend()
    )
    # This validates the synthetic pilot contract only; it is not human-study
    # evidence and must never be reported as real-participant validation.
    app_module.app.config["STUDENT_REAL_PILOT_ENABLED"] = True
    return {"app_module": app_module, "summary": summary}


class BrowserWorkflowEmbeddingBackend:
    """Deterministic CI backend for the complete production alignment workflow."""

    backend_id = "local_multilingual_e5_pytorch_cpu_v1"
    model_id = "intfloat/multilingual-e5-small"
    model_revision = "614241f622f53c4eeff9890bdc4f31cfecc418b3"

    def readiness(self):
        return type("Readiness", (), {"ready": True, "reason_code": "READY"})()

    def embed_queries(self, texts):
        return [[1.0, 0.0] for _ in texts]

    def embed_passages(self, texts):
        return [
            [1.0, 0.0] if "电势" in text else [0.0, 1.0]
            for text in texts
        ]


class BrowserWorkflowRerankerBackend:
    backend_id = "local_bge_reranker_v2_m3_cpu_v1"
    model_id = "BAAI/bge-reranker-v2-m3"
    model_revision = "79c481748842b7efa0a12db59915db91731f0b93"

    def readiness(self):
        return type("Readiness", (), {"ready": True, "reason_code": "READY"})()

    def score_pairs(self, pairs):
        return [5.0 for _ in pairs]


def seed_student_concept_query_demo(app_module: Any, uploads: Path) -> None:
    student = app_module.User.query.filter_by(email="review.student@lexibridge.local").first()
    course = app_module.Course.query.filter_by(name="DEMO Signals and Systems").first()
    if student is None or course is None:
        raise RuntimeError("Task 13B browser fixture requires seeded Student and course.")
    membership = app_module.CourseMember.query.filter_by(
        user_id=student.id, course_id=course.id
    ).first()
    if membership is None:
        app_module.db.session.add(app_module.CourseMember(
            user_id=student.id, course_id=course.id, role="student",
            role_in_course="student", status="active",
            created_at=app_module.current_time_text(), joined_at=app_module.current_time_text(),
        ))
    sources = [
        dict(uid="e2e-personal-zh", title="我的中文物理参考", language="zh", scope="personal",
             owner=student.id, course_id=None, visibility="private", role="chinese_reference_material"),
        dict(uid="e2e-course-en", title="Course Electrostatics", language="en", scope="course",
             owner=None, course_id=course.id, visibility="course", role="english_course_material"),
        dict(uid="e2e-course-zh", title="课程中文电磁学证据", language="zh", scope="course",
             owner=None, course_id=course.id, visibility="course", role="chinese_reference_material"),
    ]
    for item in sources:
        source = app_module.KnowledgeSource.query.filter_by(source_uid=item["uid"]).first()
        if source is None:
            source = app_module.KnowledgeSource(
                source_uid=item["uid"], name=item["title"], title=item["title"],
                language=item["language"], scope_type=item["scope"], owner_user_id=item["owner"],
                course_id=item["course_id"], course=course.name if item["course_id"] else "",
                visibility=item["visibility"], source_role=item["role"], status="active",
                # Keep the browser fixture aligned with the governed source
                # contract used by the production qualification gate.  A
                # generic "authorized" value is not sufficient to establish
                # course-use evidence eligibility.
                version=1,
                authorization_status=(
                    "allowed_for_course_use"
                    if item["scope"] == "course"
                    else "allowed_for_private_use"
                ),
                license_status="licensed",
                # The qualification policy consumes the normalized parse
                # quality vocabulary ("ready"), not the UI label
                # "qualified".  Keep this synthetic source on the same
                # governed path as an actually indexed, ready document.
                allow_student_search=True, quality_status="ready",
            )
            app_module.db.session.add(source)
    app_module.db.session.flush()
    course_source = app_module.KnowledgeSource.query.filter_by(
        source_uid="e2e-course-en"
    ).one()
    if course_source.document_id is None:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas

        course_pdf = uploads / "e2e-managed-course-electrostatics.pdf"
        pdf = canvas.Canvas(str(course_pdf), pagesize=letter)
        pdf.drawString(72, 720, "Electric potential")
        pdf.drawString(
            72,
            690,
            "The electric potential at a point equals potential energy per unit charge.",
        )
        pdf.save()
        storage = app_module.storage_service().save_file(
            str(course_pdf),
            purpose="uploaded_document",
            owner_user_id=student.id,
            course_id=course.id,
            original_filename=course_pdf.name,
        )
        parse_uid = "e2e-course-en-parse"
        document = app_module.Document(
            owner_user_id=student.id,
            course_id=course.id,
            scope_type="course",
            filename=course_pdf.name,
            original_filename=course_pdf.name,
            file_type="pdf",
            content_type="application/pdf",
            size_bytes=int(storage.get("size_bytes") or 0),
            sha256=str(storage.get("sha256") or ""),
            storage_backend=str(storage.get("storage_backend") or ""),
            storage_key=str(storage.get("storage_key") or ""),
            language="en",
            parsing_status="parsed",
            parse_uid=parse_uid,
            deleted_at="",
        )
        parse_record = app_module.DocumentParseRecord(
            parse_uid=parse_uid,
            source_filename=course_pdf.name,
            file_type="pdf",
            mime_type="application/pdf",
            parser_name="pymupdf_native",
            parser_version="parse_quality_v1",
            parse_status="parsed",
            quality_status="native_text_ok",
            page_count=1,
            block_count=1,
        )
        app_module.db.session.add_all([document, parse_record])
        app_module.db.session.flush()
        course_source.document_id = document.id
        course_source.parse_uid = parse_uid
        course_source.file_type = "pdf"
    else:
        document = app_module.db.session.get(
            app_module.Document, course_source.document_id
        )
    for uid, source_uid, scope, course_id, owner, language, text in (
        (
            "e2e-personal-zh-chunk", "e2e-personal-zh", "personal", None,
            student.id, "zh", "电势表示单位电荷在电场中的电势能。",
        ),
        (
            "e2e-course-en-chunk", "e2e-course-en", "course", course.id,
            None, "en", "The electric potential at a point equals potential energy per unit charge.",
        ),
        (
            "e2e-course-zh-chunk", "e2e-course-zh", "course", course.id,
            None, "zh", "电势表示单位电荷在电场中的电势能。",
        ),
    ):
        if app_module.KnowledgeChunk.query.filter_by(chunk_uid=uid).first() is None:
            app_module.db.session.add(app_module.KnowledgeChunk(
                chunk_uid=uid, source_uid=source_uid,
                document_id=(
                    document.id
                    if source_uid == "e2e-course-en"
                    else 910000 + len(uid)
                ),
                content=text, normalized_text=text.lower(), language=language,
                scope_type=scope, course_id=course_id, course=course.name if course_id else "",
                owner_user_id=str(owner or ""), visibility="course" if course_id else "private",
                status="active", quality_status="ready", page_number=1,
                parse_block_uid=f"{uid}-block",
            ))
    app_module.db.session.commit()


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def start_server(app_module: Any, port: int):
    from flask import Response, send_from_directory
    from werkzeug.serving import make_server

    if "pilot_browser_e2e_frontend" not in app_module.app.view_functions:
        @app_module.app.route("/e2e", endpoint="pilot_browser_e2e_frontend")
        def pilot_browser_e2e_frontend():
            html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
            injected = "<script>window.LEXIBRIDGE_CONFIG = { API_BASE: window.location.origin };</script>"
            html = html.replace("<script>", injected + "\n<script>", 1)
            return Response(html, mimetype="text/html")

    if "pilot_browser_e2e_config" not in app_module.app.view_functions:
        @app_module.app.route("/js/config.js", endpoint="pilot_browser_e2e_config")
        def pilot_browser_e2e_config():
            return Response(
                "window.LEXIBRIDGE_CONFIG = { API_BASE: window.location.origin };",
                mimetype="application/javascript",
            )

    if "pilot_browser_e2e_formal_workflow" not in app_module.app.view_functions:
        @app_module.app.route("/js/formal-workflow.js", endpoint="pilot_browser_e2e_formal_workflow")
        def pilot_browser_e2e_formal_workflow():
            return Response(
                (ROOT / "frontend" / "js" / "formal-workflow.js").read_text(encoding="utf-8"),
                mimetype="application/javascript",
            )

    if "pilot_browser_e2e_frontend_modules" not in app_module.app.view_functions:
        @app_module.app.route(
            "/js/<path:filename>", endpoint="pilot_browser_e2e_frontend_modules"
        )
        def pilot_browser_e2e_frontend_modules(filename):
            return send_from_directory(ROOT / "frontend" / "js", filename)

    if "pilot_browser_e2e_pdfjs_assets" not in app_module.app.view_functions:
        @app_module.app.route(
            "/vendor/pdfjs/<path:filename>",
            endpoint="pilot_browser_e2e_pdfjs_assets",
        )
        def pilot_browser_e2e_pdfjs_assets(filename):
            return send_from_directory(ROOT / "frontend" / "vendor" / "pdfjs", filename)

    if "pilot_browser_e2e_favicon" not in app_module.app.view_functions:
        @app_module.app.route("/favicon.ico", endpoint="pilot_browser_e2e_favicon")
        def pilot_browser_e2e_favicon():
            return Response("", status=204)

    server = make_server("127.0.0.1", port, app_module.app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def assert_playwright_available() -> None:
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except Exception as exc:
        raise RuntimeError(
            "E2E_ENVIRONMENT_UNAVAILABLE: Python Playwright is not installed. "
            "Install requirements-e2e.txt and Chromium before running browser E2E."
        ) from exc


def flow_result(name: str) -> dict[str, Any]:
    return {
        "name": name,
        "status": "SKIPPED",
        "steps": [],
        "console_errors": [],
        "page_errors": [],
        "failed_requests": [],
        "requests": [],
        "downloads": [],
    }


def add_step(flow: dict[str, Any], name: str, status: str = "PASS", details: str = "") -> None:
    flow["steps"].append({"name": name, "status": status, "details": details})


def assert_student_learning_support_contract(
    alignment_status: str,
    support: dict[str, Any],
) -> None:
    """Validate the Student-first display contract without forcing automation."""
    expected_support_statuses = {
        "READY": {"EVIDENCE_GROUNDED", "GROUNDING_INCOMPLETE"},
        "REVIEW_REQUIRED": {
            "ALTERNATIVES_UNRESOLVED",
            "GROUNDING_INCOMPLETE",
        },
        "NOT_READY": {"NO_RELIABLE_ALIGNMENT"},
    }
    assert alignment_status in expected_support_statuses
    assert support["contract_id"] == "student-learning-support@1.0.0"
    assert support["provider_used"] is False
    assert support["grounding_mode"] == "DETERMINISTIC_EVIDENCE_TEMPLATE"
    assert support["status"] in expected_support_statuses[alignment_status]
    if alignment_status == "NOT_READY":
        assert support["candidate_evidence"] == []
        assert support["do_not_confuse_with"] == []


def flow_has_failures(flow: dict[str, Any], external_dependencies: list[dict[str, Any]]) -> bool:
    failed_steps = any(step.get("status") == "FAIL" for step in flow.get("steps", []))
    unexpected_failed_requests = [
        item for item in flow.get("failed_requests", []) if not item.get("expected")
    ]
    return bool(
        failed_steps
        or flow.get("console_errors")
        or flow.get("page_errors")
        or unexpected_failed_requests
        or external_dependencies
    )


def build_overall_result(
    *,
    browser_name: str = "chromium",
    browser_version: str = "",
    student_flow: dict[str, Any] | None = None,
    instructor_flow: dict[str, Any] | None = None,
    reviewer_flow: dict[str, Any] | None = None,
    teacher_flow: dict[str, Any] | None = None,
    blocked_external_requests: list[dict[str, Any]] | None = None,
    artifacts_directory: str | None = None,
    status: str | None = None,
    message: str = "",
) -> dict[str, Any]:
    student_flow = student_flow or flow_result("student")
    instructor_flow = instructor_flow or teacher_flow or flow_result("instructor")
    reviewer_flow = reviewer_flow or flow_result("reviewer")
    # Compatibility field for existing readiness/artifact consumers. It now
    # aliases the Instructor flow and no longer means bilingual review.
    teacher_flow = instructor_flow
    blocked_external_requests = blocked_external_requests or []
    external_dependencies = [item for item in blocked_external_requests if item.get("source") == "page"]
    if status is None:
        requested_flows = [
            flow
            for flow in (student_flow, instructor_flow, reviewer_flow)
            if flow.get("status") != "SKIPPED"
        ]
        status = (
            "PASS"
            if requested_flows
            and all(flow.get("status") == "PASS" and not flow_has_failures(flow, external_dependencies) for flow in requested_flows)
            and not external_dependencies
            else "FAIL"
        )
    return {
        "status": status,
        "message": message,
        "browser": {
            "name": browser_name,
            "version": browser_version,
            "playwright_version": playwright_version(),
        },
        "student_flow": student_flow,
        "instructor_flow": instructor_flow,
        "reviewer_flow": reviewer_flow,
        "teacher_flow": teacher_flow,
        "teacher_flow_compatibility": "instructor_flow_alias",
        "blocked_external_requests": blocked_external_requests,
        "external_dependency_requests": external_dependencies,
        "artifacts_directory": artifacts_directory,
        "generated_at": utc_now(),
    }


class FlowCapture:
    def __init__(self, flow: dict[str, Any], blocked_external_requests: list[dict[str, Any]], port: int):
        self.flow = flow
        self.blocked_external_requests = blocked_external_requests
        self.port = port
        self.probe_urls: set[str] = set()

    def is_allowed(self, url: str) -> bool:
        return (
            url.startswith(f"http://127.0.0.1:{self.port}/")
            or url.startswith(f"http://localhost:{self.port}/")
            or url.startswith(ALLOWED_SCHEMES)
        )

    def route(self, route, request) -> None:
        url = request.url
        if self.is_allowed(url):
            self.flow["requests"].append(url)
            route.continue_()
            return
        source = "probe" if url in self.probe_urls else "page"
        self.blocked_external_requests.append({"url": url, "source": source, "flow": self.flow["name"]})
        route.abort()

    def attach_page(self, page) -> None:
        page.on("console", self.on_console)
        page.on("pageerror", lambda exc: self.flow["page_errors"].append(str(exc)))
        page.on("requestfailed", self.on_request_failed)

    def on_console(self, msg) -> None:
        if msg.type == "error":
            if "Failed to load resource: net::ERR_FAILED" in msg.text:
                return
            if "Failed to load resource: the server responded with a status of 400" in msg.text:
                # The teacher flow intentionally triggers one policy-blocked API request
                # and verifies the surfaced request_id. Treat that expected negative
                # path separately from unhandled JavaScript errors.
                return
            if "Failed to load resource: the server responded with a status of 409" in msg.text:
                # Publication integrity browser checks intentionally trigger a stale
                # review conflict and verify the page-level error state.
                return
            self.flow["console_errors"].append(msg.text)

    def on_request_failed(self, request) -> None:
        url = request.url
        failure = request.failure or ""
        expected_browser_lifecycle = (
            url.startswith("blob:") and "ERR_ABORTED" in failure
        )
        self.flow["failed_requests"].append(
            {
                "url": url,
                "failure": failure,
                "expected": url in self.probe_urls or expected_browser_lifecycle,
            }
        )


def expect_visible(page, selector: str, step_name: str, flow: dict[str, Any], timeout: int = 10000):
    locator = page.locator(selector).first
    locator.wait_for(state="visible", timeout=timeout)
    add_step(flow, step_name)
    return locator


def expect_text_absent(page, text: str, step_name: str, flow: dict[str, Any]) -> None:
    body = page.locator("body").inner_text()
    assert text not in body, f"unexpected text visible: {text}"
    add_step(flow, step_name)


def click_and_expect_download(page, locator, flow: dict[str, Any], artifact_dir: Path, expected_suffixes: tuple[str, ...], step_name: str) -> None:
    download_dir = artifact_dir / "downloads" / flow["name"]
    download_dir.mkdir(parents=True, exist_ok=True)
    with page.expect_download(timeout=10000) as download_info:
        locator.click()
    download = download_info.value
    suggested = download.suggested_filename
    target = download_dir / suggested
    download.save_as(str(target))
    size = target.stat().st_size
    assert size > 0, f"download was empty: {suggested}"
    assert target.suffix.lower() in expected_suffixes, f"unexpected download suffix: {target.suffix}"
    flow["downloads"].append({"suggested_filename": suggested, "size_bytes": size, "path": str(target)})
    add_step(flow, step_name, details=f"{suggested} {size} bytes")


def probe_external_block(page, capture: FlowCapture, flow: dict[str, Any]) -> None:
    probe_url = f"https://example.invalid/lexibridge-e2e-probe-{uuid.uuid4().hex}.json"
    before = len(capture.blocked_external_requests)
    capture.probe_urls.add(probe_url)
    page.evaluate("url => fetch(url).catch(() => null)", probe_url)
    for _ in range(20):
        if len(capture.blocked_external_requests) > before:
            break
        page.wait_for_timeout(100)
    assert any(item.get("url") == probe_url and item.get("source") == "probe" for item in capture.blocked_external_requests)
    add_step(flow, "active external request probe blocked")


def open_frontend(page, port: int, flow: dict[str, Any]) -> None:
    page.goto(f"http://127.0.0.1:{port}/e2e", wait_until="domcontentloaded")
    try:
        page.wait_for_load_state("networkidle", timeout=5000)
    except Exception:
        pass
    add_step(flow, "open page")


def login(page, email: str, password: str, flow: dict[str, Any]) -> None:
    page.locator("button", has_text="Login").first.click()
    form = page.locator("form").filter(has=page.locator('input[name="password"]')).first
    form.locator('input[name="email"]').fill(email)
    form.locator('input[name="password"]').fill(password)
    form.locator("button").last.click()
    page.wait_for_selector("#userChip", timeout=10000)
    page.wait_for_function("email => document.querySelector('#userChip')?.innerText.includes(email)", arg=email, timeout=10000)
    add_step(flow, "login")


def wait_text_change(page, selector: str, previous: str) -> None:
    page.wait_for_function(
        """([selector, previous]) => {
            const el = document.querySelector(selector);
            return el && el.innerText !== previous;
        }""",
        arg=[selector, previous],
        timeout=10000,
    )


def wait_text_contains(page, selector: str, expected: str, timeout: int = 10000):
    """Wait for async rendering to replace cached text before asserting it."""
    page.wait_for_function(
        """([selector, expected]) => {
            const el = document.querySelector(selector);
            return el && el.innerText.includes(expected);
        }""",
        arg=[selector, expected],
        timeout=timeout,
    )
    return page.locator(selector)


def wait_pdfjs_page_ready(page, page_number: int, flow: dict[str, Any], label: str):
    page.wait_for_function(
        """expected => {
            const preview = document.querySelector('[data-testid="student-pdf-preview"]');
            const layer = document.querySelector('[data-testid="student-pdf-text-layer"]');
            return preview?.dataset.pdfjsStatus === 'READY'
                && preview?.dataset.pdfjsVersion === '6.2.108'
                && preview?.dataset.pdfjsPage === String(expected)
                && layer?.querySelectorAll('span').length > 0;
        }""",
        arg=page_number,
        timeout=15000,
    )
    assert page.locator('[data-testid="student-material-reader"] iframe').count() == 0
    assert page.locator('[data-testid="student-pdf-fallback"]').count() == 0
    add_step(flow, f"{label} rendered through local PDF.js text layer")


def select_pdfjs_text(page, phrase: str) -> dict[str, Any]:
    layer = page.locator('[data-testid="student-pdf-text-layer"]')
    layer.evaluate(
        """(element, phrase) => {
            const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
            const positions = [];
            let compact = '';
            while (walker.nextNode()) {
                const node = walker.currentNode;
                for (let offset = 0; offset < node.data.length; offset += 1) {
                    const character = node.data[offset];
                    if (/\\s/u.test(character)) continue;
                    compact += character.toLocaleLowerCase('en-US');
                    positions.push({node, offset});
                }
            }
            const normalizedPhrase = String(phrase)
                .replace(/\\s/gu, '')
                .toLocaleLowerCase('en-US');
            const start = compact.indexOf(normalizedPhrase);
            if (start < 0) throw new Error(`PDF text layer is missing: ${phrase}`);
            const first = positions[start];
            const last = positions[start + normalizedPhrase.length - 1];
            if (!first || !last) throw new Error('PDF selection boundary is unavailable');
            const range = document.createRange();
            range.setStart(first.node, first.offset);
            range.setEnd(last.node, last.offset + 1);
            const selection = window.getSelection();
            selection.removeAllRanges();
            selection.addRange(range);
            element.dispatchEvent(new PointerEvent('pointerup', {bubbles: true}));
        }""",
        phrase,
    )
    page.wait_for_function(
        """phrase => state.studentConceptQuery.selectedText.toLowerCase()
            === String(phrase).toLowerCase()""",
        arg=phrase,
        timeout=10000,
    )
    return page.evaluate(
        """() => ({
            selectedText: state.studentConceptQuery.selectedText,
            chunkUid: state.studentConceptQuery.chunkUid,
            selectionStart: state.studentConceptQuery.selectionStart,
            selectionEnd: state.studentConceptQuery.selectionEnd,
        })"""
    )


def run_student_flow(page, summary: dict[str, Any], flow: dict[str, Any], artifact_dir: Path, capture: FlowCapture, app_module: Any) -> None:
    student = summary["users"]["student"]
    open_frontend(page, capture.port, flow)
    probe_external_block(page, capture, flow)
    login(page, student["email"], student["password"], flow)
    assert page.locator('[data-testid="concept-review-nav"]').count() == 0
    add_step(flow, "teacher review nav hidden for student")

    # Task 13C: exercise the real student upload route and the existing
    # layout-aware ingestion worker with a synthetic, repository-independent PDF.
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfgen import canvas

    english_pdf = artifact_dir / "synthetic-personal-physics.pdf"
    chinese_pdf = artifact_dir / "synthetic-personal-chinese-evidence.pdf"
    english_pdf.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(english_pdf), pagesize=letter)
    pdf.drawString(72, 720, "Electric potential")
    pdf.drawString(72, 690, "Electric potential is potential energy per unit charge.")
    pdf.showPage()
    pdf.drawString(72, 720, "Electric field")
    pdf.drawString(72, 690, "Electric field is force per unit charge.")
    pdf.save()
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    pdf = canvas.Canvas(str(chinese_pdf), pagesize=letter)
    pdf.setFont("STSong-Light", 12)
    pdf.drawString(72, 720, "电势")
    pdf.drawString(72, 690, "电势表示单位电荷在电场中的电势能。")
    pdf.save()
    page.locator('[data-testid="my-workspace-nav"]').first.click()
    expect_visible(page, '[data-testid="student-personal-workspace"]', "My Workspace visible", flow)
    expect_visible(
        page,
        '[data-testid="student-pilot-panel"]',
        "optional consent-first student pilot panel visible",
        flow,
    )
    page.locator('[data-testid="student-pilot-consent"]').check()
    with page.expect_response(
        lambda response: response.request.method == "POST" and response.url.endswith("/api/student/pilot/enrollment"),
        timeout=10000,
    ):
        page.locator('[data-testid="student-pilot-enroll"]').click()
    expect_visible(page, '[data-testid="student-pilot-consented"]', "pilot consent recorded", flow)
    with page.expect_response(
        lambda response: response.request.method == "POST" and response.url.endswith("/api/student/pilot/sessions"),
        timeout=10000,
    ):
        page.locator('[data-testid="student-pilot-start"]').click()
    expect_visible(page, '[data-testid="student-pilot-active"]', "synthetic pilot session started", flow)
    add_step(flow, "synthetic pilot contract recorded explicit optional consent")

    upload_form = page.locator('[data-testid="personal-material-upload-form"]')
    upload_form.locator('select[name="personal_material_role"]').select_option(
        "CHINESE_REFERENCE_EVIDENCE"
    )
    upload_form.locator('input[name="usage_rights_confirmed"]').check()
    upload_form.locator('input[type="file"]').set_input_files(str(chinese_pdf))
    with page.expect_response(
        lambda response: response.request.method == "POST" and response.url.endswith("/api/documents/upload"),
        timeout=10000,
    ) as upload_info:
        page.locator('[data-testid="personal-material-upload"]').click()
    chinese_upload_payload = upload_info.value.json()["data"]
    with app_module.app.app_context():
        app_module.run_background_job(
            chinese_upload_payload["job_id"], worker_id="browser-13c2-zh"
        )
        chinese_source = app_module.KnowledgeSource.query.filter_by(
            document_id=chinese_upload_payload["document_id"]
        ).one()
        assert chinese_source.source_role == "chinese_reference_material"
        assert chinese_source.visibility == "private"
        assert chinese_source.allow_student_search is True
    page.locator('[data-testid="my-workspace-nav"]').first.click()
    expect_visible(
        page,
        '[data-testid="personal-evidence-corpus-status"]',
        "personal Chinese evidence corpus visible",
        flow,
    )
    wait_text_contains(
        page,
        '[data-testid="personal-evidence-corpus-status"]',
        "1 份可检索",
    )
    chinese_row = page.locator('[data-testid="personal-material-item"]').filter(
        has_text="synthetic-personal-chinese-evidence.pdf"
    )
    assert "READY" in chinese_row.inner_text()
    assert "中文参考证据" in chinese_row.inner_text()
    add_step(flow, "private Chinese PDF admitted to the personal evidence corpus")

    upload_form = page.locator('[data-testid="personal-material-upload-form"]')
    upload_form.locator('select[name="personal_material_role"]').select_option(
        "ENGLISH_COURSE_MATERIAL"
    )
    upload_form.locator('input[name="usage_rights_confirmed"]').check()
    upload_form.locator('input[type="file"]').set_input_files(str(english_pdf))
    with page.expect_response(
        lambda response: response.request.method == "POST" and response.url.endswith("/api/documents/upload"),
        timeout=10000,
    ) as upload_info:
        page.locator('[data-testid="personal-material-upload"]').click()
    upload_payload = upload_info.value.json()["data"]
    with app_module.app.app_context():
        app_module.run_background_job(upload_payload["job_id"], worker_id="browser-13c2-en")
        uploaded_source = app_module.KnowledgeSource.query.filter_by(
            document_id=upload_payload["document_id"]
        ).one()
        assert uploaded_source.source_role == "english_course_material"
        uploaded_source_uid = uploaded_source.source_uid
    page.locator('[data-testid="my-workspace-nav"]').first.click()
    ready_material = page.locator('[data-testid="personal-material-item"]').filter(
        has_text="synthetic-personal-physics.pdf"
    )
    ready_material.wait_for(state="visible", timeout=10000)
    add_step(flow, "personal PDF parsed into private evidence material")
    assert "READY" in ready_material.inner_text()
    add_step(flow, "personal PDF upload, parse, chunk, and private index completed")

    page.locator('[data-testid="student-concept-card-nav"]').first.click()
    expect_visible(page, '[data-testid="student-concept-card-page"]', "student Concept Cards page visible", flow)
    expect_visible(page, '[data-testid="student-card-row"]', "approved card row visible", flow)
    assert "DEMO Signals and Systems" in page.locator("body").inner_text()
    add_step(flow, "DEMO Signals and Systems approved card visible")
    expect_text_absent(page, "DEMO Hidden Course", "hidden course card not visible", flow)

    page.locator('[data-testid="student-card-row"]').first.click()
    expect_visible(page, '[data-testid="student-card-detail"]', "student detail visible", flow)
    expect_visible(page, '[data-testid="student-english-evidence-items"] .quote', "english evidence nonempty", flow)
    expect_visible(page, '[data-testid="student-chinese-evidence-items"] .quote', "chinese evidence nonempty", flow)

    favorite = page.locator('[data-testid="student-favorite-toggle"]').first
    favorite_before = favorite.inner_text()
    favorite.click()
    wait_text_change(page, '[data-testid="student-favorite-toggle"]', favorite_before)
    add_step(flow, "favorite state toggled")

    mastered = page.locator('[data-testid="student-mastered-toggle"]').first
    mastered_before = mastered.inner_text()
    mastered.click()
    wait_text_change(page, '[data-testid="student-mastered-toggle"]', mastered_before)
    add_step(flow, "mastered state toggled")

    progress_before = page.locator('[data-testid="student-progress-panel"]').inner_text()
    feedback_form = page.locator('[data-testid="student-feedback-form"]')
    feedback_form.locator('select[name="feedback_type"]').select_option("explanation_unclear")
    feedback_form.locator('textarea[name="message"]').fill("Browser E2E feedback: explanation needs one more example.")
    feedback_form.locator('[data-testid="student-feedback-submit"]').click()
    expect_visible(page, '[data-testid="student-card-success"]', "student feedback success", flow)

    page.locator('[data-testid="student-concept-card-page"] button', has_text="刷新").first.click()
    wait_text_change(page, '[data-testid="student-progress-panel"]', progress_before)
    add_step(flow, "learning progress updated after state/feedback")

    click_and_expect_download(
        page,
        page.locator('[data-testid="student-export-button"]').first,
        flow,
        artifact_dir,
        (".json", ".csv"),
        "student export download verified",
    )
    assert page.locator('[data-testid="review-action-approve"]').count() == 0
    add_step(flow, "student cannot trigger review action")

    page.locator('[data-testid="my-workspace-nav"]').first.click()
    page.locator('[data-testid="personal-material-query"]').first.click()
    expect_visible(page, '[data-testid="student-concept-query-page"]', "student ConceptQuery page visible", flow)
    expect_visible(page, '[data-testid="student-material-reader"]', "shared Student material reader visible", flow)
    expect_visible(page, '[data-testid="student-pdf-preview"]', "authorized Personal PDF preview visible", flow)
    expect_visible(page, '[data-testid="student-reader-page"]', "page-aware reader navigation visible", flow)
    wait_pdfjs_page_ready(page, 1, flow, "Personal PDF")
    add_step(flow, "Personal PDF opened through authenticated Blob reader")
    with page.expect_response(
        lambda response: response.url.endswith(f"/api/student/concept-materials/{uploaded_source_uid}/reader?page=2"),
        timeout=10000,
    ):
        page.locator('[data-testid="student-reader-next"]').click()
    wait_pdfjs_page_ready(page, 2, flow, "Personal PDF page 2")
    assert "electric field" in page.locator('[data-testid="student-pdf-text-layer"]').inner_text().lower()
    with page.expect_response(
        lambda response: response.url.endswith(f"/api/student/concept-materials/{uploaded_source_uid}/reader?page=1"),
        timeout=10000,
    ):
        page.locator('[data-testid="student-reader-prev"]').click()
    wait_pdfjs_page_ready(page, 1, flow, "Personal PDF page 1")
    add_step(flow, "page navigation kept PDF canvas and text layer synchronized")
    for source_uid, expected_scope, step_prefix in (
        (uploaded_source_uid, "PERSONAL", "Personal Workspace uploaded source"),
        ("e2e-course-en", "MANAGED_COURSE", "Managed Course"),
    ):
        if source_uid != uploaded_source_uid:
            with page.expect_response(
                lambda response: response.url.endswith(f"/api/student/concept-materials/{source_uid}/reader?page=1"),
                timeout=10000,
            ):
                page.locator('[data-testid="student-concept-material-select"]').select_option(source_uid)
        assert page.evaluate(
            "() => state.cache.studentMaterialReader?.source?.workspace_scope"
        ) == expected_scope
        add_step(flow, f"{step_prefix} entered the shared page-aware reader")
        wait_pdfjs_page_ready(page, 1, flow, step_prefix)
        mapping = select_pdfjs_text(page, "electric potential")
        assert mapping["chunkUid"]
        assert mapping["selectionEnd"] - mapping["selectionStart"] == len(
            "electric potential"
        )
        add_step(flow, f"{step_prefix} PDF text mapped to governed chunk/span")
        selection_summary = expect_visible(
            page,
            '[data-testid="student-selection-summary"]',
            f"{step_prefix} selection captured",
            flow,
        )
        assert "electric potential" in selection_summary.inner_text().lower()
        page.locator('[data-testid="student-concept-align-action"]').click()
        result = expect_visible(
            page, '[data-testid="student-concept-result"]',
            f"{step_prefix} alignment result visible", flow,
        )
        assert "PRIVATE" in result.inner_text()
        assert "NON_OFFICIAL" in result.inner_text()
        assert "电势" in result.inner_text()
        assert page.evaluate(
            "() => window.Lexi && state.studentConceptQuery.result.source_uid"
        ) == source_uid
        add_step(flow, f"{step_prefix} query retained the selected source UID")
        expect_visible(
            page,
            '[data-testid="student-learning-card"]',
            f"{step_prefix} result rendered as a concept learning card",
            flow,
        )
        page.locator('[data-testid="student-learning-card-evidence-toggle"]').click()
        expect_visible(page, '[data-testid="student-query-english-evidence"] .quote', f"{step_prefix} English evidence visible", flow)
        expect_visible(page, '[data-testid="student-query-chinese-evidence"] .quote', f"{step_prefix} Chinese evidence visible", flow)
        expect_visible(
            page,
            '[data-testid="student-learning-support-grounding"]',
            f"{step_prefix} evidence-only learning support disclosed",
            flow,
        )
        expect_visible(
            page,
            '[data-testid="student-meaning-here"]',
            f"{step_prefix} bounded course meaning visible",
            flow,
        )
        expect_visible(
            page,
            '[data-testid="student-alignment-rationale"]',
            f"{step_prefix} alignment rationale visible",
            flow,
        )
        support = page.evaluate(
            "() => window.Lexi && state.studentConceptQuery.result.learning_support"
        )
        alignment_status = page.evaluate(
            "() => window.Lexi && state.studentConceptQuery.result.alignment_status"
        )
        assert_student_learning_support_contract(alignment_status, support)
        add_step(flow, f"{step_prefix} learning support remained deterministic and non-official")
        if expected_scope == "PERSONAL":
            private_query_uid = page.evaluate(
                "() => window.Lexi && state.studentConceptQuery.result.query_uid"
            )
            with page.expect_response(
                lambda response: response.request.method == "PUT" and response.url.endswith("/personal-record"),
                timeout=10000,
            ):
                page.locator('[data-testid="student-query-save"]').click()
            page.locator('[data-testid="student-learning-card-note-toggle"]').click()
            page.locator('[data-testid="student-query-note"]').fill("Browser private learning note.")
            with page.expect_response(
                lambda response: response.request.method == "PUT" and response.url.endswith("/personal-record"),
                timeout=10000,
            ):
                page.locator('[data-testid="student-query-note-save"]').click()
            with page.expect_response(
                lambda response: response.request.method == "PUT" and response.url.endswith("/personal-record"),
                timeout=10000,
            ):
                page.locator('[data-testid="student-query-understood"]').click()
            page.wait_for_function(
                """() => document.querySelector('[data-testid="student-query-note"]')?.value === 'Browser private learning note.'""",
                timeout=10000,
            )
            add_step(flow, "Personal learning record saved with note and understanding")
        else:
            with page.expect_response(
                lambda response: response.request.method == "PUT" and response.url.endswith("/personal-record"),
                timeout=10000,
            ):
                page.locator('[data-testid="student-query-save"]').click()
            add_step(flow, "Managed Course result saved to the same private notebook")
        add_step(flow, f"{step_prefix} remained private and non-official")

    page.locator('[data-testid="personal-concept-notebook-nav"]').first.click()
    expect_visible(
        page,
        '[data-testid="personal-concept-notebook-page"]',
        "private concept notebook visible",
        flow,
    )
    expect_visible(page, '[data-testid="notebook-summary"]', "notebook summary visible", flow)
    assert page.locator('[data-testid="notebook-result-row"]').count() == 2
    add_step(flow, "Personal and Managed Course results shared one private notebook")

    notebook_form = page.locator('form').filter(
        has=page.locator('[data-testid="notebook-workspace-filter"]')
    )
    notebook_form.locator('[data-testid="notebook-search"]').fill("electric potential")
    notebook_form.locator('[data-testid="notebook-workspace-filter"]').select_option("PERSONAL")
    with page.expect_response(
        lambda response: "/api/student/personal-concept-notebook?" in response.url,
        timeout=10000,
    ):
        notebook_form.locator("button").click()
    personal_rows = page.locator('[data-testid="notebook-result-row"]')
    assert personal_rows.count() == 1
    assert "我的资料" in personal_rows.first.inner_text()
    add_step(flow, "notebook search and Personal Workspace filter applied")

    with page.expect_response(
        lambda response: response.request.method == "POST" and response.url.endswith("/revisit"),
        timeout=10000,
    ):
        personal_rows.first.click()
    expect_visible(
        page,
        '[data-testid="student-concept-result"]',
        "saved private alignment reopened",
        flow,
    )
    expect_visible(
        page,
        '[data-testid="student-learning-card-reveal"]',
        "notebook revisit starts in active-recall mode",
        flow,
    ).click()
    expect_visible(
        page,
        '[data-testid="student-result-chinese-term"]',
        "active-recall answer revealed on demand",
        flow,
    )
    page.locator('[data-testid="student-learning-card-note-toggle"]').click()
    page.wait_for_function(
        """() => document.querySelector('[data-testid="student-query-note"]')?.value === 'Browser private learning note.'""",
        timeout=10000,
    )
    assert page.evaluate(
        "() => state.studentConceptQuery.result.personal_state.understanding_state"
    ) == "UNDERSTOOD"
    add_step(flow, "notebook revisit preserved note and understanding state")

    with page.expect_response(
        lambda response: response.request.method == "PUT" and response.url.endswith("/complete"),
        timeout=10000,
    ):
        page.locator('[data-testid="student-pilot-complete"]').click()
    expect_visible(page, '[data-testid="student-pilot-survey"]', "bounded pilot survey visible", flow)
    survey = page.locator('[data-testid="student-pilot-survey"]')
    survey.locator('input[name="helpfulness"]').fill("5")
    survey.locator('input[name="evidence_helpfulness"]').fill("5")
    survey.locator('input[name="uncertainty_understanding"]').fill("4")
    survey.locator('input[name="task_difficulty"]').fill("2")
    survey.locator('input[name="would_use_again"]').check()
    with page.expect_response(
        lambda response: response.request.method == "PUT" and response.url.endswith("/survey"),
        timeout=10000,
    ):
        survey.locator('[data-testid="student-pilot-survey-submit"]').click()
    expect_visible(
        page,
        '[data-testid="student-pilot-survey-complete"]',
        "synthetic pilot survey recorded without content telemetry",
        flow,
    )
    add_step(flow, "synthetic pilot contract completed without claiming real participants")

    page.locator('[data-testid="personal-concept-notebook-nav"]').first.click()
    expect_visible(page, '[data-testid="personal-concept-notebook-page"]', "notebook reopened after pilot survey", flow)

    notebook_form = page.locator('form').filter(
        has=page.locator('[data-testid="notebook-workspace-filter"]')
    )
    notebook_form.locator('[data-testid="notebook-workspace-filter"]').select_option("MANAGED_COURSE")
    with page.expect_response(
        lambda response: "/api/student/personal-concept-notebook?" in response.url,
        timeout=10000,
    ):
        notebook_form.locator("button").click()
    managed_rows = page.locator('[data-testid="notebook-result-row"]')
    assert managed_rows.count() == 1
    assert "DEMO Signals and Systems" in managed_rows.first.inner_text()
    add_step(flow, "notebook Managed Course filter retained private non-official result")

    page.evaluate("() => window.Lexi.logout()")
    page.wait_for_function("() => !document.querySelector('#userChip')?.innerText.includes('@')")
    student2 = summary["users"]["student2"]
    login(page, student2["email"], student2["password"], flow)
    student2_token = page.evaluate("() => state.token")
    api_base = f"http://127.0.0.1:{capture.port}"
    query_probe = page.context.request.get(
        f"{api_base}/api/student/concept-queries/{private_query_uid}",
        headers={"Authorization": f"Bearer {student2_token}"},
    )
    record_probe = page.context.request.put(
        f"{api_base}/api/student/concept-queries/{private_query_uid}/personal-record",
        headers={"Authorization": f"Bearer {student2_token}"},
        data={"saved": True, "expected_version": 0},
    )
    assert [query_probe.status, record_probe.status] == [404, 404]
    add_step(flow, "Student 2 blocked from Student 1 query and personal record")


def run_legacy_teacher_review_flow(page, summary: dict[str, Any], flow: dict[str, Any], artifact_dir: Path, capture: FlowCapture) -> None:
    """Deprecated pre-13A flow retained temporarily for source history; never dispatched."""
    teacher = summary["users"]["teacher"]
    open_frontend(page, capture.port, flow)
    probe_external_block(page, capture, flow)
    login(page, teacher["email"], teacher["password"], flow)
    expect_visible(page, '[data-testid="concept-review-nav"]', "Concept Review nav visible", flow)

    page.locator('[data-testid="concept-review-nav"]').first.click()
    expect_visible(page, '[data-testid="review-queue"]', "review queue visible", flow)
    page.locator('[data-testid="review-filter-course"]').fill("DEMO Signals and Systems")
    page.locator("form").filter(has=page.locator('[data-testid="review-filter-course"]')).locator("button").first.click()
    expect_visible(page, '[data-testid="review-card-row"]', "review queue filtered", flow)

    page.locator('[data-testid="review-card-row"]', has_text="Fourier transform").first.click()
    expect_visible(page, '[data-testid="review-card-detail"]', "review detail visible", flow)
    expect_visible(page, '[data-testid="english-evidence-list"] .quote', "review english evidence visible", flow)
    expect_visible(page, '[data-testid="chinese-evidence-list"] .quote', "review chinese evidence visible", flow)
    assert "bilingual_alignment_not_verified" in page.locator("body").inner_text()
    add_step(flow, "risk labels visible")
    expect_visible(
        page,
        '[data-testid="teacher-alignment-review-case"]',
        "unified teacher alignment case visible",
        flow,
    )
    accept_form = page.locator("form").filter(
        has=page.locator('[data-testid="review-action-accept-recommendation"]')
    ).first
    accept_form.locator('textarea[name="review_comment"]').fill(
        "Browser E2E accepts the governed evidence-backed recommendation."
    )
    accept_form.locator(
        '[data-testid="review-action-accept-recommendation"]'
    ).click()
    expect_visible(page, '[data-testid="review-success"]', "human approval saved", flow)
    page.wait_for_function(
        """() => document.querySelector('[data-testid="teacher-alignment-review-case"]')?.innerText.includes('HUMAN_APPROVED')""",
        timeout=10000,
    )
    add_step(flow, "machine recommendation accepted without overwriting machine state")

    page.locator('[data-testid="review-generate-draft"]').click()
    expect_visible(page, '[data-testid="teacher-draft-editor"]', "fake draft editor visible", flow)
    draft_form = page.locator('[data-testid="teacher-draft-editor"]')
    draft_form.locator('textarea[name="english_explanation"]').fill(
        "Teacher-edited browser E2E explanation."
    )
    draft_form.locator("button").click()
    page.wait_for_function(
        """() => document.querySelector('[data-testid="teacher-draft-editor"] textarea[name="english_explanation"]')?.value.includes('Teacher-edited')""",
        timeout=10000,
    )
    assert "NOT_PUBLISHED" in draft_form.inner_text()
    add_step(flow, "fake draft generated, edited, saved, and left unpublished")

    history = expect_visible(page, '[data-testid="review-history"]', "review history visible", flow)
    history_before = history.locator("tbody tr").count() if history.locator("tbody").count() else 0

    revision = page.locator('[data-testid="review-action-request-revision"]').first
    revision.click()
    revision.locator('input[name="reason_code"]').fill("evidence_insufficient")
    revision.locator('textarea[name="required_changes"]').fill("Clarify evidence for browser E2E.\nAdd one more Chinese source if needed.")
    revision.locator('textarea[name="review_comment"]').fill("Browser E2E request revision.")
    revision.locator('[data-testid="review-submit"]').click()
    expect_visible(page, '[data-testid="review-success"]', "request revision success", flow)
    page.wait_for_function(
        """previous => {
            const rows = document.querySelectorAll('[data-testid="review-history"] tbody tr').length;
            return rows > previous;
        }""",
        arg=history_before,
        timeout=10000,
    )
    add_step(flow, "review history increased")

    expect_visible(page, '[data-testid="teacher-feedback-queue"]', "teacher feedback queue visible", flow)
    expect_visible(page, '[data-testid="teacher-feedback-row"]', "submitted feedback visible", flow)
    page.once("dialog", lambda dialog: dialog.accept("Acknowledged by browser E2E."))
    page.locator('[data-testid="teacher-feedback-action-acknowledge"]').first.click()
    expect_visible(page, '[data-testid="review-success"]', "feedback acknowledge success", flow)
    page.wait_for_function(
        """() => document.querySelector('[data-testid="teacher-feedback-row"]')?.innerText.includes('triaged')""",
        timeout=10000,
    )
    add_step(flow, "feedback status updated")

    expect_visible(page, '[data-testid="teacher-learning-analytics"]', "learning analytics visible", flow)
    expect_visible(page, '[data-testid="teacher-analytics-summary"]', "analytics summary visible", flow)
    expect_visible(page, '[data-testid="teacher-analytics-chapter-table"]', "analytics chapter table visible", flow)
    expect_visible(page, '[data-testid="teacher-analytics-low-mastery-list"]', "low mastery list visible", flow)
    expect_visible(page, '[data-testid="teacher-analytics-feedback-hotspots"]', "feedback hotspots visible", flow)
    click_and_expect_download(
        page,
        page.locator('[data-testid="teacher-analytics-export"]').first,
        flow,
        artifact_dir,
        (".csv", ".json"),
        "teacher analytics export download verified",
    )

    approve = page.locator('[data-testid="review-action-approve"]').first
    approve.locator('textarea[name="review_comment"]').fill("Attempt approve without override for policy block.")
    approve.locator('[data-testid="review-submit"]').click()
    expect_visible(page, '[data-testid="review-error"]', "policy block error visible", flow)
    page.wait_for_function(
        """() => document.querySelector('[data-testid="review-error"]')?.innerText.includes('request_id=')""",
        timeout=10000,
    )
    add_step(flow, "policy block request_id visible")


def run_instructor_flow(
    page,
    summary: dict[str, Any],
    flow: dict[str, Any],
    artifact_dir: Path,
    capture: FlowCapture,
) -> None:
    del artifact_dir
    instructor = summary["users"]["teacher"]
    open_frontend(page, capture.port, flow)
    probe_external_block(page, capture, flow)
    login(page, instructor["email"], instructor["password"], flow)
    dashboard = expect_visible(
        page,
        '[data-testid="instructor-dashboard"]',
        "Instructor English dashboard visible",
        flow,
    )
    assert page.locator('[data-testid="concept-review-nav"]').count() == 0
    add_step(flow, "Reviewer Console navigation hidden for Instructor")
    text = dashboard.inner_text()
    assert "Teacher Dashboard" in page.locator("body").inner_text()
    for forbidden_copy in ("概念卡审核", "中文证据", "选择正确中文候选"):
        assert forbidden_copy not in text
    add_step(flow, "Instructor primary dashboard is English course-side")
    page.wait_for_timeout(300)
    reviewer_only_fragments = (
        "/api/concept-cards/review-queue",
        "/reviews",
        "/review-case",
        "/api/concept-cards/student-feedback-queue",
        "/api/quality-control",
    )
    unexpected = [
        url
        for url in flow["requests"]
        if any(fragment in url for fragment in reviewer_only_fragments)
    ]
    assert unexpected == [], f"Instructor prefetched Reviewer-only data: {unexpected}"
    add_step(flow, "Instructor initialization did not prefetch Reviewer data")


def run_reviewer_flow(
    page,
    summary: dict[str, Any],
    flow: dict[str, Any],
    artifact_dir: Path,
    capture: FlowCapture,
) -> None:
    del artifact_dir
    reviewer = summary["users"]["reviewer"]
    open_frontend(page, capture.port, flow)
    probe_external_block(page, capture, flow)
    login(page, reviewer["email"], reviewer["password"], flow)
    expect_visible(
        page,
        '[data-testid="concept-review-nav"]',
        "Reviewer Console navigation visible",
        flow,
    )
    assert "Reviewer Console" in page.locator("body").inner_text()
    add_step(flow, "Reviewer Console product identity visible")
    expect_visible(page, '[data-testid="review-queue"]', "Reviewer queue readable", flow)
    page.locator('[data-testid="review-filter-course"]').fill("DEMO Signals and Systems")
    with page.expect_response(
        lambda response: (
            "/api/concept-cards/review-queue?" in response.url
            and "course=DEMO+Signals+and+Systems" in response.url
        ),
        timeout=10000,
    ):
        page.locator("form").filter(
            has=page.locator('[data-testid="review-filter-course"]')
        ).locator("button").first.click()
    expect_visible(
        page,
        '[data-testid="review-card-row"]',
        "Reviewer queue filtered",
        flow,
    )
    fourier_uid = summary["card_uids"]["fourier"]
    row = page.locator(
        f'[data-testid="review-card-row"][data-card-uid="{fourier_uid}"]'
    )
    with page.expect_response(
        lambda response: response.url.endswith("/review-case"),
        timeout=10000,
    ):
        row.click()
    expect_visible(page, '[data-testid="review-card-detail"]', "Reviewer detail visible", flow)
    page.get_by_text("Fourier transform", exact=True).first.wait_for(
        state="visible",
        timeout=10000,
    )
    expect_visible(
        page,
        '[data-testid="teacher-alignment-review-case"]',
        "Task 12J-B review case readable by Reviewer",
        flow,
    )
    expect_visible(
        page,
        '[data-testid="english-evidence-list"] .quote',
        "Reviewer English evidence visible",
        flow,
    )
    expect_visible(
        page,
        '[data-testid="chinese-evidence-list"] .quote',
        "Reviewer Chinese evidence visible",
        flow,
    )
    # The detail, history, and review-case requests render the same panel.
    # Wait until all three have settled so a late render cannot erase the
    # required rationale between fill and submit.
    page.wait_for_load_state("networkidle", timeout=10000)
    accept_form = page.locator("form").filter(
        has=page.locator('[data-testid="review-action-accept-recommendation"]')
    ).first
    review_comment = "Reviewer browser smoke accepts the governed recommendation."
    accept_comment = accept_form.locator('textarea[name="review_comment"]')
    accept_comment.fill(review_comment)
    assert accept_comment.input_value() == review_comment
    with page.expect_response(
        lambda response: (
            response.request.method == "POST"
            and response.url.endswith("/review")
        ),
        timeout=30000,
    ) as review_response:
        accept_form.locator('[data-testid="review-action-accept-recommendation"]').click()
    assert review_response.value.status == 200
    page.get_by_text("Reviewer review saved.", exact=False).wait_for(
        state="visible",
        timeout=10000,
    )
    add_step(flow, "Reviewer decision saved")
    page.wait_for_function(
        """() => document.querySelector('[data-testid="teacher-alignment-review-case"]')?.innerText.includes('HUMAN_APPROVED')""",
        timeout=10000,
    )
    add_step(flow, "Reviewer safe approval preserved machine decision and audit")
    page.locator('[data-testid="review-generate-draft"]').click()
    draft = expect_visible(
        page,
        '[data-testid="teacher-draft-editor"]',
        "Reviewer fake draft generated",
        flow,
    )
    assert "NOT_PUBLISHED" in draft.inner_text()
    add_step(flow, "Reviewer fake draft remained unpublished")


def run_one_flow(playwright_browser, flow_name: str, base_dir: Path, artifacts_dir: Path, blocked_external_requests: list[dict[str, Any]], headed: bool) -> dict[str, Any]:
    flow = flow_result(flow_name)
    flow["status"] = "RUNNING"
    flow_dir = base_dir / flow_name
    database = flow_dir / "e2e.db"
    uploads = flow_dir / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    runtime = run_setup(database, uploads, flow_name)
    port = find_free_port()
    server, thread = start_server(runtime["app_module"], port)
    context = None
    page = None
    capture = FlowCapture(flow, blocked_external_requests, port)
    try:
        context = playwright_browser.new_context(accept_downloads=True)
        context.route("**/*", capture.route)
        page = context.new_page()
        capture.attach_page(page)
        if flow_name == "student":
            run_student_flow(
                page,
                runtime["summary"],
                flow,
                artifacts_dir,
                capture,
                runtime["app_module"],
            )
        elif flow_name == "instructor":
            run_instructor_flow(page, runtime["summary"], flow, artifacts_dir, capture)
        elif flow_name == "reviewer":
            run_reviewer_flow(page, runtime["summary"], flow, artifacts_dir, capture)
        else:
            raise ValueError(f"unknown flow: {flow_name}")
    except Exception as exc:
        add_step(flow, "flow failed", "FAIL", str(exc))
        if page is not None:
            artifacts_dir.mkdir(parents=True, exist_ok=True)
            try:
                page.screenshot(path=str(artifacts_dir / f"{flow_name}-failure.png"), full_page=True)
            except Exception:
                pass
    finally:
        if context is not None:
            context.close()
        server.shutdown()
        thread.join(timeout=5)

    external_dependencies = [item for item in blocked_external_requests if item.get("source") == "page" and item.get("flow") == flow_name]
    flow["status"] = "FAIL" if flow_has_failures(flow, external_dependencies) else "PASS"
    return flow


def run_browser_checks(
    *,
    base_dir: Path,
    artifact_dir: Path,
    headed: bool = False,
    run_student: bool = True,
    run_instructor: bool = True,
    run_reviewer: bool = True,
) -> dict[str, Any]:
    assert_playwright_available()
    from playwright.sync_api import sync_playwright

    blocked_external_requests: list[dict[str, Any]] = []
    student_flow = flow_result("student")
    instructor_flow = flow_result("instructor")
    reviewer_flow = flow_result("reviewer")
    browser_version = ""

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=not headed)
        except Exception as exc:
            configured = str(os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE") or "").strip()
            fallback = Path(configured) if configured else next(
                (path for path in SYSTEM_CHROMIUM_CANDIDATES if path.exists()), None
            )
            if fallback is None or not fallback.exists():
                raise RuntimeError(
                    "E2E_ENVIRONMENT_UNAVAILABLE: Playwright Chromium runtime is not installed. "
                    "Run `python -m playwright install chromium` in the project environment."
                ) from exc
            browser = playwright.chromium.launch(
                headless=not headed, executable_path=str(fallback)
            )
        browser_version = browser.version
        try:
            if run_student:
                student_flow = run_one_flow(browser, "student", base_dir, artifact_dir, blocked_external_requests, headed)
            if run_instructor:
                instructor_flow = run_one_flow(
                    browser, "instructor", base_dir, artifact_dir, blocked_external_requests, headed
                )
            if run_reviewer:
                reviewer_flow = run_one_flow(
                    browser, "reviewer", base_dir, artifact_dir, blocked_external_requests, headed
                )
        finally:
            browser.close()

    return build_overall_result(
        browser_version=browser_version,
        student_flow=student_flow,
        instructor_flow=instructor_flow,
        reviewer_flow=reviewer_flow,
        blocked_external_requests=blocked_external_requests,
        artifacts_directory=str(artifact_dir),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run LexiBridge real browser E2E checks.")
    parser.add_argument("--json-output", help="Write machine-readable result JSON.")
    parser.add_argument("--headed", action="store_true", help="Run Chromium headed for local debugging.")
    parser.add_argument("--student-only", action="store_true", help="Run only the student browser flow.")
    parser.add_argument("--instructor-only", action="store_true", help="Run only the Instructor browser flow.")
    parser.add_argument(
        "--teacher-only",
        action="store_true",
        help="Compatibility alias for --instructor-only.",
    )
    parser.add_argument("--reviewer-only", action="store_true", help="Run only the Reviewer browser flow.")
    parser.add_argument("--keep-artifacts", action="store_true", help="Keep temp DB/uploads/downloads/screenshots after success.")
    parser.add_argument("--artifacts", help="Optional artifact directory for screenshots/downloads.")
    args = parser.parse_args(argv)

    selected_only = sum(
        bool(value)
        for value in (
            args.student_only,
            args.instructor_only or args.teacher_only,
            args.reviewer_only,
        )
    )
    if selected_only > 1:
        print("Only one of --student-only, --instructor-only/--teacher-only, or --reviewer-only may be used", file=sys.stderr)
        return 1

    base_dir = Path(tempfile.mkdtemp(prefix="lexibridge-browser-e2e-"))
    artifact_dir = Path(args.artifacts).resolve() if args.artifacts else base_dir / "artifacts"
    try:
        try:
            result = run_browser_checks(
                base_dir=base_dir,
                artifact_dir=artifact_dir,
                headed=args.headed,
                run_student=not (
                    args.instructor_only or args.teacher_only or args.reviewer_only
                ),
                run_instructor=not (args.student_only or args.reviewer_only),
                run_reviewer=not (
                    args.student_only or args.instructor_only or args.teacher_only
                ),
            )
            exit_code = 0 if result["status"] == "PASS" else 1
        except RuntimeError as exc:
            if str(exc).startswith("E2E_ENVIRONMENT_UNAVAILABLE"):
                result = build_overall_result(
                    status="E2E_ENVIRONMENT_UNAVAILABLE",
                    message=str(exc),
                    artifacts_directory=str(artifact_dir),
                )
                exit_code = E2E_ENVIRONMENT_UNAVAILABLE
            else:
                result = build_overall_result(status="FAIL", message=str(exc), artifacts_directory=str(artifact_dir))
                exit_code = 1
        except Exception as exc:
            result = build_overall_result(status="FAIL", message=str(exc), artifacts_directory=str(artifact_dir))
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
