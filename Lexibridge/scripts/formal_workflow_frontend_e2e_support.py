"""Shared test-only support for the formal workflow frontend E2E runners."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from scripts.formal_document_alignment_api_e2e_support import create_formal_source


SENTINEL = "LEXIBRIDGE_SENTINEL_SECRET_9C5H"


@dataclass(frozen=True)
class VisibleFormalSource:
    document_id: int
    source_uid: str


def prepare_visible_formal_source(
    app_module,
    summary,
    *,
    suffix: str,
    terms: tuple[str, ...],
    bilingual_terms: dict[str, str],
) -> VisibleFormalSource:
    teacher = app_module.User.query.filter_by(
        email=summary["users"]["teacher"]["email"]
    ).one()
    course = app_module.Course.query.filter_by(name=summary["course"]).one()
    prepared = create_formal_source(
        app_module,
        suffix=suffix,
        terms=terms,
        bilingual_terms=bilingual_terms,
        owner_email=teacher.email,
        course_name=course.name,
    )
    document = app_module.Document(
        owner_user_id=teacher.id,
        course_id=course.id,
        scope_type="course",
        filename=f"formal-frontend-{suffix}.txt",
        original_filename=f"formal-frontend-{suffix}.txt",
        content_type="text/plain",
        size_bytes=max(128, sum(len(term) for term in terms)),
        file_type="txt",
        language="en",
        upload_time=app_module.current_time_text(),
        parsing_status="parsed",
        parse_uid=prepared.source.parse_uid,
        source_type="teacher_courseware",
        quality_flags_json="[]",
    )
    app_module.db.session.add(document)
    app_module.db.session.flush()
    prepared.source.document_id = document.id
    prepared.source.license_note = SENTINEL
    app_module.KnowledgeChunk.query.filter_by(
        source_uid=prepared.source_uid
    ).update({"document_id": document.id}, synchronize_session=False)
    app_module.db.session.commit()
    return VisibleFormalSource(document.id, prepared.source_uid)


def attach_request_log(page) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []

    def record(request) -> None:
        records.append({
            "method": request.method,
            "path": urlsplit(request.url).path,
        })

    page.on("request", record)
    return records


def request_count(records, path: str, method: str | None = None) -> int:
    return sum(
        1
        for item in records
        if item["path"] == path and (method is None or item["method"] == method)
    )


def wait_for_request_count(
    page,
    records,
    path: str,
    expected: int,
    *,
    method: str | None = None,
    timeout_seconds: float = 10,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if request_count(records, path, method) >= expected:
            return
        page.wait_for_timeout(50)
    raise AssertionError(f"request count did not reach {expected}: {method or '*'} {path}")


def open_teacher_upload(base_e2e, page, port: int, flow, teacher) -> None:
    base_e2e.open_frontend(page, port, flow)
    base_e2e.login(page, teacher["email"], teacher["password"], flow)
    page.locator("button", has_text="Courseware Upload").first.click()
    page.get_by_test_id("formal-alignment-status").wait_for(state="visible", timeout=10000)


def start_source_from_ui(page, source: VisibleFormalSource, *, duplicate_click: bool = False) -> None:
    button = page.locator(
        f'[data-testid="formal-alignment-start"][data-document-id="{source.document_id}"]'
    ).first
    button.wait_for(state="visible", timeout=10000)
    if duplicate_click:
        button.dblclick(delay=0)
    else:
        button.click()


def current_run_uid(app_module, source_uid: str) -> str:
    run = app_module.DocumentAlignmentWorkflowRun.query.filter_by(
        source_uid=source_uid
    ).order_by(app_module.DocumentAlignmentWorkflowRun.id.desc()).first()
    if run is None:
        raise AssertionError("formal UI did not create a WorkflowRun")
    return run.run_uid


def assert_safe_browser_state(page, *, sentinel: str = SENTINEL) -> list[str]:
    body = page.locator("body").inner_text()
    stored = page.evaluate(
        "() => sessionStorage.getItem('lexibridge.formalAlignment.activeRun.v1') || ''"
    )
    assert sentinel not in body
    assert sentinel not in stored
    parsed = json.loads(stored) if stored else {}
    allowed = {
        "source_uid",
        "idempotency_key",
        "run_uid",
        "location",
        "items_url",
        "started_at",
        "last_status",
        "poll_interval_seconds",
        "page",
        "page_size",
    }
    assert set(parsed) <= allowed
    return sorted(set(parsed))

