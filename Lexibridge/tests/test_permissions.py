import json


def auth_header(token):
    return {"Authorization": f"Bearer {token}"}


def test_student_and_teacher_cannot_access_admin_users(client, student_token, teacher_token):
    student_response = client.get("/api/admin/users", headers=auth_header(student_token))
    teacher_response = client.get("/api/admin/users", headers=auth_header(teacher_token))

    assert student_response.status_code == 403
    assert student_response.get_json()["error_code"] == "PERMISSION_DENIED"
    assert teacher_response.status_code == 403
    assert teacher_response.get_json()["error_code"] == "PERMISSION_DENIED"


def test_admin_can_access_admin_users(client, admin_token):
    response = client.get("/api/admin/users", headers=auth_header(admin_token))

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "success"
    assert any(item["email"] == "admin.test@lexibridge.local" for item in payload["users"])


def test_student_cannot_access_quality_control(client, student_token):
    response = client.get("/api/quality-control", headers=auth_header(student_token))

    assert response.status_code == 403
    assert response.get_json()["error_code"] == "PERMISSION_DENIED"


def test_student_cannot_run_evaluation(client, student_token):
    response = client.post(
        "/api/evaluation/run",
        json={"evaluation_set_id": 1, "split": "test"},
        headers=auth_header(student_token),
    )

    assert response.status_code == 403
    assert response.get_json()["error_code"] == "PERMISSION_DENIED"


def test_teacher_cannot_run_unowned_unbound_evaluation_set(client, app_module, teacher_token, admin_token):
    with app_module.app.app_context():
        admin = app_module.User.query.filter_by(email="admin.test@lexibridge.local").first()
        evaluation_set = app_module.EvaluationSet(
            name="admin_unbound_security_set",
            discipline="signal_processing",
            description="Admin-only unbound set",
            created_by=admin.id,
            created_at=app_module.current_time_text(),
            updated_at=app_module.current_time_text(),
        )
        app_module.db.session.add(evaluation_set)
        app_module.db.session.flush()
        app_module.db.session.add(app_module.EvaluationItem(
            set_id=evaluation_set.id,
            evaluation_set_id=evaluation_set.id,
            item_id="SEC-001",
            split="test",
            discipline="signal_processing",
            english_term="Fourier Transform",
            expected_chinese_term="傅里叶变换",
            english_context="Fourier Transform converts a time-domain signal into a frequency-domain representation.",
            expected_english_evidence="Fourier Transform represents a signal by frequency components.",
            expected_chinese_evidence="傅里叶变换用于将信号表示为频率分量。",
            expected_alignment_status="exact_match",
            version="v1",
            created_at=app_module.current_time_text(),
        ))
        app_module.db.session.commit()
        set_id = evaluation_set.id

    teacher_response = client.post(
        "/api/evaluation/run",
        json={"evaluation_set_id": set_id, "split": "test"},
        headers=auth_header(teacher_token),
    )
    admin_response = client.post(
        "/api/evaluation/run",
        json={"evaluation_set_id": set_id, "split": "test"},
        headers=auth_header(admin_token),
    )

    assert teacher_response.status_code == 403
    assert admin_response.status_code == 200
    assert admin_response.get_json()["status"] == "success"


def test_student_cannot_trigger_course_scope_alignment(client, student_token, test_course):
    response = client.post(
        "/api/alignment/run",
        json={
            "scope_type": "course",
            "course_id": test_course.id,
            "english_term": "Fourier Transform",
        },
        headers=auth_header(student_token),
    )

    assert response.status_code == 403


def test_teacher_cannot_access_other_teacher_course_search(client, app_module, teacher_token):
    with app_module.app.app_context():
        other_teacher = app_module.User(
            username="other_teacher",
            email="other.teacher@lexibridge.local",
            password_hash=app_module.generate_password_hash("Teacher1234", method="pbkdf2:sha256"),
            role="teacher",
            is_verified=True,
            created_at=app_module.current_time_text(),
        )
        app_module.db.session.add(other_teacher)
        app_module.db.session.flush()
        other_course = app_module.Course(
            name="Other Teacher Course",
            course_code="OTHER-101",
            teacher_id=other_teacher.id,
            created_at=app_module.current_time_text(),
        )
        app_module.db.session.add(other_course)
        app_module.db.session.commit()
        other_course_id = other_course.id

    response = client.get(
        f"/api/knowledge/search?q=Fourier&scope_type=course&course_id={other_course_id}&language=en",
        headers=auth_header(teacher_token),
    )

    assert response.status_code == 403
