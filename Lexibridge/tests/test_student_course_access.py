import uuid

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError


def unique_course(prefix="Student Access Course"):
    return f"{prefix} {uuid.uuid4().hex[:10]}"


def make_user(app_module, *, role="student", username_prefix="access_user"):
    user = app_module.User(
        username=f"{username_prefix}_{uuid.uuid4().hex[:8]}",
        email=f"{username_prefix}_{uuid.uuid4().hex[:8]}@lexibridge.local",
        password_hash=app_module.generate_password_hash("Password1234", method="pbkdf2:sha256"),
        role=role,
        is_verified=True,
        created_at=app_module.current_time_text(),
    )
    app_module.db.session.add(user)
    app_module.db.session.commit()
    return user


def create_policy(app_module, course, *, visibility="enrolled_only", allow_teacher_preview=True, status="active"):
    admin = app_module.User.query.filter_by(role="admin").first()
    policy, _ = app_module.student_course_access_service.create_or_update_course_student_visibility_policy(
        app_module.db.session,
        app_module.CourseStudentVisibilityPolicy,
        course,
        {
            "visibility": visibility,
            "allow_teacher_preview": allow_teacher_preview,
            "status": status,
        },
        actor=admin,
        now_fn=app_module.current_time_text,
    )
    app_module.db.session.commit()
    return policy


def create_membership(app_module, user, course, *, role_in_course="student", status="active"):
    admin = app_module.User.query.filter_by(role="admin").first()
    membership = app_module.student_course_access_service.add_student_course_membership(
        app_module.db.session,
        app_module.StudentCourseMembership,
        user.id,
        course,
        {
            "role_in_course": role_in_course,
            "status": status,
        },
        actor=admin,
        now_fn=app_module.current_time_text,
    )
    app_module.db.session.commit()
    return membership


def create_card(app_module, course, *, status="approved"):
    card = app_module.ConceptAlignmentCard(
        card_uid=f"card-{uuid.uuid4().hex}",
        english_term=f"Access Term {uuid.uuid4().hex[:6]}",
        chinese_term=f"访问术语{uuid.uuid4().hex[:4]}",
        course=course,
        chapter="Visibility",
        concept_scope="Visibility test card.",
        english_evidence='[{"snippet":"Visibility evidence.","source_title":"Visibility Source"}]',
        chinese_evidence="[]",
        risk_labels="[]",
        status=status,
        reviewed_at=app_module.current_time_text() if status == "approved" else "",
    )
    app_module.db.session.add(card)
    app_module.db.session.commit()
    return card


def test_student_course_access_tables_exist(app_module):
    with app_module.app.app_context():
        inspector = inspect(app_module.db.engine)
        assert "student_course_membership" in inspector.get_table_names()
        assert "course_student_visibility_policy" in inspector.get_table_names()


def test_student_course_membership_unique_user_course(app_module):
    with app_module.app.app_context():
        course = unique_course("Unique Membership")
        student = make_user(app_module, role="student", username_prefix="unique_student")
        first = app_module.StudentCourseMembership(
            membership_uid=f"membership-{uuid.uuid4().hex}",
            user_id=student.id,
            course=course,
            role_in_course="student",
            status="active",
        )
        duplicate = app_module.StudentCourseMembership(
            membership_uid=f"membership-{uuid.uuid4().hex}",
            user_id=student.id,
            course=course,
            role_in_course="student",
            status="active",
        )
        app_module.db.session.add(first)
        app_module.db.session.commit()
        app_module.db.session.add(duplicate)
        with pytest.raises(IntegrityError):
            app_module.db.session.commit()
        app_module.db.session.rollback()


