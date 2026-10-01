from io import BytesIO


def auth_header(token):
    return {"Authorization": f"Bearer {token}"}


def queued_upload_job(client, token, course_id):
    response = client.post(
        "/api/documents/upload",
        headers=auth_header(token),
        data={
            "scope_type": "course",
            "course_id": str(course_id),
            "language": "en",
            "file": (BytesIO(b"Convolution combines two signals."), "job-api.txt"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    return response.get_json()["data"]["job_id"]


def test_job_list_detail_events_and_cancel(client, teacher_token, student_token, test_course):
    job_id = queued_upload_job(client, teacher_token, test_course.id)

    list_response = client.get("/api/jobs", headers=auth_header(teacher_token))
    assert list_response.status_code == 200
    assert any(item["id"] == job_id for item in list_response.get_json()["data"]["items"])

    detail_response = client.get(f"/api/jobs/{job_id}", headers=auth_header(teacher_token))
    assert detail_response.status_code == 200
    assert detail_response.get_json()["data"]["job"]["status"] == "queued"

    student_response = client.get(f"/api/jobs/{job_id}", headers=auth_header(student_token))
    assert student_response.status_code == 403

    events_response = client.get(f"/api/jobs/{job_id}/events", headers=auth_header(teacher_token))
    assert events_response.status_code == 200
    assert events_response.get_json()["data"]["items"][0]["event_type"] == "created"

    cancel_response = client.post(f"/api/jobs/{job_id}/cancel", headers=auth_header(teacher_token))
    assert cancel_response.status_code == 200
    assert cancel_response.get_json()["data"]["job"]["status"] == "canceled"


def test_failed_job_can_be_retried_by_owner(client, app_module, teacher_token):
    with app_module.app.app_context():
        teacher = app_module.User.query.filter_by(email="teacher.test@lexibridge.local").first()
        job = app_module.create_background_job(
            "document_ingestion",
            teacher,
            input_data={"save_path": "/missing/file.txt"},
            max_attempts=1,
        )
        job.status = "failed"
        job.error_code = "PARSING_FAILED"
        job.error_message = "missing file"
        app_module.db.session.commit()
        job_id = job.id

    retry_response = client.post(f"/api/jobs/{job_id}/retry", headers=auth_header(teacher_token))
    assert retry_response.status_code == 200
    payload = retry_response.get_json()["data"]["job"]
    assert payload["status"] == "queued"
    assert payload["error_code"] == ""
