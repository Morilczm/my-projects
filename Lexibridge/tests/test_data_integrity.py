import importlib.util
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SEED_SCRIPT = ROOT / "scripts" / "seed_review_demo.py"


def load_seed_module():
    spec = importlib.util.spec_from_file_location("seed_review_demo_module_integrity", SEED_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def login(client, email, password):
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()["token"]


def loads(value, fallback):
    if value in (None, ""):
        return fallback
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


def assert_json_list(value, field_name):
    parsed = loads(value, None)
    assert isinstance(parsed, list), field_name


def test_core_pilot_data_integrity_in_demo_namespace(client, app_module):
    seed = load_seed_module()
    summary = seed.seed_review_demo(app_module, reset_demo=True)

    with app_module.app.app_context():
        approved_cards = app_module.ConceptAlignmentCard.query.filter_by(status="approved").all()
        assert approved_cards
        for card in approved_cards:
            assert str(card.english_term or "").strip()
            assert str(card.chinese_term or "").strip()
            assert str(card.course or "").strip()
            assert loads(card.english_evidence, []) or loads(card.chinese_evidence, [])
            assert_json_list(card.risk_labels, f"card {card.card_uid} risk_labels")
            assert_json_list(card.input_risk_labels, f"card {card.card_uid} input_risk_labels")
            assert_json_list(card.parse_quality_flags, f"card {card.card_uid} parse_quality_flags")
            if card.confidence_score is not None:
                assert 0 <= float(card.confidence_score) <= 1

        cards_by_uid = {card.card_uid: card for card in app_module.ConceptAlignmentCard.query.all()}
        for state in app_module.StudentConceptCardState.query.all():
            assert state.card_uid in cards_by_uid

        feedbacks = app_module.Feedback.query.filter_by(feedback_source="student_concept_card").all()
        for feedback in feedbacks:
            assert feedback.card_uid in cards_by_uid
            assert feedback.linked_card_uid in {"", feedback.card_uid}

        sources_by_uid = {source.source_uid: source for source in app_module.KnowledgeSource.query.all()}
        for chunk in app_module.KnowledgeChunk.query.all():
            if chunk.source_uid:
                assert chunk.source_uid in sources_by_uid
            assert_json_list(chunk.quality_flags, f"chunk {chunk.chunk_uid} quality_flags")
            if chunk.parse_uid:
                parse_record = app_module.DocumentParseRecord.query.filter_by(parse_uid=chunk.parse_uid).first()
                if parse_record and chunk.parse_block_uid:
                    assert app_module.DocumentParseBlock.query.filter_by(block_uid=chunk.parse_block_uid).first() is not None

        for review in app_module.ConceptCardReviewRecord.query.all():
            assert review.card_uid in cards_by_uid
            assert_json_list(review.required_changes, f"review {review.review_uid} required_changes")
            assert_json_list(review.resolved_risk_labels, f"review {review.review_uid} resolved_risk_labels")
            assert_json_list(review.remaining_risk_labels, f"review {review.review_uid} remaining_risk_labels")

        for run in app_module.AlignmentVerificationRun.query.all():
            if run.card_uid:
                assert run.card_uid in cards_by_uid
            if run.alignment_confidence is not None:
                assert 0 <= float(run.alignment_confidence) <= 1
            assert_json_list(run.risk_labels, f"run {run.run_uid} risk_labels")
            output = loads(run.output_payload, {})
            if run.provider_type in {"mock", "fake_llm", "replay_llm"}:
                assert output.get("is_production_result") is not True

        active_memberships = [
            (membership.user_id, membership.course)
            for membership in app_module.StudentCourseMembership.query.filter_by(status="active").all()
        ]
        duplicates = [item for item, count in Counter(active_memberships).items() if count > 1]
        assert duplicates == []

        active_visibility_policies = [
            policy.course
            for policy in app_module.CourseStudentVisibilityPolicy.query.filter_by(status="active").all()
        ]
        duplicates = [item for item, count in Counter(active_visibility_policies).items() if count > 1]
        assert duplicates == []

        for policy in app_module.AlignmentProviderPolicy.query.all():
            assert policy.allow_auto_approve is False
            assert policy.require_human_review is True

        assert app_module.DocumentAlignmentWorkflowRun.__tablename__ == "document_alignment_workflow_runs"
        assert app_module.DocumentAlignmentWorkflowItem.__tablename__ == "document_alignment_workflow_items"
        assert (
            app_module.DocumentAlignmentItemVerificationExecution.__tablename__
            == "document_alignment_item_verification_executions"
        )
        assert app_module.DocumentAlignmentWorkflowRun.query.count() == 0
        assert app_module.DocumentAlignmentWorkflowItem.query.count() == 0
        assert app_module.DocumentAlignmentItemVerificationExecution.query.count() == 0

        secret_dump = json.dumps(
            [
                {
                    "event": audit.event_type,
                    "input": audit.input_payload,
                    "output": audit.output_payload,
                }
                for audit in app_module.AuditRecord.query.all()
            ],
            ensure_ascii=False,
        )
        assert "Authorization" not in secret_dump
        assert "Cookie" not in secret_dump
        assert "sk-" not in secret_dump

    student = summary["users"]["student"]
    student_token = login(client, student["email"], student["password"])
    response = client.get(
        "/api/student/concept-cards?per_page=100",
        headers={**bearer(student_token), "X-Request-ID": "integrity-student-list"},
    )
    assert response.status_code == 200, response.get_data(as_text=True)
    payload = response.get_json()
    assert payload["request_id"] == "integrity-student-list"
    statuses = {item["status"] for item in payload["data"]["items"]}
    assert statuses <= {"approved"}
    terms = {item["english_term"] for item in payload["data"]["items"]}
    assert "Hidden course concept" not in terms
    assert "Rejected example" not in terms
