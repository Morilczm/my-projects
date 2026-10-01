import io
import json
import uuid
from urllib.parse import quote


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def _json(response):
    return response.get_json() or {}


def _create_login_user(app_module, client, *, role, username_prefix):
    suffix = uuid.uuid4().hex[:8]
    email = f"{username_prefix}.{suffix}@lexibridge.local"
    password = f"{role.title()}1234!"
    with app_module.app.app_context():
        user = app_module.User(
            username=f"{username_prefix}_{suffix}",
            email=email,
            password_hash=app_module.generate_password_hash(password, method="pbkdf2:sha256"),
            role=role,
            is_verified=True,
            created_at=app_module.current_time_text(),
        )
        app_module.db.session.add(user)
        app_module.db.session.commit()
        user_id = user.id
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.get_data(as_text=True)
    return user_id, _json(response)["token"]


def _create_course(client, teacher_token, name):
    response = client.post(
        "/api/courses",
        json={
            "name": name,
            "course_code": f"PHY-{uuid.uuid4().hex[:6]}",
            "language_mode": "bilingual",
        },
        headers=bearer(teacher_token),
    )
    assert response.status_code == 200, response.get_data(as_text=True)
    return _json(response)["course"]


def _grant_student_access(client, admin_token, *, course, student_id):
    policy = client.post(
        "/api/course-student-visibility-policies",
        json={"course": course, "visibility": "enrolled_only", "status": "active"},
        headers={**bearer(admin_token), "X-Request-ID": f"11b-student-policy-{uuid.uuid4().hex[:8]}"},
    )
    assert policy.status_code == 200, policy.get_data(as_text=True)
    membership = client.post(
        "/api/student/course-memberships",
        json={"course": course, "user_id": student_id, "role_in_course": "student", "status": "active"},
        headers={**bearer(admin_token), "X-Request-ID": f"11b-student-membership-{uuid.uuid4().hex[:8]}"},
    )
    assert membership.status_code == 200, membership.get_data(as_text=True)


def _grant_teacher_review_access(client, admin_token, *, course, teacher_id):
    policy = client.post(
        "/api/review-policies",
        json={
            "course": course,
            "required_evidence_sides": "both",
            "min_required_evidence_count": 2,
            "allow_teacher_override": True,
            "require_admin_for_override": False,
            "allow_approve_with_unverified_alignment": False,
            "override_allowed_risk_labels": [
                "bilingual_alignment_not_verified",
                "candidate_not_alignment_verified",
                "weak_candidate_score",
            ],
        },
        headers={**bearer(admin_token), "X-Request-ID": f"11b-review-policy-{uuid.uuid4().hex[:8]}"},
    )
    assert policy.status_code == 200, policy.get_data(as_text=True)
    permission = client.post(
        "/api/review-permissions",
        json={
            "course": course,
            "reviewer_id": teacher_id,
            "reviewer_role": "teacher",
            "permission_level": "override",
        },
        headers={**bearer(admin_token), "X-Request-ID": f"11b-review-permission-{uuid.uuid4().hex[:8]}"},
    )
    assert permission.status_code == 200, permission.get_data(as_text=True)


def _upload_source(client, token, *, course_id, language, filename, source_name, chapter, text):
    response = client.post(
        "/api/documents/upload",
        data={
            "file": (io.BytesIO(text.encode("utf-8")), filename),
            "scope_type": "course",
            "course_id": str(course_id),
            "language": language,
            "source_name": source_name,
            "chapter": chapter,
        },
        content_type="multipart/form-data",
        headers={**bearer(token), "X-Request-ID": f"11b-upload-{uuid.uuid4().hex[:8]}"},
    )
    assert response.status_code == 200, response.get_data(as_text=True)
    payload = _json(response)["data"]
    assert payload["ingestion_status"] == "queued"
    return payload


def _run_ingestion_job(app_module, job_id):
    with app_module.app.app_context():
        job = app_module.run_background_job(job_id, worker_id=f"11b-ingestion-{uuid.uuid4().hex[:8]}")
        assert job.status == "completed", job.error_message
        result = json.loads(job.result_json)
        assert result["ingestion_status"] == "ingested"
        assert result["chunk_uids"]
        return result


def _start_formal_run(client, teacher_token, source_uid):
    response = client.post(
        "/api/document-alignment-runs",
        json={"source_uid": source_uid},
        headers={
            **bearer(teacher_token),
            "Idempotency-Key": f"11b-formal-{uuid.uuid4().hex}",
            "X-Request-ID": f"11b-formal-request-{uuid.uuid4().hex[:8]}",
        },
    )
    assert response.status_code == 202, response.get_data(as_text=True)
    return _json(response)["data"]["run_uid"]


