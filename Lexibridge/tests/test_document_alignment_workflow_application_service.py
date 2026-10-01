import dataclasses
import os
from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError

from services.document_alignment_workflow_contract import (
    FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE,
    FORMAL_DOCUMENT_ALIGNMENT_WORKFLOW_VERSION,
)
from services.document_alignment_workflow_application import (
    DocumentAlignmentSourceAdmissionDecision,
    DocumentAlignmentWorkflowApplicationDependencies,
    DocumentAlignmentWorkflowAuthorizationDecision,
    GovernedKnowledgeSourceSnapshot,
    StartDocumentAlignmentWorkflowCommand,
    start_document_alignment_workflow,
)


ROOT = Path(__file__).resolve().parents[1]


class CountingSession:
    def __init__(self, session):
        self._session = session
        self.commits = 0
        self.rollbacks = 0
        self.flushes = 0

    def add(self, value):
        return self._session.add(value)

    def flush(self):
        self.flushes += 1
        return self._session.flush()

    def commit(self):
        self.commits += 1
        return self._session.commit()

    def rollback(self):
        self.rollbacks += 1
        return self._session.rollback()

    def query(self, *args, **kwargs):
        return self._session.query(*args, **kwargs)


class FailingFlushSession(CountingSession):
    def flush(self):
        self.flushes += 1
        raise RuntimeError("flush failed with LEXIBRIDGE_SENTINEL_SECRET_9C4X")


class FailingCommitSession(CountingSession):
    def commit(self):
        self.commits += 1
        raise RuntimeError("commit failed with LEXIBRIDGE_SENTINEL_SECRET_9C4X")


class RaceQuery:
    def __init__(self, query, race_session, model):
        self._query = query
        self._race_session = race_session
        self._model = model

    def filter_by(self, **kwargs):
        self._query = self._query.filter_by(**kwargs)
        return self

    def first(self):
        if self._model is self._race_session.workflow_run_model and self._race_session.hide_first_workflow_query:
            self._race_session.hide_first_workflow_query = False
            return None
        return self._query.first()

    def all(self):
        return self._query.all()


class RaceIntegritySession(CountingSession):
    def __init__(self, session, workflow_run_model):
        super().__init__(session)
        self.workflow_run_model = workflow_run_model
        self.hide_first_workflow_query = True

    def query(self, model, *args, **kwargs):
        return RaceQuery(self._session.query(model, *args, **kwargs), self, model)

    def flush(self):
        self.flushes += 1
        raise IntegrityError(
            "INSERT",
            {},
            Exception("UNIQUE constraint failed: document_alignment_workflow_runs.requested_by"),
        )


def _snapshot(**overrides):
    values = {
        "source_uid": "source-9c4x",
        "parse_uid": "parse-9c4x",
        "source_version": "1",
        "course": "Signals",
        "chapter": "Frequency",
        "owner_user_id": "teacher-1",
        "visibility": "course",
        "source_status": "active",
        "source_trust_level": "teacher_verified",
        "parse_status": "success",
        "parse_quality": "native_text_ok",
        "usable_chunk_count": 2,
    }
    values.update(overrides)
    return GovernedKnowledgeSourceSnapshot(**values)


def _command(**overrides):
    values = {
        "source_uid": "source-9c4x",
        "requested_by": "teacher-1",
        "request_id": "request-9c4x",
        "idempotency_key": "idem-9c4x",
    }
    values.update(overrides)
    return StartDocumentAlignmentWorkflowCommand(**values)


def _allowed_authorization(*args, **kwargs):
    return DocumentAlignmentWorkflowAuthorizationDecision(allowed=True)


def _allowed_admission(*args, **kwargs):
    return DocumentAlignmentSourceAdmissionDecision(allowed=True)


