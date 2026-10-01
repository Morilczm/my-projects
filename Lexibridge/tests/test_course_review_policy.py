import json
import uuid

import pytest

from services import audit_records
from services import concept_alignment_cards as concept_cards
from services import concept_card_review
from services import course_review_policy
from test_concept_card_review import create_source_and_chunk, evidence_from_source, with_expected_version


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def unique_text(prefix="CourseReview"):
    return f"{prefix} {uuid.uuid4().hex[:10]}"


def evidence(language="en", term="Policy Review Term"):
    return [{
        "chunk_uid": f"chunk-{uuid.uuid4().hex}",
        "source_uid": f"source-{uuid.uuid4().hex}",
        "source_title": f"{language} Review Source",
        "course": "Course Review Policy Course",
        "chapter": "Policy Gate",
        "language": language,
        "trust_level": "teacher_verified",
        "quality_status": "native_text_ok",
        "source_locator": "page:1",
        "snippet": f"{term} evidence for course review policy.",
        "score": 0.88,
    }]


def reviewer_context(user):
    return {"reviewer_id": user.id, "reviewer_role": user.role, "reviewer_name": user.username}


def get_user(app_module, role):
    return app_module.User.query.filter_by(role=role).first()


def create_card(app_module, **overrides):
    course = overrides.pop("course", "Course Review Policy Course")
    chapter = overrides.pop("chapter", "Policy Gate")
    english_term = overrides.pop("english_term", unique_text("Policy Term"))
    chinese_term = overrides.pop("chinese_term", f"策略术语{uuid.uuid4().hex[:5]}")
    if "english_evidence" in overrides:
        english_evidence = overrides.pop("english_evidence")
    else:
        en_source, en_chunk = create_source_and_chunk(app_module, term=english_term, course=course, chapter=chapter, language="en")
        english_evidence = evidence_from_source(en_source, en_chunk, term=english_term, language="en")
    if "chinese_evidence" in overrides:
        chinese_evidence = overrides.pop("chinese_evidence")
    else:
        zh_source, zh_chunk = create_source_and_chunk(app_module, term=chinese_term, course=course, chapter=chapter, language="zh")
        chinese_evidence = evidence_from_source(zh_source, zh_chunk, term=chinese_term, language="zh")
    data = {
        "english_term": english_term,
        "chinese_term": chinese_term,
        "course": course,
        "chapter": chapter,
        "status": "needs_review",
        "risk_labels": [],
        "english_evidence": english_evidence,
        "chinese_evidence": chinese_evidence,
        "confidence_score": None,
    }
    data.update(overrides)
    return concept_cards.create_concept_card(
        app_module.db.session,
        app_module.ConceptAlignmentCard,
        data,
        now_fn=app_module.current_time_text,
    )


def create_policy(app_module, course="Course Review Policy Course", **overrides):
    admin = get_user(app_module, "admin")
    data = {
        "course": course,
        "required_evidence_sides": "both",
        "min_required_evidence_count": 2,
        "blocking_risk_labels": course_review_policy.DEFAULT_BLOCKING_RISK_LABELS,
        "override_forbidden_risk_labels": ["parse_failed"],
    }
    data.update(overrides)
    policy, _ = course_review_policy.create_or_update_course_review_policy(
        app_module.db.session,
        app_module.CourseReviewPolicy,
        course,
        data,
        actor=admin,
        now_fn=app_module.current_time_text,
    )
    return policy


def grant_permission(app_module, user, course="Course Review Policy Course", permission_level="approve", **overrides):
    admin = get_user(app_module, "admin")
    data = {
        "reviewer_id": user.id,
        "reviewer_role": user.role,
        "permission_level": permission_level,
    }
    data.update(overrides)
    permission, _ = course_review_policy.grant_course_review_permission(
        app_module.db.session,
        app_module.CourseReviewPermission,
        course,
        user.id,
        data,
        actor=admin,
        now_fn=app_module.current_time_text,
    )
    return permission


def approve_with_policy(app_module, card, user, data=None, **kwargs):
    payload = {
        "reason_code": "teacher_verified",
        "review_comment": "Reviewed for this course.",
    }
    payload.update(data or {})
    return concept_card_review.approve_concept_card(
        app_module.db.session,
        app_module.ConceptAlignmentCard,
        app_module.ConceptCardReviewRecord,
        card.card_uid,
        reviewer_context(user),
        payload,
        audit_model=app_module.AuditRecord,
        audit_context={"request_id": kwargs.pop("request_id", f"policy-{uuid.uuid4().hex[:8]}"), "source": "service"},
        policy_model=app_module.CourseReviewPolicy,
        permission_model=app_module.CourseReviewPermission,
        now_fn=app_module.current_time_text,
        **kwargs,
    )