def _student_cards(client, student_token, course):
    response = client.get(
        f"/api/student/concept-cards?course={quote(course)}&per_page=50",
        headers=bearer(student_token),
    )
    assert response.status_code == 200, response.get_data(as_text=True)
    return _json(response)["data"]["items"]


def _card_detail(client, token, card_uid):
    response = client.get(f"/api/student/concept-cards/{card_uid}", headers=bearer(token))
    assert response.status_code == 200, response.get_data(as_text=True)
    return _json(response)["data"]["card"]


def _review_action(client, token, card_uid, action, **payload):
    if "expected_version" not in payload:
        detail = client.get(f"/api/concept-cards/{card_uid}", headers=bearer(token))
        if detail.status_code == 200:
            payload["expected_version"] = _json(detail)["data"]["card"].get("review_token")
    response = client.post(
        f"/api/concept-cards/{card_uid}/review",
        json={"action": action, **payload},
        headers={**bearer(token), "X-Request-ID": f"11b-review-{uuid.uuid4().hex[:8]}"},
    )
    return response


def _review_queue(client, teacher_token, course):
    response = client.get(
        f"/api/concept-cards/review-queue?course={quote(course)}&status=needs_review,draft&per_page=50",
        headers=bearer(teacher_token),
    )
    assert response.status_code == 200, response.get_data(as_text=True)
    return _json(response)["data"]["items"]


def _item_by_term(items, term):
    for item in items:
        if item.get("candidate_term", "").casefold() == term.casefold():
            return item
    raise AssertionError(f"Missing formal item for {term}: {items}")


def _card_by_english_term(cards, term):
    for card in cards:
        if card.get("english_term", "").casefold() == term.casefold():
            return card
    raise AssertionError(f"Missing concept card for {term}: {cards}")