def _dependencies(app_module, session=None, snapshot=None, **overrides):
    snapshot = snapshot if snapshot is not None else _snapshot()
    values = {
        "session": session or CountingSession(app_module.db.session),
        "workflow_run_model": app_module.DocumentAlignmentWorkflowRun,
        "background_job_model": app_module.BackgroundJob,
        "audit_record_model": app_module.AuditRecord,
        "source_loader": lambda source_uid: snapshot if source_uid == snapshot.source_uid else None,
        "authorization_checker": _allowed_authorization,
        "source_admission_checker": _allowed_admission,
        "current_time_factory": lambda: "2026-07-18T00:00:00Z",
        "uid_factory": lambda: "workflow-run-9c4x",
        "workflow_version": FORMAL_DOCUMENT_ALIGNMENT_WORKFLOW_VERSION,
    }
    values.update(overrides)
    return DocumentAlignmentWorkflowApplicationDependencies(**values)


@pytest.fixture()
def clean_admission_tables(app_module):
    with app_module.app.app_context():
        app_module.db.session.rollback()
        app_module.DocumentAlignmentWorkflowItem.query.delete()
        app_module.DocumentAlignmentWorkflowRun.query.delete()
        app_module.BackgroundJob.query.filter_by(job_type=FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE).delete()
        app_module.AuditRecord.query.filter_by(event_type="document_alignment_requested").delete()
        app_module.db.session.commit()
    yield
    with app_module.app.app_context():
        app_module.db.session.rollback()
        app_module.DocumentAlignmentWorkflowItem.query.delete()
        app_module.DocumentAlignmentWorkflowRun.query.delete()
        app_module.BackgroundJob.query.filter_by(job_type=FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE).delete()
        app_module.AuditRecord.query.filter_by(event_type="document_alignment_requested").delete()
        app_module.db.session.commit()


def test_service_module_static_boundaries_and_frozen_dtos():
    source = (ROOT / "backend" / "services" / "document_alignment_workflow_application.py").read_text(encoding="utf-8")

    forbidden = [
        "from flask",
        "import flask",
        "backend.app",
        "backend.routes",
        "urllib",
        "requests",
        "httpx",
        "socket",
        "os.environ",
        "jsonify",
        "Response",
        "WorkflowItem(",
        "AlignmentRun(",
        "TerminologyCard(",
        "AICallLog(",
        "AlignmentVerificationRun(",
        "ConceptAlignmentCard(",
    ]
    for text in forbidden:
        assert text not in source

    command = _command()
    dependencies = DocumentAlignmentWorkflowApplicationDependencies(
        session=object(),
        workflow_run_model=object(),
        background_job_model=object(),
        audit_record_model=object(),
        source_loader=lambda source_uid: None,
        authorization_checker=lambda actor, snapshot: DocumentAlignmentWorkflowAuthorizationDecision(False),
        source_admission_checker=lambda snapshot: DocumentAlignmentSourceAdmissionDecision(False),
        current_time_factory=lambda: "",
        uid_factory=lambda: "",
    )
    result = start_document_alignment_workflow(command, dependencies)

    for value in [command, dependencies, result]:
        with pytest.raises(dataclasses.FrozenInstanceError):
            value.__setattr__("source_uid" if hasattr(value, "source_uid") else "outcome", "changed")


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_uid", ""),
        ("source_uid", "   "),
        ("requested_by", ""),
        ("request_id", ""),
        ("idempotency_key", ""),
    ],
)
def test_command_required_fields(field, value):
    values = dataclasses.asdict(_command())
    values[field] = value

    with pytest.raises(ValueError):
        StartDocumentAlignmentWorkflowCommand(**values)


def test_blocked_admission_paths_do_not_write_or_commit(app_module, clean_admission_tables):
    with app_module.app.app_context():
        session = CountingSession(app_module.db.session)
        denied = _dependencies(
            app_module,
            session=session,
            authorization_checker=lambda actor, snapshot: DocumentAlignmentWorkflowAuthorizationDecision(
                allowed=False,
                safe_error_code="DOCUMENT_ALIGNMENT_SOURCE_NOT_AVAILABLE",
                safe_error_message="Source is not available.",
            ),
        )
        result = start_document_alignment_workflow(_command(), denied)

        assert result.outcome == "source_not_available"
        assert session.commits == 0
        assert app_module.DocumentAlignmentWorkflowRun.query.count() == 0
        assert app_module.BackgroundJob.query.filter_by(job_type=FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE).count() == 0
        assert app_module.AuditRecord.query.filter_by(event_type="document_alignment_requested").count() == 0

        parse_blocked = _dependencies(
            app_module,
            session=session,
            source_admission_checker=lambda snapshot: DocumentAlignmentSourceAdmissionDecision(
                allowed=False,
                safe_error_code="DOCUMENT_ALIGNMENT_PARSE_BLOCKED",
                safe_error_message="Parse is blocked.",
                outcome="parse_blocked",
            ),
        )
        result = start_document_alignment_workflow(_command(), parse_blocked)

        assert result.outcome == "parse_blocked"
        assert session.commits == 0
        assert app_module.DocumentAlignmentWorkflowRun.query.count() == 0


