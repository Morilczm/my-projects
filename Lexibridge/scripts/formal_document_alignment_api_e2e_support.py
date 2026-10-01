"""Test-only support for formal document-alignment HTTP E2E checks."""

from __future__ import annotations

import json
import io
import socket
import threading
import time
import uuid
from contextlib import contextmanager, redirect_stdout
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, build_opener

from services.document_alignment_workflow_contract import (
    FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE,
)


PREFIX = "formal-api-e2e-9c5g-v3"
FORBIDDEN_PUBLIC_KEYS = frozenset({
    "attempt_count",
    "database_id",
    "event_identity",
    "execution_attempt",
    "execution_key",
    "heartbeat_at",
    "input_fingerprint",
    "job_payload",
    "job_uid",
    "lease_expires_at",
    "lease_token",
    "locked_at",
    "locked_by",
    "max_attempts",
    "preflight_run_uid",
    "safe_input_fingerprint",
    "usage_record_uid",
    "worker_id",
})


@dataclass(frozen=True)
class HttpJsonResponse:
    status: int
    body: dict
    headers: dict[str, str]


@dataclass(frozen=True)
class AuthenticatedHttpClient:
    token: str
    opener: object


@dataclass(frozen=True)
class ThreadedServer:
    base_url: str
    server: object
    thread: threading.Thread


@dataclass(frozen=True)
class PollingResult:
    terminal_status: str
    timeline: tuple[str, ...]


class PollingTimeout(RuntimeError):
    pass


_STATUS_RANK = {
    "queued": 0,
    "validating": 1,
    "processing": 2,
    "ready_for_review": 3,
    "completed_with_warnings": 3,
    "blocked": 3,
    "failed": 3,
}
_TERMINAL_STATUSES = frozenset({
    "ready_for_review",
    "completed_with_warnings",
    "blocked",
    "failed",
})


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def run_quiet_e2e_setup(base_e2e, database, uploads, flow_name):
    original_run = base_e2e.subprocess.run

    def captured_run(*args, **kwargs):
        kwargs["capture_output"] = True
        return original_run(*args, **kwargs)

    with patch.object(base_e2e.subprocess, "run", side_effect=captured_run):
        with redirect_stdout(io.StringIO()):
            return base_e2e.run_setup(database, uploads, flow_name)