def test_course_review_policy_models_and_default_are_conservative(app_module):
    with app_module.app.app_context():
        default = course_review_policy.default_course_review_policy("Conservative Course")
        assert default["require_human_review"] is True
        assert default["require_admin_for_override"] is True
        assert default["allow_teacher_override"] is False
        assert default["required_evidence_sides"] == "both"
        assert default["min_required_evidence_count"] == 2

        policy = create_policy(
            app_module,
            course="JSON Policy Course",
            blocking_risk_labels=["input_partial_text"],
            override_allowed_risk_labels=["input_partial_text"],
        )
        teacher = get_user(app_module, "teacher")
        permission = grant_permission(app_module, teacher, course="JSON Policy Course", permission_level="override")
        policy_data = course_review_policy.serialize_course_review_policy(policy)
        permission_data = course_review_policy.serialize_course_review_permission(permission)

        assert policy.policy_uid
        assert policy_data["blocking_risk_labels"] == ["input_partial_text"]
        assert policy_data["override_allowed_risk_labels"] == ["input_partial_text"]
        assert permission.permission_uid
        assert permission_data["can_review"] is True
        assert permission_data["can_approve"] is True
        assert permission_data["can_override_risk"] is True


def test_teacher_course_permissions_are_required_and_scoped(app_module):
    with app_module.app.app_context():
        course = unique_text("Permission Course")
        other_course = unique_text("Unassigned Course")
        teacher = get_user(app_module, "teacher")
        card = create_card(app_module, course=course)
        create_policy(app_module, course=course)

        with pytest.raises(concept_card_review.ConceptCardReviewError, match="course_review_permission_missing"):
            approve_with_policy(app_module, card, teacher)

        grant_permission(app_module, teacher, course=course, permission_level="approve")
        approved, _ = approve_with_policy(app_module, card, teacher)
        assert approved.status == "approved"
        assert approved.confidence_score is None

        other_card = create_card(app_module, course=other_course)
        create_policy(app_module, course=other_course)
        with pytest.raises(concept_card_review.ConceptCardReviewError, match="course_review_permission_missing"):
            approve_with_policy(app_module, other_card, teacher)


def test_disabled_and_revoked_permission_do_not_apply(app_module):
    with app_module.app.app_context():
        teacher = get_user(app_module, "teacher")
        create_policy(app_module, course="Disabled Permission Course")
        disabled_card = create_card(app_module, course="Disabled Permission Course")
        grant_permission(
            app_module,
            teacher,
            course="Disabled Permission Course",
            permission_level="approve",
            status="disabled",
        )
        with pytest.raises(concept_card_review.ConceptCardReviewError, match="course_review_permission_missing"):
            approve_with_policy(app_module, disabled_card, teacher)

        create_policy(app_module, course="Revoked Permission Course")
        revoked_card = create_card(app_module, course="Revoked Permission Course")
        permission = grant_permission(app_module, teacher, course="Revoked Permission Course", permission_level="approve")
        course_review_policy.revoke_course_review_permission(
            app_module.db.session,
            app_module.CourseReviewPermission,
            permission.permission_uid,
            actor=get_user(app_module, "admin"),
            now_fn=app_module.current_time_text,
        )
        with pytest.raises(concept_card_review.ConceptCardReviewError, match="course_review_permission_missing"):
            approve_with_policy(app_module, revoked_card, teacher)


def test_reviewer_can_request_revision_but_cannot_approve(app_module):
    with app_module.app.app_context():
        teacher = get_user(app_module, "teacher")
        create_policy(app_module, course="Review Only Course")
        grant_permission(app_module, teacher, course="Review Only Course", permission_level="review")
        card = create_card(app_module, course="Review Only Course")

        revised, review = concept_card_review.request_card_revision(
            app_module.db.session,
            app_module.ConceptAlignmentCard,
            app_module.ConceptCardReviewRecord,
            card.card_uid,
            reviewer_context(teacher),
            {"reason_code": "evidence_insufficient", "required_changes": ["Add evidence"]},
            policy_model=app_module.CourseReviewPolicy,
            permission_model=app_module.CourseReviewPermission,
            now_fn=app_module.current_time_text,
        )
        assert revised.status == "needs_review"
        assert concept_card_review.serialize_review_record(review)["decision"] == "needs_revision"

        with pytest.raises(concept_card_review.ConceptCardReviewError, match="course_approve_permission_denied"):
            approve_with_policy(app_module, card, teacher)