def test_created_reused_and_conflict_paths(app_module, clean_admission_tables):
    with app_module.app.app_context():
        session = CountingSession(app_module.db.session)
        dependencies = _dependencies(app_module, session=session)

        created = start_document_alignment_workflow(_command(), dependencies)

        assert created.outcome == "created"
        assert created.run_uid == "workflow-run-9c4x"
        assert created.job_uid
        assert created.status == "queued"
        assert created.stage == "queued"
        assert created.reused is False
        assert session.commits == 1
        assert app_module.DocumentAlignmentWorkflowRun.query.count() == 1
        assert app_module.DocumentAlignmentWorkflowItem.query.count() == 0
        assert app_module.BackgroundJob.query.filter_by(job_type=FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE).count() == 1
        assert app_module.AuditRecord.query.filter_by(event_type="document_alignment_requested").count() == 1

        replay_session = CountingSession(app_module.db.session)
        replay = start_document_alignment_workflow(_command(request_id="request-9c4x-replay"), _dependencies(app_module, session=replay_session))

        assert replay.outcome == "reused"
        assert replay.reused is True
        assert replay.run_uid == created.run_uid
        assert replay_session.commits == 0
        assert app_module.DocumentAlignmentWorkflowRun.query.count() == 1
        assert app_module.BackgroundJob.query.filter_by(job_type=FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE).count() == 1
        assert app_module.AuditRecord.query.filter_by(event_type="document_alignment_requested").count() == 1

        changed_snapshot = _snapshot(parse_uid="parse-9c4x-new")
        conflict_session = CountingSession(app_module.db.session)
        conflict = start_document_alignment_workflow(
            _command(request_id="request-9c4x-conflict"),
            _dependencies(app_module, session=conflict_session, snapshot=changed_snapshot),
        )

        assert conflict.outcome == "idempotency_conflict"
        assert conflict.error_code == "DOCUMENT_ALIGNMENT_IDEMPOTENCY_CONFLICT"
        assert conflict_session.commits == 0
        assert app_module.DocumentAlignmentWorkflowRun.query.count() == 1


def test_idempotency_scope_allows_different_key_user_source_and_workflow_version(app_module, clean_admission_tables):
    with app_module.app.app_context():
        first = start_document_alignment_workflow(_command(), _dependencies(app_module))
        second = start_document_alignment_workflow(_command(idempotency_key="idem-9c4x-2"), _dependencies(app_module, uid_factory=lambda: "workflow-run-key-2"))
        third = start_document_alignment_workflow(_command(requested_by="teacher-2"), _dependencies(app_module, uid_factory=lambda: "workflow-run-teacher-2"))
        fourth_snapshot = _snapshot(source_uid="source-9c4x-other")
        fourth = start_document_alignment_workflow(
            _command(source_uid=fourth_snapshot.source_uid),
            _dependencies(app_module, snapshot=fourth_snapshot, uid_factory=lambda: "workflow-run-source-2"),
        )
        fifth = start_document_alignment_workflow(
            _command(),
            _dependencies(app_module, uid_factory=lambda: "workflow-run-version-2", workflow_version="formal-document-alignment-v2"),
        )

        assert [first.outcome, second.outcome, third.outcome, fourth.outcome, fifth.outcome] == [
            "created",
            "created",
            "created",
            "created",
            "created",
        ]
        assert app_module.DocumentAlignmentWorkflowRun.query.count() == 5
        assert app_module.BackgroundJob.query.filter_by(job_type=FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE).count() == 5