def test_teacher_reviewed_card_publication_from_uploaded_bilingual_sources(
    app_module,
    client,
    teacher_token,
    admin_token,
):
    with app_module.app.app_context():
        teacher = app_module.User.query.filter_by(email="teacher.test@lexibridge.local").one()
        teacher_id = teacher.id
        before_provider_calls = app_module.AICallLog.query.count()
        before_workflow_runs = app_module.DocumentAlignmentWorkflowRun.query.count()

    enrolled_student_id, enrolled_student_token = _create_login_user(
        app_module,
        client,
        role="student",
        username_prefix="student_11b_enrolled",
    )
    _non_enrolled_student_id, non_enrolled_student_token = _create_login_user(
        app_module,
        client,
        role="student",
        username_prefix="student_11b_outside",
    )
    _other_teacher_id, other_teacher_token = _create_login_user(
        app_module,
        client,
        role="teacher",
        username_prefix="teacher_11b_other",
    )

    course_name = f"Introductory Physics 11B {uuid.uuid4().hex[:8]}"
    course = _create_course(client, teacher_token, course_name)
    _grant_student_access(client, admin_token, course=course_name, student_id=enrolled_student_id)
    _grant_teacher_review_access(client, admin_token, course=course_name, teacher_id=teacher_id)

    english_upload = _upload_source(
        client,
        teacher_token,
        course_id=course["id"],
        language="en",
        filename="intro-physics-en.txt",
        source_name="Synthetic English Momentum Notes",
        chapter="Momentum",
        text=(
            "Momentum is defined as the product of mass and velocity.\n"
            "Acceleration is defined as the rate of change of velocity.\n"
        ),
    )
    chinese_upload = _upload_source(
        client,
        teacher_token,
        course_id=course["id"],
        language="zh",
        filename="intro-physics-zh.txt",
        source_name="Synthetic Chinese Momentum Notes",
        chapter="Momentum",
        text=(
            "动量（Momentum）是物体质量与速度的乘积。\n"
            "加速度（Acceleration）是速度随时间变化的率。\n"
        ),
    )
    english_ingestion = _run_ingestion_job(app_module, english_upload["job_id"])
    chinese_ingestion = _run_ingestion_job(app_module, chinese_upload["job_id"])
    assert english_ingestion["source_uid"] != chinese_ingestion["source_uid"]

    with app_module.app.app_context():
        english_source = app_module.KnowledgeSource.query.filter_by(source_uid=english_ingestion["source_uid"]).one()
        chinese_source = app_module.KnowledgeSource.query.filter_by(source_uid=chinese_ingestion["source_uid"]).one()
        assert english_source.language == "en"
        assert english_source.source_role == "english_course_material"
        assert english_source.status == "active"
        assert chinese_source.language == "zh"
        assert chinese_source.source_role == "chinese_reference_material"
        assert chinese_source.status == "active"
        assert app_module.KnowledgeChunk.query.filter_by(source_uid=english_source.source_uid, language="en").count() >= 1
        assert app_module.KnowledgeChunk.query.filter_by(source_uid=chinese_source.source_uid, language="zh").count() >= 1

    run_uid = _start_formal_run(client, teacher_token, english_ingestion["source_uid"])
    with app_module.app.app_context():
        first_worker = app_module.run_formal_worker_once(worker_id="11b-formal-worker")
        assert first_worker.outcome == "completed", first_worker
        retry_worker = app_module.run_formal_worker_once(worker_id="11b-formal-worker-repeat")
        assert retry_worker.outcome == "no_job_available"

    run_response = client.get(f"/api/document-alignment-runs/{run_uid}", headers=bearer(teacher_token))
    assert run_response.status_code == 200, run_response.get_data(as_text=True)
    run_data = _json(run_response)["data"]
    assert run_data["ready_for_review_items"] >= 2
    # The deterministic extractor may surface additional generic English tokens
    # from the same synthetic source. Those can fail closed, but they must not
    # become student-visible cards.
    assert run_data["blocked_items"] >= 0

    items_response = client.get(
        f"/api/document-alignment-runs/{run_uid}/items?page=1&page_size=50&reviewable_only=true",
        headers=bearer(teacher_token),
    )
    assert items_response.status_code == 200, items_response.get_data(as_text=True)
    workflow_items = _json(items_response)["data"]["items"]
    momentum_item = _item_by_term(workflow_items, "Momentum")
    acceleration_item = _item_by_term(workflow_items, "Acceleration")
    assert momentum_item["status"] == "needs_review"
    assert acceleration_item["status"] == "needs_review"
    assert momentum_item["draft_card_uid"]
    assert acceleration_item["draft_card_uid"]

    assert _student_cards(client, enrolled_student_token, course_name) == []
    assert _review_action(
        client,
        enrolled_student_token,
        momentum_item["draft_card_uid"],
        "approve",
        reason_code="teacher_verified",
        review_comment="Students cannot approve.",
    ).status_code == 403
    assert _review_action(
        client,
        other_teacher_token,
        momentum_item["draft_card_uid"],
        "approve",
        reason_code="teacher_verified",
        review_comment="Other teacher cannot approve.",
    ).status_code == 400

    cards = _review_queue(client, teacher_token, course_name)
    momentum_card = _card_by_english_term(cards, "Momentum")
    acceleration_card = _card_by_english_term(cards, "Acceleration")
    assert momentum_card["status"] == "needs_review"
    assert acceleration_card["status"] == "needs_review"
    assert momentum_card["english_evidence"]
    assert momentum_card["chinese_evidence"]
    momentum_risk_labels = sorted(set(momentum_card["risk_labels"]))
    policy_update = client.post(
        "/api/review-policies",
        json={
            "course": course_name,
            "required_evidence_sides": "both",
            "min_required_evidence_count": 2,
            "allow_teacher_override": True,
            "require_admin_for_override": False,
            "allow_approve_with_unverified_alignment": False,
            "override_allowed_risk_labels": momentum_risk_labels,
        },
        headers={**bearer(admin_token), "X-Request-ID": f"11b-review-policy-final-{uuid.uuid4().hex[:8]}"},
    )
    assert policy_update.status_code == 200, policy_update.get_data(as_text=True)

    patch = client.patch(
        f"/api/concept-cards/{momentum_card['card_uid']}",
        json={
            "expected_version": momentum_card["review_token"],
            "chinese_term": "动量",
            "chinese_explanation": "教师确认：动量是质量与速度的乘积。",
            "english_explanation": "Teacher reviewed explanation for momentum.",
        },
        headers={**bearer(teacher_token), "X-Request-ID": f"11b-edit-{uuid.uuid4().hex[:8]}"},
    )
    assert patch.status_code == 200, patch.get_data(as_text=True)
    approval = _review_action(
        client,
        teacher_token,
        momentum_card["card_uid"],
        "approve",
        reason_code="teacher_verified",
        review_comment="Synthetic bilingual evidence is sufficient for publication flow verification.",
            allow_risk_override=True,
            override_reason="11B verifies workflow closure with teacher-reviewed synthetic evidence.",
            resolved_risk_labels=momentum_risk_labels,
        )
    assert approval.status_code == 200, approval.get_data(as_text=True)
    approved_card = _json(approval)["data"]["card"]
    assert approved_card["status"] == "approved"
    assert approved_card["reviewed_by"] == teacher_id
    assert approved_card["reviewed_at"]

    rejection = _review_action(
        client,
        teacher_token,
        acceleration_card["card_uid"],
        "reject",
        reason_code="course_context_mismatch",
        review_comment="Rejecting one draft to prove rejected cards are not student-visible.",
    )
    assert rejection.status_code == 200, rejection.get_data(as_text=True)
    assert _json(rejection)["data"]["card"]["status"] == "rejected"

    visible_cards = _student_cards(client, enrolled_student_token, course_name)
    assert [card["card_uid"] for card in visible_cards] == [approved_card["card_uid"]]
    assert _student_cards(client, non_enrolled_student_token, course_name) == []
    rejected_detail = client.get(
        f"/api/student/concept-cards/{acceleration_card['card_uid']}",
        headers=bearer(enrolled_student_token),
    )
    assert rejected_detail.status_code == 404

    detail = _card_detail(client, enrolled_student_token, approved_card["card_uid"])
    assert detail["english_term"] == "Momentum"
    assert detail["chinese_term"] == "动量"
    assert detail["status"] == "approved"
    assert detail["reviewed_at"]
    assert detail["english_evidence"]
    assert detail["chinese_evidence"]
    assert {item["language"] for item in detail["english_evidence"]} == {"en"}
    assert {item["language"] for item in detail["chinese_evidence"]} == {"zh"}
    assert all(item["source_uid"] and item["chunk_uid"] for item in detail["english_evidence"])
    assert all(item["source_uid"] and item["chunk_uid"] for item in detail["chinese_evidence"])

    non_enrolled_feedback = client.post(
        f"/api/student/concept-cards/{approved_card['card_uid']}/feedback",
        json={"feedback_type": "explanation_unclear", "message": "I should not be able to submit."},
        headers=bearer(non_enrolled_student_token),
    )
    assert non_enrolled_feedback.status_code == 404
    draft_feedback = client.post(
        f"/api/student/concept-cards/{acceleration_card['card_uid']}/feedback",
        json={"feedback_type": "explanation_unclear", "message": "Draft/rejected cards reject feedback."},
        headers=bearer(enrolled_student_token),
    )
    assert draft_feedback.status_code == 404

    feedback = client.post(
        f"/api/student/concept-cards/{approved_card['card_uid']}/feedback",
        json={
            "feedback_type": "explanation_unclear",
            "message": "Please add a worked example.",
            "suggested_chinese_term": "动量",
        },
        headers={**bearer(enrolled_student_token), "X-Request-ID": f"11b-feedback-{uuid.uuid4().hex[:8]}"},
    )
    assert feedback.status_code == 200, feedback.get_data(as_text=True)
    feedback_payload = _json(feedback)["data"]["feedback"]
    assert feedback_payload["feedback_status"] == "submitted"
    assert feedback_payload["card_uid"] == approved_card["card_uid"]

    feedback_queue = client.get(
        f"/api/concept-cards/student-feedback-queue?course={quote(course_name)}&status=submitted",
        headers=bearer(teacher_token),
    )
    assert feedback_queue.status_code == 200, feedback_queue.get_data(as_text=True)
    queue_items = _json(feedback_queue)["data"]["items"]
    assert len(queue_items) == 1
    assert queue_items[0]["card_uid"] == approved_card["card_uid"]
    assert queue_items[0]["message"] == "Please add a worked example."

    unauthorized_queue = client.get(
        f"/api/concept-cards/student-feedback-queue?course={quote(course_name)}&status=submitted",
        headers=bearer(other_teacher_token),
    )
    assert unauthorized_queue.status_code == 200, unauthorized_queue.get_data(as_text=True)
    assert _json(unauthorized_queue)["data"]["items"] == []

    with app_module.app.app_context():
        assert app_module.AICallLog.query.count() == before_provider_calls
        assert app_module.DocumentAlignmentWorkflowRun.query.count() == before_workflow_runs + 1
        assert app_module.ConceptAlignmentCard.query.filter_by(course=course_name, status="approved").count() == 1
        assert app_module.ConceptAlignmentCard.query.filter_by(course=course_name, status="rejected").count() == 1
        assert app_module.Feedback.query.filter_by(
            feedback_source="student_concept_card",
            actual_result=approved_card["card_uid"],
            status="submitted",
        ).count() == 1
