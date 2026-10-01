import json
import uuid
from io import BytesIO
from pathlib import Path

from services.document_alignment_workflow_contract import FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE


def auth_header(token):
    return {"Authorization": f"Bearer {token}"}


def test_worker_processes_document_ingestion_job(client, app_module, teacher_token, test_course):
    response = client.post(
        "/api/documents/upload",
        headers=auth_header(teacher_token),
        data={
            "scope_type": "course",
            "course_id": str(test_course.id),
            "language": "en",
            "discipline": "signal_processing",
            "file": (BytesIO(b"Fourier Transform converts a time-domain signal into a frequency-domain representation."), "worker-doc.txt"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    payload = response.get_json()["data"]
    job_id = payload["job_id"]
    document_id = payload["document_id"]

    with app_module.app.app_context():
        job = app_module.run_background_job(job_id, worker_id="pytest-worker")
        document = app_module.db.session.get(app_module.Document, document_id)
        chunks = app_module.DocumentChunk.query.filter_by(document_id=document_id).all()

        assert job.status == "completed"
        assert document.parsing_status in {"parsed", "parsed_with_warnings"}
        assert len(chunks) >= 1
        governed_chunks = app_module.KnowledgeChunk.query.filter_by(document_id=document_id).all()
        assert len(governed_chunks) >= 1
        assert governed_chunks[0].source_uid
        assert governed_chunks[0].chunk_uid
        assert governed_chunks[0].parse_uid == document.parse_uid
        assert app_module.KnowledgeSource.query.filter_by(source_uid=governed_chunks[0].source_uid).first() is not None
        assert app_module.BackgroundJobEvent.query.filter_by(job_id=job_id, event_type="completed").count() == 1


def test_worker_processes_direct_alignment_job(client, app_module, teacher_token, test_course):
    term = f"Worker Direct Alignment {uuid.uuid4().hex[:8]}"
    response = client.post(
        "/api/alignment/run",
        json={
            "scope_type": "course",
            "course_id": test_course.id,
            "english_term": term,
            "courseware_sentence": f"{term} converts a time-domain signal.",
        },
        headers=auth_header(teacher_token),
    )
    assert response.status_code == 200
    payload = response.get_json()["data"]
    job_id = payload["job_id"]
    run_id = payload["alignment_run_id"]

    with app_module.app.app_context():
        job = app_module.run_background_job(job_id, worker_id="pytest-worker")
        run = app_module.db.session.get(app_module.AlignmentRun, run_id)

        assert job.status == "completed"
        assert run.status == "completed"
        assert run.card_created_count == 1
        assert app_module.TerminologyCard.query.filter_by(source_alignment_run_id=run_id).count() == 1


def test_worker_processes_evaluation_job(client, app_module, teacher_token):
    create_response = client.post(
        "/api/evaluation/sets",
        json={
            "name": "pytest_async_eval",
            "discipline": "signal_processing",
            "description": "Async evaluation test",
        },
        headers=auth_header(teacher_token),
    )
    assert create_response.status_code == 200
    set_id = create_response.get_json()["data"]["evaluation_set_id"]

    eval_file = Path(app_module.PROJECT_ROOT) / "tests" / "_tmp_async_eval.jsonl"
    eval_file.write_text(
        json.dumps({
            "item_id": "ASYNC-001",
            "split": "test",
            "discipline": "signal_processing",
            "english_term": "Fourier Transform",
            "expected_chinese_term": "傅里叶变换",
            "english_context": "Fourier Transform converts a time-domain signal.",
            "expected_english_evidence": "Fourier Transform represents a signal by frequency components.",
            "expected_chinese_evidence": "傅里叶变换用于将信号表示为频率分量。",
            "expected_alignment_status": "no_en_evidence",
            "negative_english_evidence": "A hash table maps keys to buckets.",
            "negative_chinese_evidence": "哈希表通过哈希函数映射关键字。",
            "difficulty": "easy",
            "tags": ["core_term"],
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    try:
        import_response = client.post(
            "/api/evaluation/items/import",
            json={"evaluation_set_id": set_id, "file_path": "tests/_tmp_async_eval.jsonl"},
            headers=auth_header(teacher_token),
        )
        assert import_response.status_code == 200

        run_response = client.post(
            "/api/evaluation/run",
            json={"evaluation_set_id": set_id, "split": "test"},
            headers=auth_header(teacher_token),
        )
        assert run_response.status_code == 200
        payload = run_response.get_json()["data"]
        job_id = payload["job_id"]
        run_id = payload["evaluation_run_id"]
        assert payload["job_status"] == "queued"

        with app_module.app.app_context():
            job = app_module.run_background_job(job_id, worker_id="pytest-worker")
            run = app_module.db.session.get(app_module.EvaluationRun, run_id)
            assert job.status == "completed"
            assert run.status == "completed"
            assert run.input_count == 1
            assert "# LexiBridge AI Evaluation Report" in run.report_markdown
    finally:
        try:
            eval_file.unlink()
        except FileNotFoundError:
            pass


def test_legacy_worker_never_claims_or_fails_formal_job(app_module):
    with app_module.app.app_context():
        app_module.db.session.rollback()
        formal = app_module.BackgroundJob(
            job_type=FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE,
            status="queued",
            priority=1,
            input_json="{}",
            result_json="{}",
            attempt_count=0,
            max_attempts=1,
            created_at=app_module.current_time_text(),
            updated_at=app_module.current_time_text(),
        )
        legacy = app_module.BackgroundJob(
            job_type="document_ingestion",
            status="queued",
            priority=2,
            input_json="{}",
            result_json="{}",
            attempt_count=0,
            max_attempts=1,
            created_at=app_module.current_time_text(),
            updated_at=app_module.current_time_text(),
        )
        app_module.db.session.add_all([formal, legacy])
        app_module.db.session.commit()

        claimed = app_module.claim_next_background_job(worker_id="legacy-worker-9c4z")
        assert claimed.id == legacy.id
        app_module.db.session.rollback()

        direct = app_module.run_background_job(formal.id, worker_id="legacy-worker-9c4z")
        app_module.db.session.expire_all()
        stored = app_module.db.session.get(app_module.BackgroundJob, formal.id)
        assert direct.id == formal.id
        assert stored.status == "queued"
        assert stored.attempt_count == 0
        assert stored.error_code in {None, ""}

        app_module.BackgroundJob.query.filter(
            app_module.BackgroundJob.id.in_([formal.id, legacy.id])
        ).delete(synchronize_session=False)
        app_module.db.session.commit()