def test_policy_evidence_and_risk_blocks_approve(app_module):
    with app_module.app.app_context():
        course = unique_text("Evidence Policy Course")
        teacher = get_user(app_module, "teacher")
        create_policy(app_module, course=course)
        grant_permission(app_module, teacher, course=course, permission_level="approve")

        missing_chinese = create_card(app_module, course=course, chinese_evidence=[])
        with pytest.raises(concept_card_review.ConceptCardReviewError, match="course_review_policy_blocked"):
            approve_with_policy(app_module, missing_chinese, teacher)

        unverified = create_card(app_module, course=course, risk_labels=["bilingual_alignment_not_verified"])
        with pytest.raises(concept_card_review.ConceptCardReviewError, match="course_review_policy_blocked"):
            approve_with_policy(app_module, unverified, teacher)

        partial = create_card(app_module, course=course, risk_labels=["input_partial_text"])
        with pytest.raises(concept_card_review.ConceptCardReviewError, match="course_review_policy_blocked"):
            approve_with_policy(app_module, partial, teacher)

        too_few = create_card(app_module, course=course, chinese_evidence=[])
        create_policy(
            app_module,
            course=course,
            allow_approve_with_missing_chinese_evidence=True,
            required_evidence_sides="either",
            min_required_evidence_count=2,
        )
        with pytest.raises(concept_card_review.ConceptCardReviewError, match="course_review_policy_blocked"):
            approve_with_policy(app_module, too_few, teacher)


def test_risk_override_is_controlled_by_policy_and_permission(app_module):
    with app_module.app.app_context():
        course = unique_text("Override Course")
        teacher = get_user(app_module, "teacher")
        admin = get_user(app_module, "admin")
        create_policy(
            app_module,
            course=course,
            blocking_risk_labels=["input_partial_text", "parse_failed"],
            override_allowed_risk_labels=["input_partial_text"],
            override_forbidden_risk_labels=["parse_failed"],
            allow_approve_with_partial_text=False,
            allow_teacher_override=True,
            require_admin_for_override=False,
        )
        grant_permission(app_module, teacher, course=course, permission_level="override")

        forbidden = create_card(app_module, course=course, risk_labels=["parse_failed"])
        with pytest.raises(concept_card_review.ConceptCardReviewError, match="course_review_risk_override_forbidden"):
            approve_with_policy(
                app_module,
                forbidden,
                teacher,
                {"allow_risk_override": True, "override_reason": "Trying forbidden override."},
            )

        create_policy(
            app_module,
            course=course,
            blocking_risk_labels=["input_partial_text"],
            override_allowed_risk_labels=["input_partial_text"],
            allow_approve_with_partial_text=False,
            allow_teacher_override=True,
            require_admin_for_override=True,
            override_forbidden_risk_labels=[],
        )
        admin_required = create_card(app_module, course=course, risk_labels=["input_partial_text"])
        with pytest.raises(concept_card_review.ConceptCardReviewError, match="course_review_admin_required_for_override"):
            approve_with_policy(
                app_module,
                admin_required,
                teacher,
                {"allow_risk_override": True, "override_reason": "Teacher cannot override under policy."},
            )

        admin_card = create_card(app_module, course=course, risk_labels=["input_partial_text"])
        approved, review = approve_with_policy(
            app_module,
            admin_card,
            admin,
            {"allow_risk_override": True, "override_reason": "Admin accepted the documented risk."},
        )
        assert approved.status == "approved"
        assert concept_card_review.serialize_review_record(review)["risk_assessment"]["risk_override_used"] is True

        create_policy(
            app_module,
            course=course,
            blocking_risk_labels=["input_partial_text"],
            override_allowed_risk_labels=["input_partial_text"],
            allow_approve_with_partial_text=False,
            allow_teacher_override=True,
            require_admin_for_override=False,
            override_forbidden_risk_labels=[],
        )
        teacher_card = create_card(app_module, course=course, risk_labels=["input_partial_text"])
        approved_teacher, _ = approve_with_policy(
            app_module,
            teacher_card,
            teacher,
            {"allow_risk_override": True, "override_reason": "Teacher has course override permission."},
        )
        assert approved_teacher.status == "approved"


