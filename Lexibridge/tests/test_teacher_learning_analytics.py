import json
import uuid
from urllib.parse import quote

from services import course_review_policy
from services import teacher_learning_analytics


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def unique_text(prefix):
    return f"{prefix} {uuid.uuid4().hex[:10]}"


def teacher_user(app_module):
    return app_module.User.query.filter_by(role="teacher").first()


def student_user(app_module):
    return app_module.User.query.filter_by(role="student").first()


def admin_user(app_module):
    return app_module.User.query.filter_by(role="admin").first()


def make_second_student(app_module):
    user = app_module.User(
        username=f"analytics_student_{uuid.uuid4().hex[:8]}",
        email=f"analytics.student.{uuid.uuid4().hex[:8]}@lexibridge.local",
        password_hash=app_module.generate_password_hash("Student1234", method="pbkdf2:sha256"),
        role="student",
        is_verified=True,
        created_at=app_module.current_time_text(),
    )
    app_module.db.session.add(user)
    app_module.db.session.commit()
    return user


def evidence(term, language="en"):
    return [{
        "chunk_uid": f"chunk-{uuid.uuid4().hex}",
        "source_uid": f"src-{uuid.uuid4().hex}",
        "source_title": f"{term} Source",
        "course": "Analytics Course",
        "chapter": "Analytics Chapter",
        "language": language,
        "source_role": "english_course_material" if language == "en" else "chinese_reference_material",
        "trust_level": "teacher_verified",
        "quality_status": "native_text_ok",
        "source_locator": "page:8",
        "snippet": f"{term} evidence.",
        "score": 0.88,
    }]


def create_card(app_module, course, *, english_term, chapter="Analytics Chapter", status="approved"):
    card = app_module.ConceptAlignmentCard(
        card_uid=f"card-{uuid.uuid4().hex}",
        english_term=english_term,
        chinese_term=f"分析术语{uuid.uuid4().hex[:4]}",
        course=course,
        chapter=chapter,
        concept_scope="Teacher analytics concept.",
        english_evidence=json.dumps(evidence(english_term, "en"), ensure_ascii=False),
        chinese_evidence=json.dumps(evidence(english_term, "zh"), ensure_ascii=False),
        risk_labels="[]",
        status=status,
        reviewed_by=1,
        reviewed_at=app_module.current_time_text() if status == "approved" else "",
        retrieval_version="lexical-v1",
        created_at=app_module.current_time_text(),
        updated_at=app_module.current_time_text(),
    )
    app_module.db.session.add(card)
    app_module.db.session.commit()
    return card


def grant_teacher_and_student_access(app_module, course, students):
    teacher = teacher_user(app_module)
    admin = admin_user(app_module)
    app_module.student_course_access_service.create_or_update_course_student_visibility_policy(
        app_module.db.session,
        app_module.CourseStudentVisibilityPolicy,
        course,
        {"visibility": "enrolled_only", "status": "active", "allow_teacher_preview": True},
        actor=admin,
        now_fn=app_module.current_time_text,
    )
    for student in students:
        app_module.student_course_access_service.add_student_course_membership(
            app_module.db.session,
            app_module.StudentCourseMembership,
            student.id,
            course,
            {"role_in_course": "student", "status": "active"},
            actor=admin,
            now_fn=app_module.current_time_text,
        )
    course_review_policy.grant_course_review_permission(
        app_module.db.session,
        app_module.CourseReviewPermission,
        course,
        teacher.id,
        {
            "reviewer_id": teacher.id,
            "reviewer_role": "teacher",
            "permission_level": "review",
            "status": "active",
        },
        actor=admin,
        now_fn=app_module.current_time_text,
    )
    app_module.db.session.commit()


def create_state(app_module, card, student, *, mastered=False, favorited=False, view_count=0):
    state = app_module.StudentConceptCardState(
        state_uid=f"state-{uuid.uuid4().hex}",
        user_id=student.id,
        card_uid=card.card_uid,
        course=card.course,
        favorited=favorited,
        mastered=mastered,
        mastered_at=app_module.current_time_text() if mastered else "",
        last_viewed_at=app_module.current_time_text() if view_count else "",
        view_count=view_count,
    )
    app_module.db.session.add(state)
    app_module.db.session.commit()
    return state