def test_student_course_access_service_visibility_rules(app_module):
    with app_module.app.app_context():
        student = make_user(app_module, role="student", username_prefix="visibility_student")
        teacher = make_user(app_module, role="teacher", username_prefix="visibility_teacher")

        enrolled_course = unique_course("Enrolled Course")
        no_membership_course = unique_course("No Membership Course")
        public_course = unique_course("Public Course")
        disabled_course = unique_course("Disabled Course")
        private_course = unique_course("Private Course")
        revoked_course = unique_course("Revoked Course")
        teacher_course = unique_course("Teacher Preview Course")

        create_policy(app_module, enrolled_course, visibility="enrolled_only")
        create_policy(app_module, no_membership_course, visibility="enrolled_only")
        create_policy(app_module, public_course, visibility="public")
        create_policy(app_module, disabled_course, visibility="disabled")
        create_policy(app_module, private_course, visibility="private")
        create_policy(app_module, revoked_course, visibility="enrolled_only")
        create_policy(app_module, teacher_course, visibility="private", allow_teacher_preview=False)

        create_membership(app_module, student, enrolled_course)
        create_membership(app_module, student, revoked_course, status="revoked")

        service = app_module.student_course_access_service
        assert service.can_student_view_course(
            app_module.db.session,
            app_module.StudentCourseMembership,
            app_module.CourseStudentVisibilityPolicy,
            student,
            enrolled_course,
        ).allowed
        assert not service.can_student_view_course(
            app_module.db.session,
            app_module.StudentCourseMembership,
            app_module.CourseStudentVisibilityPolicy,
            student,
            no_membership_course,
        ).allowed
        assert service.can_student_view_course(
            app_module.db.session,
            app_module.StudentCourseMembership,
            app_module.CourseStudentVisibilityPolicy,
            student,
            public_course,
        ).allowed
        assert not service.can_student_view_course(
            app_module.db.session,
            app_module.StudentCourseMembership,
            app_module.CourseStudentVisibilityPolicy,
            student,
            disabled_course,
        ).allowed
        assert not service.can_student_view_course(
            app_module.db.session,
            app_module.StudentCourseMembership,
            app_module.CourseStudentVisibilityPolicy,
            student,
            private_course,
        ).allowed
        assert not service.can_student_view_course(
            app_module.db.session,
            app_module.StudentCourseMembership,
            app_module.CourseStudentVisibilityPolicy,
            student,
            revoked_course,
        ).allowed
        assert not service.can_student_view_course(
            app_module.db.session,
            app_module.StudentCourseMembership,
            app_module.CourseStudentVisibilityPolicy,
            teacher,
            teacher_course,
        ).allowed


def test_student_card_visibility_requires_approved_status(app_module):
    with app_module.app.app_context():
        student = make_user(app_module, role="student", username_prefix="card_visibility_student")
        course = unique_course("Approved Required")
        create_policy(app_module, course, visibility="enrolled_only")
        create_membership(app_module, student, course)
        approved = create_card(app_module, course, status="approved")
        needs_review = create_card(app_module, course, status="needs_review")

        service = app_module.student_course_access_service
        assert service.can_student_view_concept_card(
            app_module.db.session,
            app_module.StudentCourseMembership,
            app_module.CourseStudentVisibilityPolicy,
            student,
            approved,
        ).allowed
        blocked = service.can_student_view_concept_card(
            app_module.db.session,
            app_module.StudentCourseMembership,
            app_module.CourseStudentVisibilityPolicy,
            student,
            needs_review,
        )
        assert not blocked.allowed
        assert blocked.reason == "card_not_approved"


def test_student_course_access_admin_membership_and_policy_apis(app_module, client, admin_token, student_token):
    with app_module.app.app_context():
        student = make_user(app_module, role="student", username_prefix="api_membership_student")
        course = unique_course("API Membership")
        student_id = student.id

    policy_response = client.post(
        "/api/course-student-visibility-policies",
        json={"course": course, "visibility": "enrolled_only", "status": "active"},
        headers={"Authorization": f"Bearer {admin_token}", "X-Request-ID": "policy-create-test"},
    )
    assert policy_response.status_code == 200
    assert policy_response.get_json()["request_id"] == "policy-create-test"

    membership_response = client.post(
        "/api/student/course-memberships",
        json={"user_id": student_id, "course": course, "role_in_course": "student"},
        headers={"Authorization": f"Bearer {admin_token}", "X-Request-ID": "membership-create-test"},
    )
    assert membership_response.status_code == 200
    membership_payload = membership_response.get_json()
    membership_uid = membership_payload["data"]["membership"]["membership_uid"]

    student_create = client.post(
        "/api/student/course-memberships",
        json={"user_id": student_id, "course": course},
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert student_create.status_code == 403

    list_response = client.get(
        f"/api/student/course-memberships?user_id={student_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert list_response.status_code == 200
    assert list_response.get_json()["data"]["items"][0]["course"] == course

    revoke_response = client.post(
        f"/api/student/course-memberships/{membership_uid}/revoke",
        headers={"Authorization": f"Bearer {admin_token}", "X-Request-ID": "membership-revoke-test"},
    )
    assert revoke_response.status_code == 200
    assert revoke_response.get_json()["data"]["membership"]["status"] == "revoked"

    with app_module.app.app_context():
        created_audit = app_module.AuditRecord.query.filter_by(
            event_type="student_course_membership_created",
            request_id="membership-create-test",
        ).first()
        policy_audit = app_module.AuditRecord.query.filter_by(
            event_type="course_student_visibility_policy_created",
            request_id="policy-create-test",
        ).first()
        revoked_audit = app_module.AuditRecord.query.filter_by(
            event_type="student_course_membership_revoked",
            request_id="membership-revoke-test",
        ).first()
        assert created_audit is not None
        assert policy_audit is not None
        assert revoked_audit is not None