def test_two_step_review_keeps_teacher_approval_in_needs_review(app_module):
    with app_module.app.app_context():
        teacher = get_user(app_module, "teacher")
        create_policy(app_module, course="Two Step Course", require_two_step_review=True)
        grant_permission(app_module, teacher, course="Two Step Course", permission_level="approve")
        card = create_card(app_module, course="Two Step Course")

        reviewed, record = approve_with_policy(app_module, card, teacher)
        review_data = concept_card_review.serialize_review_record(record)

        assert reviewed.status == "needs_review"
        assert review_data["decision"] == "ready_for_admin_review"


def test_review_policy_and_permission_apis_and_audit(client, app_module, admin_token, teacher_token):
    request_id = f"policy-api-{uuid.uuid4().hex[:8]}"
    with app_module.app.app_context():
        teacher = get_user(app_module, "teacher")
        teacher_id = teacher.id

    forbidden_policy = client.post(
        "/api/review-policies",
        json={"course": "API Policy Course"},
        headers={**bearer(teacher_token), "X-Request-ID": f"{request_id}-forbidden"},
    )
    policy_response = client.post(
        "/api/review-policies",
        json={
            "course": "API Policy Course",
            "required_evidence_sides": "either",
            "min_required_evidence_count": 1,
            "allow_approve_with_missing_chinese_evidence": True,
        },
        headers={**bearer(admin_token), "X-Request-ID": f"{request_id}-policy"},
    )
    permission_response = client.post(
        "/api/review-permissions",
        json={
            "course": "API Policy Course",
            "reviewer_id": teacher_id,
            "reviewer_role": "teacher",
            "permission_level": "admin",
        },
        headers={**bearer(admin_token), "X-Request-ID": f"{request_id}-permission"},
    )

    assert forbidden_policy.status_code == 403
    assert policy_response.status_code == 200, policy_response.get_data(as_text=True)
    policy_uid = policy_response.get_json()["data"]["policy"]["policy_uid"]
    assert policy_response.get_json()["request_id"] == f"{request_id}-policy"
    assert permission_response.status_code == 200, permission_response.get_data(as_text=True)
    permission_uid = permission_response.get_json()["data"]["permission"]["permission_uid"]

    list_policies = client.get("/api/review-policies?course=API%20Policy%20Course", headers=bearer(teacher_token))
    get_policy = client.get(f"/api/review-policies/{policy_uid}", headers=bearer(teacher_token))
    list_permissions = client.get(f"/api/review-permissions?reviewer_id={teacher_id}", headers=bearer(teacher_token))
    revoke = client.post(
        f"/api/review-permissions/{permission_uid}/revoke",
        headers={**bearer(admin_token), "X-Request-ID": f"{request_id}-revoke"},
    )
    missing_policy = client.get(f"/api/review-policies/missing-{uuid.uuid4().hex}", headers=bearer(teacher_token))
    missing_revoke = client.post(
        f"/api/review-permissions/missing-{uuid.uuid4().hex}/revoke",
        headers=bearer(admin_token),
    )

    assert list_policies.status_code == 200
    assert get_policy.status_code == 200
    assert list_permissions.status_code == 200
    assert revoke.status_code == 200
    assert missing_policy.status_code == 404
    assert missing_revoke.status_code == 404
    with app_module.app.app_context():
        created = app_module.AuditRecord.query.filter_by(
            request_id=f"{request_id}-policy",
            event_type="course_review_policy_created",
        ).first()
        granted = app_module.AuditRecord.query.filter_by(
            request_id=f"{request_id}-permission",
            event_type="course_review_permission_granted",
        ).first()
        revoked = app_module.AuditRecord.query.filter_by(
            request_id=f"{request_id}-revoke",
            event_type="course_review_permission_revoked",
        ).first()
        assert created is not None
        assert granted is not None
        assert revoked is not None