def create_feedback(app_module, card, student, *, status="submitted", feedback_type="concept_explanation_error"):
    feedback = app_module.Feedback(
        feedback_uid=f"feedback-{uuid.uuid4().hex}",
        term_id=0,
        user_id=student.id,
        user_role="student",
        course=card.course,
        chapter=card.chapter,
        card_uid=card.card_uid,
        english_term=card.english_term,
        chinese_term=card.chinese_term,
        feedback_type=feedback_type,
        feedback_source="student_concept_card",
        priority="P2",
        message="Analytics feedback message.",
        feedback_content="Analytics feedback message.",
        reported_issue="Analytics feedback message.",
        actual_result=card.card_uid,
        evidence_comment=json.dumps({"card_uid": card.card_uid}, ensure_ascii=False),
        status=status,
        linked_card_uid=card.card_uid,
        created_at=app_module.current_time_text(),
        updated_at=app_module.current_time_text(),
    )
    app_module.db.session.add(feedback)
    app_module.db.session.commit()
    return feedback


def build_analytics_fixture(app_module):
    course = unique_text("Teacher Analytics")
    hidden_course = unique_text("Unauthorized Analytics")
    student_one = student_user(app_module)
    student_two = make_second_student(app_module)
    strong = create_card(app_module, course, english_term="Strong Mastery Term")
    hotspot = create_card(app_module, course, english_term="Feedback Hotspot Term")
    quiet = create_card(app_module, course, english_term="Quiet Low Activity Term", chapter="Time Domain")
    create_card(app_module, course, english_term="Draft Should Not Count", status="needs_review")
    hidden = create_card(app_module, hidden_course, english_term="Hidden Analytics Term")
    grant_teacher_and_student_access(app_module, course, [student_one, student_two])

    create_state(app_module, strong, student_one, mastered=True, favorited=False, view_count=2)
    create_state(app_module, strong, student_two, mastered=True, favorited=False, view_count=1)
    create_state(app_module, hotspot, student_one, mastered=False, favorited=True, view_count=1)
    create_state(app_module, hotspot, student_two, mastered=False, favorited=True, view_count=1)

    create_feedback(app_module, hotspot, student_one, status="submitted")
    create_feedback(app_module, hotspot, student_two, status="submitted", feedback_type="evidence_issue")
    create_feedback(app_module, quiet, student_one, status="resolved", feedback_type="duplicate")
    return {
        "course": course,
        "hidden_course": hidden_course,
        "cards": {"strong": strong, "hotspot": hotspot, "quiet": quiet, "hidden": hidden},
        "students": [student_one, student_two],
    }


def test_teacher_learning_analytics_service_counts_and_permissions(app_module):
    with app_module.app.app_context():
        fixture = build_analytics_fixture(app_module)
        teacher = teacher_user(app_module)
        admin = admin_user(app_module)
        summary = teacher_learning_analytics.get_teacher_course_analytics(
            app_module.db.session,
            app_module.ConceptAlignmentCard,
            app_module.StudentConceptCardState,
            app_module.Feedback,
            app_module.StudentCourseMembership,
            app_module.CourseReviewPermission,
            app_module.CourseStudentVisibilityPolicy,
            teacher,
            course=fixture["course"],
        )
        overall = summary["course_summary"]
        assert overall["approved_card_count"] == 3
        assert overall["enrolled_student_count"] == 2
        assert overall["mastered_card_count"] == 2
        assert overall["unmastered_card_count"] == 4
        assert overall["favorited_card_count"] == 2
        assert overall["feedback_count"] == 3
        assert overall["unresolved_feedback_count"] == 2
        assert overall["resolved_feedback_count"] == 1
        assert overall["mastery_rate"] == 0.3333
        assert {row["chapter"] for row in summary["chapter_summaries"]} == {"Analytics Chapter", "Time Domain"}

        hotspots = summary["feedback_hotspots"]
        assert hotspots[0]["english_term"] == "Feedback Hotspot Term"
        assert hotspots[0]["priority_hint"] == "high_feedback_low_mastery"
        low_mastery = summary["low_mastery_cards"]
        assert low_mastery[0]["mastery_rate"] == 0.0

        unauthorized = teacher_learning_analytics.get_teacher_course_analytics(
            app_module.db.session,
            app_module.ConceptAlignmentCard,
            app_module.StudentConceptCardState,
            app_module.Feedback,
            app_module.StudentCourseMembership,
            app_module.CourseReviewPermission,
            app_module.CourseStudentVisibilityPolicy,
            teacher,
            course=fixture["hidden_course"],
        )
        assert unauthorized["course_summary"]["approved_card_count"] == 0

        admin_result = teacher_learning_analytics.get_teacher_course_analytics(
            app_module.db.session,
            app_module.ConceptAlignmentCard,
            app_module.StudentConceptCardState,
            app_module.Feedback,
            app_module.StudentCourseMembership,
            app_module.CourseReviewPermission,
            app_module.CourseStudentVisibilityPolicy,
            admin,
            course=fixture["hidden_course"],
        )
        assert admin_result["course_summary"]["approved_card_count"] == 1


