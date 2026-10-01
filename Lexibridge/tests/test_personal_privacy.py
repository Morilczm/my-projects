from io import BytesIO


def auth_header(token):
    return {"Authorization": f"Bearer {token}"}


def upload_personal_text(client, token, text):
    return client.post(
        "/api/documents/upload?sync=true",
        data={
            "file": (BytesIO(text.encode("utf-8")), "private-note.txt"),
            "scope_type": "personal",
            "language": "en",
        },
        content_type="multipart/form-data",
        headers=auth_header(token),
    )


def create_second_student(app_module):
    with app_module.app.app_context():
        user = app_module.User.query.filter_by(email="student.b@lexibridge.local").first()
        if user is None:
            user = app_module.User(
                username="student_b",
                email="student.b@lexibridge.local",
                password_hash=app_module.generate_password_hash("Student1234", method="pbkdf2:sha256"),
                role="student",
                is_verified=True,
                created_at=app_module.current_time_text(),
            )
            app_module.db.session.add(user)
            app_module.db.session.commit()
        return user.id


def login_second_student(client):
    response = client.post("/api/auth/login", json={
        "email": "student.b@lexibridge.local",
        "password": "Student1234",
    })
    assert response.status_code == 200
    return response.get_json()["token"]


def test_personal_knowledge_search_is_owner_scoped(client, app_module, student_token, teacher_token, admin_token):
    create_second_student(app_module)
    student_b_token = login_second_student(client)

    response = upload_personal_text(
        client,
        student_token,
        "Fourier Transform is a student-only private signal processing note.",
    )
    assert response.status_code == 200
    with app_module.app.app_context():
        student_a = app_module.User.query.filter_by(email="student.test@lexibridge.local").first()
        student_a_id = student_a.id

    own_search = client.get(
        "/api/knowledge/search?q=Fourier%20Transform&scope_type=personal&language=en",
        headers=auth_header(student_token),
    )
    other_search = client.get(
        "/api/knowledge/search?q=Fourier%20Transform&scope_type=personal&language=en",
        headers=auth_header(student_b_token),
    )
    owner_override = client.get(
        f"/api/knowledge/search?q=Fourier%20Transform&scope_type=personal&language=en&owner_user_id={student_a_id}",
        headers=auth_header(student_b_token),
    )
    teacher_override = client.get(
        f"/api/knowledge/search?q=Fourier%20Transform&scope_type=personal&language=en&owner_user_id={student_a_id}",
        headers=auth_header(teacher_token),
    )

    assert own_search.status_code == 200
    assert own_search.get_json()["count"] >= 1
    assert other_search.status_code == 200
    assert other_search.get_json()["count"] == 0
    assert owner_override.status_code == 403
    assert teacher_override.status_code == 403

    admin_search = client.get(
        f"/api/knowledge/search?q=Fourier%20Transform&scope_type=personal&language=en&owner_user_id={student_a_id}",
        headers=auth_header(admin_token),
    )
    assert admin_search.status_code == 200
    with app_module.app.app_context():
        assert app_module.PersonalAccessAudit.query.filter_by(
            actor_user_id=app_module.User.query.filter_by(email="admin.test@lexibridge.local").first().id,
            target_user_id=student_a_id,
        ).count() >= 1


def test_personal_cards_do_not_enter_course_public_lists(client, app_module, student_token):
    upload_response = upload_personal_text(
        client,
        student_token,
        "PrivateCourseLeakGuard is a personal-only terminology candidate.",
    )
    assert upload_response.status_code == 200

    course_cards = client.get(
        "/api/terminology/cards?scope_type=course",
        headers=auth_header(student_token),
    )
    assert course_cards.status_code == 200
    serialized = str(course_cards.get_json())
    assert "PrivateCourseLeakGuard" not in serialized


def test_student_b_cannot_see_student_a_personal_cards(client, app_module, student_token):
    create_second_student(app_module)
    student_b_token = login_second_student(client)
    upload_response = upload_personal_text(
        client,
        student_token,
        "PrivateCardBoundary is a personal-only card candidate.",
    )
    assert upload_response.status_code == 200

    response = client.get(
        "/api/terminology/cards?scope_type=personal",
        headers=auth_header(student_b_token),
    )

    assert response.status_code == 200
    assert "PrivateCardBoundary" not in str(response.get_json())
