from io import BytesIO


def auth_header(token):
    return {"Authorization": f"Bearer {token}"}


def test_create_background_job_records_event_and_serializes(app_module, teacher_token):
    with app_module.app.app_context():
        teacher = app_module.User.query.filter_by(email="teacher.test@lexibridge.local").first()
        job = app_module.create_background_job(
            "alignment_run",
            teacher,
            input_data={"english_term": "Fourier Transform"},
            max_attempts=1,
        )
        app_module.db.session.commit()

        serialized = app_module.serialize_background_job(job)
        assert serialized["job_type"] == "alignment_run"
        assert serialized["status"] == "queued"
        assert serialized["progress_percent"] == 0

        events = app_module.BackgroundJobEvent.query.filter_by(job_id=job.id).all()
        assert len(events) == 1
        assert events[0].event_type == "created"


def test_default_upload_returns_queued_document_ingestion_job(client, teacher_token, test_course):
    response = client.post(
        "/api/documents/upload",
        headers=auth_header(teacher_token),
        data={
            "scope_type": "course",
            "course_id": str(test_course.id),
            "language": "en",
            "file": (BytesIO(b"Fourier Transform converts a time-domain signal."), "lecture.txt"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert payload["document_id"]
    assert payload["job_id"]
    assert payload["job_type"] == "document_ingestion"
    assert payload["job_status"] == "queued"
    assert payload["document"]["parsing_status"] == "queued"