def test_teacher_learning_analytics_api_and_export(client, app_module, teacher_token, admin_token, student_token):
    with app_module.app.app_context():
        fixture = build_analytics_fixture(app_module)
        course = fixture["course"]

    response = client.get(
        f"/api/teacher/learning-analytics?course={quote(course)}",
        headers={**bearer(teacher_token), "X-Request-ID": "teacher-analytics-view"},
    )
    assert response.status_code == 200, response.get_data(as_text=True)
    payload = response.get_json()
    assert payload["request_id"] == "teacher-analytics-view"
    assert payload["data"]["course_summary"]["approved_card_count"] == 3
    assert payload["data"]["feedback_hotspots"][0]["english_term"] == "Feedback Hotspot Term"

    cards = client.get(
        f"/api/teacher/learning-analytics/cards?course={quote(course)}&sort=feedback_count",
        headers={**bearer(teacher_token), "X-Request-ID": "teacher-analytics-cards"},
    )
    assert cards.status_code == 200, cards.get_data(as_text=True)
    card_data = cards.get_json()
    assert card_data["request_id"] == "teacher-analytics-cards"
    assert card_data["data"]["items"][0]["english_term"] == "Feedback Hotspot Term"
    assert "submitted_by" not in json.dumps(card_data["data"])

    student_block = client.get(
        f"/api/teacher/learning-analytics?course={quote(course)}",
        headers={**bearer(student_token), "X-Request-ID": "teacher-analytics-student-block"},
    )
    assert student_block.status_code == 403
    assert student_block.get_json()["request_id"] == "teacher-analytics-student-block"

    export_json = client.get(
        f"/api/teacher/learning-analytics/export?course={quote(course)}&format=json",
        headers={**bearer(teacher_token), "X-Request-ID": "teacher-analytics-export-json"},
    )
    assert export_json.status_code == 200, export_json.get_data(as_text=True)
    rows = export_json.get_json()["data"]["items"]
    assert rows
    dump = json.dumps(rows, ensure_ascii=False)
    assert "AuditRecord" not in dump
    assert "Authorization" not in dump
    assert "Cookie" not in dump
    assert "teacher_note" not in dump
    assert "reviewer" not in dump
    assert "submitted_by" not in dump

    export_csv = client.get(
        f"/api/teacher/learning-analytics/export?course={quote(course)}&format=csv",
        headers={**bearer(admin_token), "X-Request-ID": "teacher-analytics-export-csv"},
    )
    assert export_csv.status_code == 200, export_csv.get_data(as_text=True)
    csv_text = export_csv.get_data(as_text=True)
    assert "english_term" in csv_text
    assert "Authorization" not in csv_text
    assert "Cookie" not in csv_text
    assert export_csv.headers["X-Request-ID"] == "teacher-analytics-export-csv"

    with app_module.app.app_context():
        assert app_module.AuditRecord.query.filter_by(
            event_type="teacher_learning_analytics_viewed",
            request_id="teacher-analytics-view",
        ).first() is not None
        assert app_module.AuditRecord.query.filter_by(
            event_type="teacher_learning_analytics_cards_viewed",
            request_id="teacher-analytics-cards",
        ).first() is not None
        assert app_module.AuditRecord.query.filter_by(
            event_type="teacher_learning_report_exported",
            request_id="teacher-analytics-export-json",
        ).first() is not None
