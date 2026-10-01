import importlib.util
import json
from pathlib import Path

from test_concept_card_review import with_expected_version


ROOT = Path(__file__).resolve().parents[1]
SEED_SCRIPT = ROOT / "scripts" / "seed_review_demo.py"


def load_seed_module():
    spec = importlib.util.spec_from_file_location("seed_review_demo_module", SEED_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def login(client, email, password):
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()["token"]


def test_review_demo_seed_is_idempotent_and_marked(app_module):
    seed = load_seed_module()
    first = seed.seed_review_demo(app_module, reset_demo=True)
    second = seed.seed_review_demo(app_module, reset_demo=False)

    with app_module.app.app_context():
        assert first["card_uids"] == second["card_uids"]
        assert app_module.Course.query.filter_by(name=seed.DEMO_COURSE).count() == 1
        assert app_module.Course.query.filter_by(name=seed.DEMO_HIDDEN_COURSE).count() == 1
        assert app_module.User.query.filter(app_module.User.email.in_([data["email"] for data in seed.DEMO_USERS.values()])).count() == 5
        reviewer = app_module.User.query.filter_by(
            email=seed.DEMO_USERS["reviewer"]["email"],
            role="reviewer",
        ).one()
        reviewer_permission = app_module.CourseReviewPermission.query.filter_by(
            course=seed.DEMO_COURSE,
            reviewer_id=reviewer.id,
        ).one()
        assert reviewer_permission.reviewer_role == "reviewer"
        assert reviewer_permission.can_review is True
        assert app_module.CourseReviewPolicy.query.filter_by(course=seed.DEMO_COURSE).count() == 1
        assert app_module.CourseReviewPermission.query.filter_by(course=seed.DEMO_COURSE).count() == 3
        assert app_module.CourseStudentVisibilityPolicy.query.filter_by(course=seed.DEMO_COURSE).count() == 1
        assert app_module.CourseStudentVisibilityPolicy.query.filter_by(course=seed.DEMO_HIDDEN_COURSE).count() == 1
        assert app_module.StudentCourseMembership.query.filter_by(course=seed.DEMO_COURSE, status="active").count() == 2
        assert app_module.KnowledgeSource.query.filter_by(course=seed.DEMO_COURSE).count() == 2
        assert app_module.KnowledgeSource.query.filter_by(course=seed.DEMO_HIDDEN_COURSE).count() == 1
        assert app_module.KnowledgeChunk.query.filter_by(course=seed.DEMO_COURSE).count() == 7
        assert app_module.KnowledgeChunk.query.filter_by(course=seed.DEMO_HIDDEN_COURSE).count() == 2
        assert app_module.ConceptAlignmentCard.query.filter_by(course=seed.DEMO_COURSE).count() == 7
        assert app_module.ConceptAlignmentCard.query.filter_by(course=seed.DEMO_HIDDEN_COURSE).count() == 1
        assert app_module.AlignmentVerificationRun.query.filter_by(card_uid=first["card_uids"]["fourier"]).count() == 1
        assert app_module.StudentConceptCardState.query.filter_by(
            state_uid=first["student_state_uid"],
            card_uid=first["card_uids"]["impulse"],
            favorited=True,
            mastered=True,
        ).count() == 1
        assert app_module.StudentConceptCardState.query.filter(
            app_module.StudentConceptCardState.state_uid.in_(first["student_state_uids"])
        ).count() == 4
        assert app_module.Feedback.query.filter_by(
            feedback_uid=first["student_feedback_uid"],
            feedback_source="student_concept_card",
            card_uid=first["card_uids"]["impulse"],
            status="submitted",
        ).count() == 1
        assert app_module.Feedback.query.filter(
            app_module.Feedback.feedback_uid.in_(first["student_feedback_uids"]),
            app_module.Feedback.status == "submitted",
        ).count() >= 3
        assert app_module.Feedback.query.filter(
            app_module.Feedback.feedback_uid.in_(first["student_feedback_uids"]),
            app_module.Feedback.status == "resolved",
        ).count() == 1

        fourier = app_module.ConceptAlignmentCard.query.filter_by(card_uid=first["card_uids"]["fourier"]).first()
        transfer = app_module.ConceptAlignmentCard.query.filter_by(card_uid=first["card_uids"]["transfer"]).first()
        convergence = app_module.ConceptAlignmentCard.query.filter_by(card_uid=first["card_uids"]["convergence"]).first()
        approved = app_module.ConceptAlignmentCard.query.filter_by(card_uid=first["card_uids"]["impulse"]).first()
        frequency = app_module.ConceptAlignmentCard.query.filter_by(card_uid=first["card_uids"]["frequency_response"]).first()
        step = app_module.ConceptAlignmentCard.query.filter_by(card_uid=first["card_uids"]["step_response"]).first()
        rejected = app_module.ConceptAlignmentCard.query.filter_by(card_uid=first["card_uids"]["rejected"]).first()
        hidden = app_module.ConceptAlignmentCard.query.filter_by(card_uid=first["card_uids"]["hidden_approved"]).first()

        assert fourier.status == "needs_review"
        assert "bilingual_alignment_not_verified" in json.loads(fourier.risk_labels)
        assert json.loads(fourier.english_evidence)
        assert json.loads(fourier.chinese_evidence)
        assert transfer.status == "needs_review"
        assert "no_chinese_evidence" in json.loads(transfer.risk_labels)
        assert json.loads(transfer.chinese_evidence) == []
        assert convergence.status == "needs_review"
        assert "input_partial_text" in json.loads(convergence.risk_labels)
        assert approved.status == "approved"
        assert approved.english_term == "Impulse response"
        assert frequency.status == "approved"
        assert step.status == "approved"
        assert hidden.status == "approved"
        assert hidden.course == seed.DEMO_HIDDEN_COURSE
        assert rejected.status == "rejected"

        history_count = app_module.ConceptCardReviewRecord.query.filter(
            app_module.ConceptCardReviewRecord.card_uid.in_(first["card_uids"].values())
        ).count()
        assert history_count >= 5

    dumped = json.dumps(first, ensure_ascii=False)
    assert "sk-" not in dumped
    assert "API_KEY" not in dumped


def test_review_demo_api_workflow_and_policy_errors(client, app_module):
    seed = load_seed_module()
    summary = seed.seed_review_demo(app_module, reset_demo=True)

    teacher = summary["users"]["teacher"]
    admin = summary["users"]["admin"]
    student = summary["users"]["student"]
    teacher_token = login(client, teacher["email"], teacher["password"])
    admin_token = login(client, admin["email"], admin["password"])
    student_token = login(client, student["email"], student["password"])

    queue = client.get(
        f"/api/concept-cards/review-queue?course={seed.DEMO_COURSE.replace(' ', '%20')}&per_page=20",
        headers={**bearer(teacher_token), "X-Request-ID": "demo-review-queue"},
    )
    assert queue.status_code == 200, queue.get_data(as_text=True)
    queue_data = queue.get_json()
    assert queue_data["request_id"] == "demo-review-queue"
    items = queue_data["data"]["items"]
    assert {item["english_term"] for item in items} >= {"Fourier transform", "Transfer function", "Convergence"}
    assert "Impulse response" not in {item["english_term"] for item in items}
    assert {"card_uid", "english_term", "chinese_term", "course", "chapter", "status", "risk_labels"} <= set(items[0])
    assert "evidence_summary" in items[0]
    assert "verification_summary" in next(item for item in items if item["english_term"] == "Fourier transform")

    fourier_uid = summary["card_uids"]["fourier"]
    detail = client.get(
        f"/api/concept-cards/{fourier_uid}",
        headers={**bearer(teacher_token), "X-Request-ID": "demo-review-detail"},
    )
    history = client.get(
        f"/api/concept-cards/{fourier_uid}/reviews",
        headers={**bearer(teacher_token), "X-Request-ID": "demo-review-history"},
    )
    assert detail.status_code == 200
    assert detail.get_json()["data"]["card"]["english_term"] == "Fourier transform"
    assert history.status_code == 200
    assert history.get_json()["data"]["items"]

    revision = client.post(
        f"/api/concept-cards/{fourier_uid}/review",
        json=with_expected_version(app_module, fourier_uid, {
            "action": "request_revision",
            "reason_code": "evidence_insufficient",
            "required_changes": ["Add a second Chinese source"],
            "review_comment": "Demo request revision.",
        }),
        headers={**bearer(teacher_token), "X-Request-ID": "demo-request-revision"},
    )
    assert revision.status_code == 200, revision.get_data(as_text=True)
    assert revision.get_json()["request_id"] == "demo-request-revision"
    assert revision.get_json()["data"]["review"]["required_changes"] == ["Add a second Chinese source"]

    transfer_uid = summary["card_uids"]["transfer"]
    blocked = client.post(
        f"/api/concept-cards/{transfer_uid}/review",
        json=with_expected_version(app_module, transfer_uid, {
            "action": "approve",
            "reason_code": "teacher_verified",
            "review_comment": "Try approving missing Chinese evidence.",
            "allow_risk_override": True,
            "override_reason": "Demo should still be blocked by policy.",
        }),
        headers={**bearer(teacher_token), "X-Request-ID": "demo-policy-block"},
    )
    assert blocked.status_code == 400
    blocked_payload = blocked.get_json()
    assert blocked_payload["request_id"] == "demo-policy-block"
    assert blocked_payload["details"]["audit_error_code"] == "concept_card_review_validation_error"

    admin_approved = client.post(
        f"/api/concept-cards/{fourier_uid}/review",
        json=with_expected_version(app_module, fourier_uid, {
            "action": "approve",
            "reason_code": "teacher_verified",
            "review_comment": "Admin manually verified the demo card.",
            "allow_risk_override": True,
            "override_reason": "Admin verified both evidence sides for demo.",
            "resolved_risk_labels": ["bilingual_alignment_not_verified"],
        }),
        headers={**bearer(admin_token), "X-Request-ID": "demo-admin-approve"},
    )
    assert admin_approved.status_code == 200, admin_approved.get_data(as_text=True)
    assert admin_approved.get_json()["data"]["card"]["status"] == "approved"
    assert admin_approved.get_json()["data"]["card"]["confidence_score"] is None

    student_review = client.post(
        f"/api/concept-cards/{summary['card_uids']['convergence']}/review",
        json={"action": "request_revision", "reason_code": "evidence_insufficient"},
        headers={**bearer(student_token), "X-Request-ID": "demo-student-block"},
    )
    assert student_review.status_code == 403
    assert student_review.get_json()["request_id"] == "demo-student-block"

    with app_module.app.app_context():
        revision_record = app_module.ConceptCardReviewRecord.query.filter_by(
            card_uid=fourier_uid,
            request_id="demo-request-revision",
        ).first()
        revision_audit = app_module.AuditRecord.query.filter_by(
            request_id="demo-request-revision",
            event_type="concept_card_revision_requested",
        ).first()
        approval_audit = app_module.AuditRecord.query.filter_by(
            request_id="demo-admin-approve",
            event_type="concept_card_approved",
        ).first()
        blocked_audit = app_module.AuditRecord.query.filter(
            app_module.AuditRecord.request_id == "demo-policy-block",
            app_module.AuditRecord.event_type.in_([
                "concept_card_review_blocked_by_course_policy",
                "concept_card_risk_override_blocked_by_policy",
            ]),
        ).first()
        assert revision_record is not None
        assert revision_audit is not None
        assert approval_audit is not None
        assert blocked_audit is not None
        audit_dump = json.dumps(
            [revision_audit.input_payload, revision_audit.output_payload, blocked_audit.input_payload],
            ensure_ascii=False,
        )
        assert "Authorization" not in audit_dump
        assert "Cookie" not in audit_dump

    student_cards = client.get(
        f"/api/student/concept-cards?course={seed.DEMO_COURSE.replace(' ', '%20')}",
        headers={**bearer(student_token), "X-Request-ID": "demo-student-cards"},
    )
    assert student_cards.status_code == 200, student_cards.get_data(as_text=True)
    student_terms = {item["english_term"] for item in student_cards.get_json()["data"]["items"]}
    assert "Impulse response" in student_terms
    assert "Hidden course concept" not in student_terms

    hidden_cards = client.get(
        f"/api/student/concept-cards?course={seed.DEMO_HIDDEN_COURSE.replace(' ', '%20')}",
        headers={**bearer(student_token), "X-Request-ID": "demo-student-hidden"},
    )
    assert hidden_cards.status_code == 200
    assert hidden_cards.get_json()["data"]["items"] == []

    courses = client.get("/api/student/courses", headers=bearer(student_token))
    course_names = {item["course"] for item in courses.get_json()["data"]["items"]}
    assert seed.DEMO_COURSE in course_names
    assert seed.DEMO_HIDDEN_COURSE not in course_names

    progress = client.get(
        f"/api/student/progress?course={seed.DEMO_COURSE.replace(' ', '%20')}",
        headers={**bearer(student_token), "X-Request-ID": "demo-student-progress"},
    )
    assert progress.status_code == 200, progress.get_data(as_text=True)
    progress_overall = progress.get_json()["data"]["overall"]
    assert progress_overall["visible_card_count"] >= 1
    assert progress_overall["mastered_count"] >= 1
    assert progress_overall["favorited_count"] >= 1
    assert progress_overall["feedback_count"] >= 1

    feedback_queue = client.get(
        f"/api/concept-cards/student-feedback-queue?course={seed.DEMO_COURSE.replace(' ', '%20')}",
        headers={**bearer(teacher_token), "X-Request-ID": "demo-feedback-queue"},
    )
    assert feedback_queue.status_code == 200, feedback_queue.get_data(as_text=True)
    feedback_items = feedback_queue.get_json()["data"]["items"]
    assert any(item["feedback_uid"] == summary["student_feedback_uid"] for item in feedback_items)

    analytics = client.get(
        f"/api/teacher/learning-analytics?course={seed.DEMO_COURSE.replace(' ', '%20')}",
        headers={**bearer(teacher_token), "X-Request-ID": "demo-learning-analytics"},
    )
    assert analytics.status_code == 200, analytics.get_data(as_text=True)
    analytics_data = analytics.get_json()["data"]
    assert analytics_data["course_summary"]["approved_card_count"] >= 3
    assert analytics_data["course_summary"]["feedback_count"] >= 3
    assert analytics_data["feedback_hotspots"]

    analytics_export = client.get(
        f"/api/teacher/learning-analytics/export?course={seed.DEMO_COURSE.replace(' ', '%20')}&format=json",
        headers={**bearer(teacher_token), "X-Request-ID": "demo-learning-export"},
    )
    assert analytics_export.status_code == 200, analytics_export.get_data(as_text=True)
    assert analytics_export.get_json()["data"]["items"]

    seed.seed_review_demo(app_module, reset_demo=True)
    with app_module.app.app_context():
        assert app_module.Feedback.query.filter_by(feedback_uid=summary["student_feedback_uid"]).count() == 1
        assert app_module.StudentConceptCardState.query.filter_by(state_uid=summary["student_state_uid"]).count() == 1
        assert app_module.Feedback.query.filter(
            app_module.Feedback.feedback_uid.in_(summary["student_feedback_uids"])
        ).count() == len(summary["student_feedback_uids"])
        assert app_module.StudentConceptCardState.query.filter(
            app_module.StudentConceptCardState.state_uid.in_(summary["student_state_uids"])
        ).count() == len(summary["student_state_uids"])