@contextmanager
def start_threaded_server(app):
    from werkzeug.serving import make_server

    port = _free_port()
    server = make_server("127.0.0.1", port, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    runtime = ThreadedServer(f"http://127.0.0.1:{port}", server, thread)
    try:
        yield runtime
    finally:
        server.shutdown()
        thread.join(timeout=5)


def http_json(
    base_url: str,
    path: str,
    *,
    method: str = "GET",
    token: str = "",
    headers: dict[str, str] | None = None,
    body: dict | None = None,
    opener=None,
) -> HttpJsonResponse:
    request_headers = {"Accept": "application/json", **(headers or {})}
    if token:
        request_headers["Authorization"] = f"Bearer {token}"
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    request = Request(
        f"{base_url}{path}",
        data=data,
        headers=request_headers,
        method=method,
    )
    client = opener or build_opener()
    try:
        response = client.open(request, timeout=15)
    except HTTPError as exc:
        response = exc
    raw = response.read().decode("utf-8")
    payload = json.loads(raw) if raw else {}
    return HttpJsonResponse(
        status=int(response.status),
        body=payload,
        headers={key: value for key, value in response.headers.items()},
    )


def login(base_url: str, email: str, password: str, *, opener=None) -> AuthenticatedHttpClient:
    client = opener or build_opener()
    response = http_json(
        base_url,
        "/api/auth/login",
        method="POST",
        body={"email": email, "password": password},
        opener=client,
    )
    if response.status != 200:
        raise AssertionError(response.body)
    return AuthenticatedHttpClient(str(response.body["token"]), client)


def poll_until_terminal(
    fetch,
    *,
    timeout_seconds: float,
    poll_interval_seconds: float,
) -> PollingResult:
    deadline = time.monotonic() + max(0.0, float(timeout_seconds))
    timeline = []
    previous_rank = -1
    while True:
        payload = fetch()
        status = str(payload.get("data", {}).get("status", ""))
        if status not in _STATUS_RANK:
            raise AssertionError(f"unexpected formal workflow status: {status or '<missing>'}")
        rank = _STATUS_RANK[status]
        if rank < previous_rank:
            raise AssertionError(f"formal workflow status regressed from {timeline[-1]} to {status}")
        previous_rank = rank
        if not timeline or timeline[-1] != status:
            timeline.append(status)
        if status in _TERMINAL_STATUSES:
            return PollingResult(status, tuple(timeline))
        if time.monotonic() >= deadline:
            raise PollingTimeout("formal workflow polling timed out")
        if poll_interval_seconds > 0:
            time.sleep(float(poll_interval_seconds))


def assert_safe_public_payload(payload, *, sentinel: str = "") -> None:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    if sentinel:
        assert sentinel not in serialized
    assert "Traceback (most recent call last)" not in serialized
    assert "/Users/" not in serialized
    assert "/private/" not in serialized

    def visit(value):
        if isinstance(value, dict):
            forbidden = set(value) & FORBIDDEN_PUBLIC_KEYS
            assert not forbidden, f"sensitive response fields: {sorted(forbidden)}"
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(payload)


@contextmanager
def block_external_network(attempts=None):
    attempts = attempts if attempts is not None else []
    original = socket.create_connection

    def guarded(address, *args, **kwargs):
        host = str(address[0]).casefold()
        if host not in {"127.0.0.1", "localhost", "::1"}:
            attempts.append({"source": "python"})
            raise AssertionError(f"external network request blocked: {host}")
        return original(address, *args, **kwargs)

    with patch("socket.create_connection", side_effect=guarded):
        yield attempts


def create_formal_source(
    app_module,
    *,
    suffix: str,
    terms: tuple[str, ...],
    bilingual_terms: dict[str, str],
    owner_email: str = "teacher.test@lexibridge.local",
    course_name: str = "OCR Test Course",
):
    unique = uuid.uuid4().hex[:10]
    identity = f"{suffix[:16]}-{unique}"
    teacher = app_module.User.query.filter_by(email=owner_email).one()
    course = app_module.Course.query.filter_by(name=course_name).one()
    parse_en = app_module.DocumentParseRecord(
        parse_uid=f"{PREFIX}-p-en-{identity}",
        source_filename=f"{PREFIX}-source.txt",
        parse_status="success",
        quality_status="native_text_ok",
        block_count=max(1, len(terms)),
        extracted_text_chars=max(64, sum(len(term) for term in terms)),
    )
    parse_zh = app_module.DocumentParseRecord(
        parse_uid=f"{PREFIX}-p-zh-{identity}",
        source_filename=f"{PREFIX}-reference.txt",
        parse_status="success",
        quality_status="native_text_ok",
        block_count=max(1, len(bilingual_terms)),
        extracted_text_chars=max(64, sum(len(value) for value in bilingual_terms.values())),
    )
    source_en = app_module.KnowledgeSource(
        source_uid=f"{PREFIX}-s-en-{identity}",
        title="Formal API E2E English source",
        name="Formal API E2E English source",
        course_id=course.id,
        course=course.name,
        chapter="Frequency",
        owner_user_id=teacher.id,
        visibility="course",
        language="en",
        source_type="course_material",
        source_role="english_course_material",
        trust_level="teacher_verified",
        parse_uid=parse_en.parse_uid,
        version=1,
        quality_status="native_text_ok",
        status="active",
        allow_derivative_cards=True,
    )
    source_zh = app_module.KnowledgeSource(
        source_uid=f"{PREFIX}-s-zh-{identity}",
        title="Formal API E2E bilingual source",
        name="Formal API E2E bilingual source",
        course_id=course.id,
        course=course.name,
        chapter="Frequency",
        owner_user_id=teacher.id,
        visibility="course",
        language="mixed",
        source_type="reference",
        source_role="bilingual_reference",
        trust_level="teacher_verified",
        parse_uid=parse_zh.parse_uid,
        version=1,
        quality_status="native_text_ok",
        status="active",
        allow_derivative_cards=True,
    )
    app_module.db.session.add_all([parse_en, parse_zh, source_en, source_zh])
    app_module.db.session.flush()
    for index, term in enumerate(terms):
        app_module.db.session.add(
            app_module.KnowledgeChunk(
                chunk_uid=f"{PREFIX}-c-en-{unique}-{index}",
                source_uid=source_en.source_uid,
                knowledge_source_id=source_en.id,
                document_id=0,
                parse_uid=parse_en.parse_uid,
                course=course.name,
                chapter="Frequency",
                chunk_index=index,
                content=term,
                language="en",
                visibility="course",
                status="active",
                is_active=True,
                quality_status="native_text_ok",
                trust_level="teacher_verified",
            )
        )
    for index, (english, chinese) in enumerate(bilingual_terms.items()):
        app_module.db.session.add(
            app_module.KnowledgeChunk(
                chunk_uid=f"{PREFIX}-c-zh-{unique}-{index}",
                source_uid=source_zh.source_uid,
                knowledge_source_id=source_zh.id,
                document_id=0,
                parse_uid=parse_zh.parse_uid,
                course=course.name,
                chapter="Frequency",
                chunk_index=index,
                content=f"{chinese}（{english}）用于课程概念分析。",
                language="mixed",
                visibility="course",
                status="active",
                is_active=True,
                quality_status="native_text_ok",
                trust_level="teacher_verified",
            )
        )
    app_module.db.session.commit()
    return SimpleNamespace(source_uid=source_en.source_uid, source=source_en)


def create_e2e_teacher(
    app_module,
    *,
    suffix: str,
    course_member: bool,
    course_name: str = "OCR Test Course",
):
    email = f"{PREFIX}-{suffix}@example.test"
    password = "Teacher1234"
    user = app_module.User(
        username=f"{PREFIX}-{suffix}",
        email=email,
        password_hash=app_module.generate_password_hash(password, method="pbkdf2:sha256"),
        role="teacher",
        is_verified=True,
        created_at=app_module.current_time_text(),
    )
    app_module.db.session.add(user)
    app_module.db.session.flush()
    if course_member:
        course = app_module.Course.query.filter_by(name=course_name).one()
        app_module.db.session.add(
            app_module.CourseMember(
                course_id=course.id,
                user_id=user.id,
                role="teacher",
                role_in_course="teacher",
                status="active",
                created_at=app_module.current_time_text(),
                joined_at=app_module.current_time_text(),
            )
        )
    app_module.db.session.commit()
    return SimpleNamespace(email=email, password=password, user_id=user.id)


def find_job_for_run(app_module, run_uid: str):
    return app_module.BackgroundJob.query.filter(
        app_module.BackgroundJob.job_type == FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE,
        app_module.BackgroundJob.input_json.like(f"%{run_uid}%"),
    ).one()


def cleanup_formal_api_state(app_module) -> None:
    session = app_module.db.session
    session.rollback()
    runs = app_module.DocumentAlignmentWorkflowRun.query.filter(
        app_module.DocumentAlignmentWorkflowRun.source_uid.like(f"{PREFIX}%")
    ).all()
    run_ids = [run.id for run in runs]
    run_uids = [run.run_uid for run in runs]
    items = (
        app_module.DocumentAlignmentWorkflowItem.query.filter(
            app_module.DocumentAlignmentWorkflowItem.workflow_run_id.in_(run_ids)
        ).all()
        if run_ids
        else []
    )
    item_uids = [item.item_uid for item in items]
    mappings = (
        app_module.DocumentAlignmentItemVerificationExecution.query.filter(
            app_module.DocumentAlignmentItemVerificationExecution.workflow_run_uid.in_(run_uids)
        ).all()
        if run_uids
        else []
    )
    execution_keys = [mapping.execution_key for mapping in mappings]
    card_uids = [mapping.draft_card_uid for mapping in mappings if mapping.draft_card_uid]
    if execution_keys:
        app_module.AlignmentProviderUsageRecord.query.filter(
            app_module.AlignmentProviderUsageRecord.execution_key.in_(execution_keys)
        ).delete(synchronize_session=False)
        app_module.AlignmentVerificationRun.query.filter(
            app_module.AlignmentVerificationRun.execution_key.in_(execution_keys)
        ).delete(synchronize_session=False)
        app_module.AlignmentProviderPreflightRun.query.filter(
            app_module.AlignmentProviderPreflightRun.execution_key.in_(execution_keys)
        ).delete(synchronize_session=False)
    if run_uids or item_uids:
        app_module.AuditRecord.query.filter(
            app_module.AuditRecord.target_uid.in_(run_uids + item_uids)
        ).delete(synchronize_session=False)
    if run_uids:
        app_module.DocumentAlignmentItemVerificationExecution.query.filter(
            app_module.DocumentAlignmentItemVerificationExecution.workflow_run_uid.in_(run_uids)
        ).delete(synchronize_session=False)
    if run_ids:
        app_module.DocumentAlignmentWorkflowItem.query.filter(
            app_module.DocumentAlignmentWorkflowItem.workflow_run_id.in_(run_ids)
        ).delete(synchronize_session=False)
        app_module.DocumentAlignmentWorkflowRun.query.filter(
            app_module.DocumentAlignmentWorkflowRun.id.in_(run_ids)
        ).delete(synchronize_session=False)
    if card_uids:
        app_module.ConceptAlignmentCard.query.filter(
            app_module.ConceptAlignmentCard.card_uid.in_(card_uids)
        ).delete(synchronize_session=False)
    for run_uid in run_uids:
        app_module.BackgroundJob.query.filter(
            app_module.BackgroundJob.job_type == FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE,
            app_module.BackgroundJob.input_json.like(f"%{run_uid}%"),
        ).delete(synchronize_session=False)
    app_module.KnowledgeChunk.query.filter(
        app_module.KnowledgeChunk.source_uid.like(f"{PREFIX}%")
    ).delete(synchronize_session=False)
    app_module.KnowledgeSource.query.filter(
        app_module.KnowledgeSource.source_uid.like(f"{PREFIX}%")
    ).delete(synchronize_session=False)
    app_module.DocumentParseRecord.query.filter(
        app_module.DocumentParseRecord.parse_uid.like(f"{PREFIX}%")
    ).delete(synchronize_session=False)
    user_ids = [
        row.id
        for row in app_module.User.query.filter(
            app_module.User.email.like(f"{PREFIX}%")
        ).all()
    ]
    if user_ids:
        app_module.AuthToken.query.filter(
            app_module.AuthToken.user_id.in_(user_ids)
        ).delete(synchronize_session=False)
        app_module.CourseMember.query.filter(
            app_module.CourseMember.user_id.in_(user_ids)
        ).delete(synchronize_session=False)
        app_module.User.query.filter(app_module.User.id.in_(user_ids)).delete(
            synchronize_session=False
        )
    standard_user_ids = [
        row.id
        for row in app_module.User.query.filter(
            app_module.User.email.in_([
                "teacher@example.com",
                "student@example.com",
                "admin@example.com",
            ])
        ).all()
    ]
    if standard_user_ids:
        app_module.AuthToken.query.filter(
            app_module.AuthToken.user_id.in_(standard_user_ids)
        ).delete(synchronize_session=False)
    session.commit()
    session.expunge_all()