def test_review_api_uses_course_permission_and_policy_gate(client, app_module, admin_token, teacher_token):
    request_id = f"review-policy-api-{uuid.uuid4().hex[:8]}"
    with app_module.app.app_context():
        teacher = get_user(app_module, "teacher")
        teacher_id = teacher.id
        card = create_card(app_module, course="API Gated Review Course")
        card_uid = card.card_uid
        other = create_card(app_module, course="API Hidden Review Course")
        other_uid = other.card_uid

    queue_without_permission = client.get(
        "/api/concept-cards/review-queue?course=API%20Gated%20Review%20Course",
        headers={**bearer(teacher_token), "X-Request-ID": f"{request_id}-queue-empty"},
    )
    no_permission = client.post(
        f"/api/concept-cards/{card_uid}/review",
        json=with_expected_version(app_module, card_uid, {"action": "approve", "reason_code": "teacher_verified", "review_comment": "No permission."}),
        headers={**bearer(teacher_token), "X-Request-ID": f"{request_id}-no-permission"},
    )
    client.post(
        "/api/review-policies",
        json={
            "course": "API Gated Review Course",
            "required_evidence_sides": "both",
            "min_required_evidence_count": 2,
        },
        headers=bearer(admin_token),
    )
    client.post(
        "/api/review-permissions",
        json={
            "course": "API Gated Review Course",
            "reviewer_id": teacher_id,
            "reviewer_role": "teacher",
            "permission_level": "approve",
        },
        headers=bearer(admin_token),
    )

    queue_with_permission = client.get(
        "/api/concept-cards/review-queue?course=API%20Gated%20Review%20Course",
        headers={**bearer(teacher_token), "X-Request-ID": f"{request_id}-queue"},
    )
    queue_other_course = client.get(
        "/api/concept-cards/review-queue?course=API%20Hidden%20Review%20Course",
        headers=bearer(teacher_token),
    )
    approved = client.post(
        f"/api/concept-cards/{card_uid}/review",
        json=with_expected_version(app_module, card_uid, {"action": "approve", "reason_code": "teacher_verified", "review_comment": "Approved with course permission."}),
        headers={**bearer(teacher_token), "X-Request-ID": f"{request_id}-approved"},
    )

    assert queue_without_permission.status_code == 200
    assert queue_without_permission.get_json()["data"]["items"] == []
    assert no_permission.status_code == 400
    assert queue_with_permission.status_code == 200
    assert any(item["card_uid"] == card_uid for item in queue_with_permission.get_json()["data"]["items"])
    assert all(item["card_uid"] != other_uid for item in queue_other_course.get_json()["data"]["items"])
    assert approved.status_code == 200, approved.get_data(as_text=True)
    assert approved.get_json()["data"]["card"]["status"] == "approved"

    risky = None
    with app_module.app.app_context():
        risky = create_card(app_module, course="API Gated Review Course", risk_labels=["input_partial_text"]).card_uid
    blocked = client.post(
        f"/api/concept-cards/{risky}/review",
        json=with_expected_version(app_module, risky, {"action": "approve", "reason_code": "teacher_verified", "review_comment": "Risk remains."}),
        headers={**bearer(teacher_token), "X-Request-ID": f"{request_id}-policy-block"},
    )
    override_blocked = client.post(
        f"/api/concept-cards/{risky}/review",
        json=with_expected_version(app_module, risky, {
            "action": "approve",
            "reason_code": "teacher_verified",
            "review_comment": "Teacher tries override.",
            "allow_risk_override": True,
            "override_reason": "Policy does not allow override.",
        }),
        headers={**bearer(teacher_token), "X-Request-ID": f"{request_id}-override-block"},
    )

    assert blocked.status_code == 400
    assert override_blocked.status_code == 400
    with app_module.app.app_context():
        permission_block = app_module.AuditRecord.query.filter_by(
            request_id=f"{request_id}-no-permission",
            event_type="concept_card_review_blocked_by_permission",
        ).first()
        policy_block = app_module.AuditRecord.query.filter_by(
            request_id=f"{request_id}-policy-block",
            event_type="concept_card_review_blocked_by_course_policy",
        ).first()
        override_block = app_module.AuditRecord.query.filter_by(
            request_id=f"{request_id}-override-block",
            event_type="concept_card_risk_override_blocked_by_policy",
        ).first()
        assert permission_block is not None
        assert policy_block is not None
        assert override_block is not None
        dump = json.dumps(audit_records.serialize_audit_record(policy_block), ensure_ascii=False)
        assert "Authorization" not in dump
        assert "Cookie" not in dump
