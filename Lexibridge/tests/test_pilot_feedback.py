def auth_header(token):
    return {"Authorization": f"Bearer {token}"}


def ensure_student_member(app_module, course, student):
    existing = app_module.CourseMember.query.filter_by(course_id=course.id, user_id=student.id).first()
    if existing:
        return existing
    member = app_module.CourseMember(
        course_id=course.id,
        user_id=student.id,
        role="student",
        role_in_course="student",
        created_at=app_module.current_time_text(),
        joined_at=app_module.current_time_text(),
    )
    app_module.db.session.add(member)
    app_module.db.session.flush()
    return member


def create_visible_card(app_module, status="approved", course=None):
    course = course or app_module.Course.query.filter_by(name="OCR Test Course").first()
    student = app_module.User.query.filter_by(email="student.test@lexibridge.local").first()
    ensure_student_member(app_module, course, student)
    card = app_module.TerminologyCard(
        scope_type="course",
        course_id=course.id,
        english_term="Fourier Transform",
        normalized_english_term="fourier transform",
        final_chinese_term="傅里叶变换",
        normalized_chinese_term="傅里叶变换",
        courseware_sentence="Fourier Transform converts a time-domain signal into a frequency-domain representation.",
        english_evidence_snapshot='[{"content_excerpt":"Fourier Transform converts a time-domain signal."}]',
        chinese_evidence_snapshot='[{"content_excerpt":"傅里叶变换用于将时域信号表示为频率分量。"}]',
        english_evidence_score=0.91,
        chinese_evidence_score=0.88,
        alignment_status="exact_match",
        status=status,
        confidence_score=88,
        created_at=app_module.current_time_text(),
        updated_at=app_module.current_time_text(),
    )
    app_module.db.session.add(card)
    app_module.db.session.commit()
    return card


def test_student_can_submit_feedback_for_visible_card(client, app_module, student_token):
    with app_module.app.app_context():
        card = create_visible_card(app_module)
        card_id = card.id

    response = client.post(
        f"/api/terminology/cards/{card_id}/feedback",
        json={
            "feedback_type": "translation_error",
            "severity": "medium",
            "reported_issue": "The Chinese term should include transform wording.",
            "expected_result": "傅里叶变换",
        },
        headers=auth_header(student_token),
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["data"]["feedback_status"] == "submitted"
    assert payload["feedback"]["feedback_type"] == "translation_error"
    assert payload["feedback"]["student_display"].startswith("student-")


def test_student_cannot_feedback_invisible_card(client, app_module, student_token):
    with app_module.app.app_context():
        teacher = app_module.User.query.filter_by(email="teacher.test@lexibridge.local").first()
        other_course = app_module.Course(
            name="Invisible Pilot Course",
            course_code="PILOT-HIDDEN",
            teacher_id=teacher.id,
            created_at=app_module.current_time_text(),
        )
        app_module.db.session.add(other_course)
        app_module.db.session.flush()
        card = app_module.TerminologyCard(
            scope_type="course",
            course_id=other_course.id,
            english_term="Hidden Term",
            final_chinese_term="隐藏术语",
            status="approved",
            created_at=app_module.current_time_text(),
        )
        app_module.db.session.add(card)
        app_module.db.session.commit()
        card_id = card.id

    response = client.post(
        f"/api/terminology/cards/{card_id}/feedback",
        json={"feedback_type": "evidence_error", "reported_issue": "Wrong evidence"},
        headers=auth_header(student_token),
    )

    assert response.status_code == 403


def test_high_severity_feedback_moves_card_to_qc(client, app_module, student_token):
    with app_module.app.app_context():
        card = create_visible_card(app_module, status="approved")
        card_id = card.id

    for issue in ["Evidence is wrong.", "The translation is misleading."]:
        response = client.post(
            f"/api/terminology/cards/{card_id}/feedback",
            json={"feedback_type": "evidence_error", "severity": "high", "reported_issue": issue},
            headers=auth_header(student_token),
        )
        assert response.status_code == 200

    with app_module.app.app_context():
        card = app_module.db.session.get(app_module.TerminologyCard, card_id)
        assert card.status == "pending_quality_control"
        assert card.feedback_count >= 2


def test_critical_feedback_creates_system_log(client, app_module, student_token):
    with app_module.app.app_context():
        card = create_visible_card(app_module)
        card_id = card.id

    response = client.post(
        f"/api/terminology/cards/{card_id}/feedback",
        json={"feedback_type": "permission_issue", "severity": "critical", "reported_issue": "I can see data I should not see."},
        headers=auth_header(student_token),
    )

    assert response.status_code == 200
    with app_module.app.app_context():
        assert app_module.SystemLog.query.filter_by(module="pilot_feedback").count() >= 1