def test_unique_constraint_race_recovers_as_reused(app_module, clean_admission_tables):
    with app_module.app.app_context():
        created = start_document_alignment_workflow(_command(), _dependencies(app_module))
        race_session = RaceIntegritySession(app_module.db.session, app_module.DocumentAlignmentWorkflowRun)

        recovered = start_document_alignment_workflow(
            _command(request_id="request-9c4x-race"),
            _dependencies(app_module, session=race_session),
        )

        assert created.outcome == "created"
        assert recovered.outcome == "reused"
        assert recovered.run_uid == created.run_uid
        assert race_session.rollbacks == 1
        assert app_module.DocumentAlignmentWorkflowRun.query.count() == 1
        assert app_module.BackgroundJob.query.filter_by(job_type=FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE).count() == 1


@pytest.mark.parametrize("session_cls", [FailingFlushSession, FailingCommitSession])
def test_persistence_failures_rollback_and_do_not_leak_secret(app_module, clean_admission_tables, session_cls):
    with app_module.app.app_context():
        os.environ["DOCUMENT_ALIGNMENT_TEST_SECRET"] = "LEXIBRIDGE_SENTINEL_SECRET_9C4X"
        session = session_cls(app_module.db.session)
        result = start_document_alignment_workflow(_command(), _dependencies(app_module, session=session))

        assert result.outcome == "persistence_error"
        assert result.error_code == "DOCUMENT_ALIGNMENT_PERSISTENCE_ERROR"
        assert "LEXIBRIDGE_SENTINEL_SECRET_9C4X" not in result.error_message
        assert session.rollbacks == 1
        assert app_module.DocumentAlignmentWorkflowRun.query.count() == 0
        assert app_module.BackgroundJob.query.filter_by(job_type=FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE).count() == 0
        assert app_module.AuditRecord.query.filter_by(event_type="document_alignment_requested").count() == 0


def test_job_and_audit_failure_roll_back_all_records(app_module, clean_admission_tables):
    with app_module.app.app_context():
        class BrokenJob:
            def __init__(self, **kwargs):
                raise RuntimeError("job construction failed")

        result = start_document_alignment_workflow(
            _command(),
            _dependencies(app_module, background_job_model=BrokenJob),
        )
        assert result.outcome == "persistence_error"
        assert app_module.DocumentAlignmentWorkflowRun.query.count() == 0

        def failing_audit_recorder(*args, **kwargs):
            raise RuntimeError("audit failed")

        result = start_document_alignment_workflow(
            _command(),
            _dependencies(app_module, audit_recorder=failing_audit_recorder),
        )
        assert result.outcome == "persistence_error"
        assert app_module.DocumentAlignmentWorkflowRun.query.count() == 0
        assert app_module.BackgroundJob.query.filter_by(job_type=FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE).count() == 0


def test_no_execution_no_dual_write_and_minimal_job_payload(app_module, clean_admission_tables):
    with app_module.app.app_context():
        before_counts = {
            "verification": app_module.AlignmentVerificationRun.query.count(),
            "items": app_module.DocumentAlignmentWorkflowItem.query.count(),
            "cards": app_module.ConceptAlignmentCard.query.count(),
            "legacy_runs": app_module.AlignmentRun.query.count(),
            "legacy_terms": app_module.TerminologyCard.query.count(),
            "ai_call_logs": app_module.AICallLog.query.count(),
        }
        result = start_document_alignment_workflow(_command(), _dependencies(app_module))

        job = app_module.BackgroundJob.query.filter_by(job_type=FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE).one()
        assert job.input_json
        assert set(__import__("json").loads(job.input_json)) == {"workflow_run_uid", "workflow_version"}
        assert app_module.AlignmentVerificationRun.query.count() == before_counts["verification"]
        assert app_module.DocumentAlignmentWorkflowItem.query.count() == before_counts["items"]
        assert app_module.ConceptAlignmentCard.query.count() == before_counts["cards"]
        assert app_module.AlignmentRun.query.count() == before_counts["legacy_runs"]
        assert app_module.TerminologyCard.query.count() == before_counts["legacy_terms"]
        assert app_module.AICallLog.query.count() == before_counts["ai_call_logs"]
        assert "LEXIBRIDGE_SENTINEL_SECRET_9C4X" not in dataclasses.asdict(result).values()
