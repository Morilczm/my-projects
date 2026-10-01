import importlib.util
import io
import json
import socket
import uuid
from pathlib import Path

from test_concept_card_review import with_expected_version


ROOT = Path(__file__).resolve().parents[1]
SEED_SCRIPT = ROOT / "scripts" / "seed_review_demo.py"


def load_seed_module():
    spec = importlib.util.spec_from_file_location("seed_review_demo_module_e2e", SEED_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def login(client, email, password):
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()["token"]


def create_unprivileged_teacher(app_module):
    email = f"pilot-e2e-teacher-{uuid.uuid4().hex[:8]}@lexibridge.local"
    with app_module.app.app_context():
        user = app_module.User(
            username=f"pilot_e2e_teacher_{uuid.uuid4().hex[:8]}",
            email=email,
            password_hash=app_module.generate_password_hash("Teacher1234", method="pbkdf2:sha256"),
            role="teacher",
            is_verified=True,
            created_at=app_module.current_time_text(),
        )
        app_module.db.session.add(user)
        app_module.db.session.commit()
    return email


def upload_txt(client, token, course_id, content: bytes, request_id: str, filename: str = "pilot.txt"):
    return client.post(
        "/api/documents/upload?sync=true",
        data={
            "file": (io.BytesIO(content), filename),
            "scope_type": "course",
            "course_id": str(course_id),
            "language": "en",
            "source_name": "Pilot E2E Source",
            "chapter": "Pilot Chapter",
        },
        content_type="multipart/form-data",
        headers={**bearer(token), "X-Request-ID": request_id},
    )


def create_governed_bilingual_chunks(app_module, course: str = "Pilot Evidence Course"):
    with app_module.app.app_context():
        source = app_module.KnowledgeSource(
            title="Pilot bilingual reference",
            name="Pilot bilingual reference",
            source_title="Pilot bilingual reference",
            course=course,
            chapter="Frequency Domain",
            language="mixed",
            source_type="teacher_upload",
            source_role="bilingual_reference",
            owner_type="course",
            visibility="course",
            trust_level="high",
            quality_status="native_text_ok",
            quality_flags="[]",
            status="active",
            allow_derivative_cards=True,
            allow_student_search=True,
            allow_full_text_indexing=True,
            created_at=app_module.current_time_text(),
        )
        app_module.db.session.add(source)
        app_module.db.session.flush()
        english = app_module.KnowledgeChunk(
            document_id=0,
            source_uid=source.source_uid,
            knowledge_source_id=source.id,
            course=course,
            chapter="Frequency Domain",
            title=source.title,
            language="en",
            content="The Fourier transform maps a time-domain signal into a frequency-domain representation.",
            normalized_text="The Fourier transform maps a time-domain signal into a frequency-domain representation.",
            source_locator="pilot:en:1",
            source_citation="Pilot bilingual reference, section 1",
            source_section="Frequency Domain",
            trust_level="high",
            quality_status="native_text_ok",
            quality_flags="[]",
            status="active",
            visibility="course",
        )
        chinese = app_module.KnowledgeChunk(
            document_id=0,
            source_uid=source.source_uid,
            knowledge_source_id=source.id,
            course=course,
            chapter="Frequency Domain",
            title=source.title,
            language="mixed",
            content="傅里叶变换（Fourier transform）将时域信号表示为频域函数，是信号与系统课程中的基础概念。",
            normalized_text="傅里叶变换（Fourier transform）将时域信号表示为频域函数，是信号与系统课程中的基础概念。",
            source_locator="pilot:zh:1",
            source_citation="Pilot bilingual reference, section 2",
            source_section="Frequency Domain",
            trust_level="high",
            quality_status="native_text_ok",
            quality_flags="[]",
            status="active",
            visibility="course",
        )
        app_module.db.session.add_all([english, chinese])
        app_module.db.session.commit()
        return {
            "course": course,
            "source_uid": source.source_uid,
            "english_chunk_uid": english.chunk_uid,
            "chinese_chunk_uid": chinese.chunk_uid,
        }


def test_document_to_knowledge_asset_and_low_quality_block(client, app_module, teacher_token, test_course):
    success = upload_txt(
        client,
        teacher_token,
        test_course.id,
        b"Fourier transform evidence for a pilot upload.\nFrequency-domain representation.",
        "pilot-upload-success",
    )
    assert success.status_code == 200, success.get_data(as_text=True)
    payload = success.get_json()
    assert payload["request_id"] == "pilot-upload-success"
    assert payload["quality_status"] == "native_text_ok"
    assert payload["ingestion_status"] == "ingested"
    assert payload["source_uid"]
    assert payload["chunk_uids"]
    assert payload["knowledge_source"]["parse_uid"]
    assert payload["knowledge_chunks"][0]["parse_block_uid"]

    with app_module.app.app_context():
        parse = app_module.DocumentParseRecord.query.filter_by(parse_uid=payload["parse_uid"]).first()
        source = app_module.KnowledgeSource.query.filter_by(source_uid=payload["source_uid"]).first()
        chunk = app_module.KnowledgeChunk.query.filter_by(chunk_uid=payload["chunk_uids"][0]).first()
        audit = app_module.AuditRecord.query.filter_by(
            request_id="pilot-upload-success",
            event_type="document_ingestion_completed",
        ).first()
        assert parse is not None
        assert source is not None
        assert chunk is not None
        assert chunk.parse_uid == parse.parse_uid
        assert chunk.parse_block_uid
        assert audit is not None
        concept_cards = app_module.ConceptAlignmentCard.query.filter_by(parse_uid=payload["parse_uid"]).all()
        assert all(card.confidence_score is None for card in concept_cards)

    blocked = upload_txt(
        client,
        teacher_token,
        test_course.id,
        b"",
        "pilot-upload-blocked",
        filename="empty-pilot.txt",
    )
    assert blocked.status_code == 422, blocked.get_data(as_text=True)
    blocked_payload = blocked.get_json()
    assert blocked_payload["request_id"] == "pilot-upload-blocked"
    assert blocked_payload["status"] == "error"
    assert blocked_payload["details"]["ingestion_status"] == "blocked"
    assert blocked_payload["details"]["cards"] == []

    with app_module.app.app_context():
        parse_uid = blocked_payload["details"]["parse_uid"]
        parse = app_module.DocumentParseRecord.query.filter_by(parse_uid=parse_uid).first()
        chunks = app_module.KnowledgeChunk.query.filter_by(parse_uid=parse_uid, status="active").all()
        audit = app_module.AuditRecord.query.filter_by(
            request_id="pilot-upload-blocked",
            event_type="document_ingestion_blocked",
        ).first()
        assert parse is not None
        assert parse.quality_status in {"empty_text", "parse_failed", "ocr_unavailable"}
        assert chunks == []
        assert audit is not None


def test_evidence_to_candidate_to_concept_card_draft(client, app_module, teacher_token):
    context = create_governed_bilingual_chunks(app_module)
    headers = {**bearer(teacher_token), "X-Request-ID": "pilot-evidence-search"}

    evidence = client.post(
        "/api/evidence/search",
        json={"query": "Fourier transform", "course": context["course"], "limit": 5},
        headers=headers,
    )
    assert evidence.status_code == 200, evidence.get_data(as_text=True)
    evidence_data = evidence.get_json()["data"]
    assert evidence_data["candidates"]

    candidates = client.post(
        "/api/terms/chinese-candidates",
        json={"english_term": "Fourier transform", "course": context["course"], "limit": 5},
        headers={**bearer(teacher_token), "X-Request-ID": "pilot-chinese-candidates"},
    )
    assert candidates.status_code == 200, candidates.get_data(as_text=True)
    candidate_items = candidates.get_json()["data"]["candidates"]
    assert candidate_items
    assert any("傅里叶变换" in item["chinese_term"] for item in candidate_items)

    bilingual = client.post(
        "/api/evidence/bilingual",
        json={
            "english_term": "Fourier transform",
            "course": context["course"],
            "chapter": "Frequency Domain",
            "auto_generate_chinese_candidates": True,
            "limit": 5,
        },
        headers={**bearer(teacher_token), "X-Request-ID": "pilot-bilingual-evidence"},
    )
    assert bilingual.status_code == 200, bilingual.get_data(as_text=True)
    bilingual_data = bilingual.get_json()["data"]
    assert bilingual_data["selected_chinese_candidate"]
    assert "candidate_not_alignment_verified" in bilingual_data["risk_labels"]

    draft = client.post(
        "/api/concept-cards/draft-from-evidence",
        json={
            "english_term": "Fourier transform",
            "course": context["course"],
            "chapter": "Frequency Domain",
            "auto_generate_chinese_candidates": True,
            "force_create": True,
        },
        headers={**bearer(teacher_token), "X-Request-ID": "pilot-draft-from-evidence"},
    )
    assert draft.status_code == 200, draft.get_data(as_text=True)
    card = draft.get_json()["data"]["card"]
    assert card["status"] == "needs_review"
    assert card["confidence_score"] is None
    assert card["model_name"] == ""
    assert card["prompt_version"] == ""
    assert "candidate_not_alignment_verified" in card["risk_labels"]


def test_alignment_provider_safety_chain_without_network(client, app_module, admin_token, monkeypatch):
    seed = load_seed_module()
    summary = seed.seed_review_demo(app_module, reset_demo=True)
    fourier_uid = summary["card_uids"]["fourier"]

    def blocked_connect(*args, **kwargs):
        raise AssertionError("external network access is forbidden in pilot E2E tests")

    monkeypatch.setattr(socket.socket, "connect", blocked_connect)

    mock_verify = client.post(
        "/api/alignment/verify",
        json={"card_uid": fourier_uid, "provider": "mock-rule-v1", "attach_to_card": True},
        headers={**bearer(admin_token), "X-Request-ID": "pilot-align-mock"},
    )
    fake_verify = client.post(
        "/api/alignment/verify",
        json={"card_uid": fourier_uid, "provider": "fake-llm-v1", "fake_response_type": "valid", "attach_to_card": True},
        headers={**bearer(admin_token), "X-Request-ID": "pilot-align-fake"},
    )
    assert mock_verify.status_code == 200, mock_verify.get_data(as_text=True)
    assert fake_verify.status_code == 200, fake_verify.get_data(as_text=True)
    assert mock_verify.get_json()["data"]["can_auto_approve"] is False
    assert fake_verify.get_json()["data"]["is_production_result"] is False

    provider = "external-llm-replay-v1"
    policy = client.post(
        f"/api/alignment/providers/{provider}/policy",
        json={
            "provider_type": "replay_llm",
            "enabled": True,
            "status": "active",
            "replay_only": True,
            "allow_external_calls": False,
            "allow_attach_to_card": True,
            "allowed_courses": [seed.DEMO_COURSE],
            "allowed_roles": ["teacher", "admin"],
            "max_calls_per_day": 10,
            "max_calls_per_month": 20,
            "max_estimated_cost_per_call": 0.01,
            "max_estimated_cost_per_day": 0.05,
        },
        headers={**bearer(admin_token), "X-Request-ID": "pilot-align-policy"},
    )
    assert policy.status_code == 200, policy.get_data(as_text=True)

    replay_verify = client.post(
        "/api/alignment/verify",
        json={"card_uid": fourier_uid, "provider": provider, "replay_response_type": "valid", "attach_to_card": True},
        headers={**bearer(admin_token), "X-Request-ID": "pilot-align-replay"},
    )
    disabled_verify = client.post(
        "/api/alignment/verify",
        json={"card_uid": fourier_uid, "provider": "deepseek-alignment-v1-disabled", "attach_to_card": True},
        headers={**bearer(admin_token), "X-Request-ID": "pilot-align-disabled"},
    )
    preflight = client.post(
        f"/api/alignment/providers/{provider}/preflight",
        json={"course": seed.DEMO_COURSE, "include_replay_dry_run": True},
        headers={**bearer(admin_token), "X-Request-ID": "pilot-align-preflight"},
    )
    assert replay_verify.status_code == 200, replay_verify.get_data(as_text=True)
    assert disabled_verify.status_code == 200, disabled_verify.get_data(as_text=True)
    assert preflight.status_code == 200, preflight.get_data(as_text=True)
    assert replay_verify.get_json()["data"]["can_auto_approve"] is False
    assert disabled_verify.get_json()["data"]["verification_status"] == "failed"
    preflight_data = preflight.get_json()["data"]
    assert preflight_data["replay_dry_run_status"] == "passed"
    assert preflight_data["external_calls_enabled"] is False
    assert preflight_data["allow_auto_approve"] is False
    assert preflight_data["allow_production_result"] is False

    with app_module.app.app_context():
        card = app_module.ConceptAlignmentCard.query.filter_by(card_uid=fourier_uid).first()
        assert card.status != "approved"
        assert card.confidence_score is None
        runs = app_module.AlignmentVerificationRun.query.filter_by(card_uid=fourier_uid).all()
        assert {run.provider_name for run in runs} >= {"mock-rule-v1", "fake-llm-v1", provider, "deepseek-alignment-v1-disabled"}


def test_review_student_feedback_and_teacher_analytics_chain(client, app_module):
    seed = load_seed_module()
    summary = seed.seed_review_demo(app_module, reset_demo=True)
    teacher_token = login(client, summary["users"]["teacher"]["email"], summary["users"]["teacher"]["password"])
    admin_token = login(client, summary["users"]["admin"]["email"], summary["users"]["admin"]["password"])
    student_token = login(client, summary["users"]["student"]["email"], summary["users"]["student"]["password"])
    no_perm_email = create_unprivileged_teacher(app_module)
    no_perm_token = login(client, no_perm_email, "Teacher1234")

    queue = client.get(
        f"/api/concept-cards/review-queue?course={seed.DEMO_COURSE.replace(' ', '%20')}",
        headers={**bearer(teacher_token), "X-Request-ID": "pilot-review-queue"},
    )
    no_perm_queue = client.get(
        f"/api/concept-cards/review-queue?course={seed.DEMO_COURSE.replace(' ', '%20')}",
        headers={**bearer(no_perm_token), "X-Request-ID": "pilot-review-no-perm"},
    )
    assert queue.status_code == 200, queue.get_data(as_text=True)
    assert no_perm_queue.status_code == 200, no_perm_queue.get_data(as_text=True)
    assert queue.get_json()["data"]["items"]
    assert no_perm_queue.get_json()["data"]["items"] == []

    transfer_blocked = client.post(
        f"/api/concept-cards/{summary['card_uids']['transfer']}/review",
        json=with_expected_version(app_module, summary["card_uids"]["transfer"], {
            "action": "approve",
            "reason_code": "teacher_verified",
            "review_comment": "Attempting to approve missing Chinese evidence.",
        }),
        headers={**bearer(teacher_token), "X-Request-ID": "pilot-review-blocked"},
    )
    assert transfer_blocked.status_code == 400

    fourier_uid = summary["card_uids"]["fourier"]
    approved = client.post(
        f"/api/concept-cards/{fourier_uid}/review",
        json=with_expected_version(app_module, fourier_uid, {
            "action": "approve",
            "reason_code": "teacher_verified",
            "review_comment": "Admin verifies the card for pilot E2E.",
            "allow_risk_override": True,
            "override_reason": "Admin manually verified evidence for pilot E2E.",
            "resolved_risk_labels": ["bilingual_alignment_not_verified"],
        }),
        headers={**bearer(admin_token), "X-Request-ID": "pilot-review-approved"},
    )
    assert approved.status_code == 200, approved.get_data(as_text=True)
    assert approved.get_json()["data"]["card"]["status"] == "approved"
    assert approved.get_json()["data"]["card"]["confidence_score"] is None

    student_review = client.post(
        f"/api/concept-cards/{fourier_uid}/review",
        json={"action": "reject", "reason_code": "other"},
        headers={**bearer(student_token), "X-Request-ID": "pilot-student-review-denied"},
    )
    assert student_review.status_code == 403

    student_cards = client.get(
        "/api/student/concept-cards?per_page=100",
        headers={**bearer(student_token), "X-Request-ID": "pilot-student-cards"},
    )
    assert student_cards.status_code == 200, student_cards.get_data(as_text=True)
    terms = {item["english_term"] for item in student_cards.get_json()["data"]["items"]}
    assert "Impulse response" in terms
    assert "Hidden course concept" not in terms
    assert "Transfer function" not in terms

    impulse_uid = summary["card_uids"]["impulse"]
    state = client.post(
        f"/api/student/concept-cards/{impulse_uid}/state",
        json={"favorited": True, "mastered": True, "personal_note": "Pilot mastered."},
        headers={**bearer(student_token), "X-Request-ID": "pilot-student-state"},
    )
    feedback = client.post(
        f"/api/student/concept-cards/{impulse_uid}/feedback",
        json={"feedback_type": "explanation_unclear", "message": "Pilot feedback loop."},
        headers={**bearer(student_token), "X-Request-ID": "pilot-student-feedback"},
    )
    export = client.get(
        "/api/student/concept-cards/export?scope=favorited&format=json",
        headers={**bearer(student_token), "X-Request-ID": "pilot-student-export"},
    )
    assert state.status_code == 200, state.get_data(as_text=True)
    assert feedback.status_code == 200, feedback.get_data(as_text=True)
    assert export.status_code == 200, export.get_data(as_text=True)
    assert export.get_json()["data"]["items"]

    feedback_queue = client.get(
        f"/api/concept-cards/student-feedback-queue?course={seed.DEMO_COURSE.replace(' ', '%20')}&status=submitted",
        headers={**bearer(teacher_token), "X-Request-ID": "pilot-feedback-queue"},
    )
    no_perm_feedback = client.get(
        f"/api/concept-cards/student-feedback-queue?course={seed.DEMO_COURSE.replace(' ', '%20')}&status=submitted",
        headers={**bearer(no_perm_token), "X-Request-ID": "pilot-feedback-no-perm"},
    )
    assert feedback_queue.status_code == 200, feedback_queue.get_data(as_text=True)
    assert no_perm_feedback.status_code == 200, no_perm_feedback.get_data(as_text=True)
    assert feedback_queue.get_json()["data"]["items"]
    assert no_perm_feedback.get_json()["data"]["items"] == []

    feedback_uid = feedback_queue.get_json()["data"]["items"][0]["feedback_uid"]
    acknowledged = client.post(
        f"/api/concept-cards/student-feedback/{feedback_uid}/triage",
        json={"action": "acknowledge", "teacher_note": "Acknowledged in pilot E2E."},
        headers={**bearer(teacher_token), "X-Request-ID": "pilot-feedback-ack"},
    )
    revision = client.post(
        f"/api/concept-cards/student-feedback/{feedback_uid}/triage",
        json={
            "action": "request_card_revision",
            "reason_code": "other",
            "teacher_note": "Student feedback requires revision.",
            "required_changes": ["Clarify Chinese explanation"],
        },
        headers={**bearer(teacher_token), "X-Request-ID": "pilot-feedback-revision"},
    )
    assert acknowledged.status_code == 200, acknowledged.get_data(as_text=True)
    assert revision.status_code == 200, revision.get_data(as_text=True)

    analytics = client.get(
        f"/api/teacher/learning-analytics?course={seed.DEMO_COURSE.replace(' ', '%20')}",
        headers={**bearer(teacher_token), "X-Request-ID": "pilot-teacher-analytics"},
    )
    student_analytics = client.get(
        f"/api/teacher/learning-analytics?course={seed.DEMO_COURSE.replace(' ', '%20')}",
        headers={**bearer(student_token), "X-Request-ID": "pilot-student-analytics-denied"},
    )
    analytics_export = client.get(
        f"/api/teacher/learning-analytics/export?course={seed.DEMO_COURSE.replace(' ', '%20')}&format=json",
        headers={**bearer(teacher_token), "X-Request-ID": "pilot-teacher-analytics-export"},
    )
    assert analytics.status_code == 200, analytics.get_data(as_text=True)
    assert student_analytics.status_code == 403
    assert analytics_export.status_code == 200, analytics_export.get_data(as_text=True)
    analytics_data = analytics.get_json()["data"]
    assert analytics_data["course_summary"]["approved_card_count"] >= 1
    assert analytics_data["feedback_hotspots"]
    export_dump = json.dumps(analytics_export.get_json(), ensure_ascii=False)
    assert "AuditRecord" not in export_dump
    assert "override_reason" not in export_dump
    assert "Authorization" not in export_dump

    with app_module.app.app_context():
        card = app_module.ConceptAlignmentCard.query.filter_by(card_uid=impulse_uid).first()
        assert card.status in {"approved", "needs_review"}
        assert app_module.ConceptCardReviewRecord.query.filter_by(request_id="pilot-feedback-revision").first() is not None
        assert app_module.AuditRecord.query.filter_by(request_id="pilot-feedback-revision").first() is not None
