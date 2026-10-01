import json
import uuid

from services import course_review_policy


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def _source_chunk(app_module, course, language, term):
    role = "english_course_material" if language == "en" else "chinese_reference_material"
    source = app_module.KnowledgeSource(
        source_uid=f"src-{uuid.uuid4().hex}",
        title=f"{term} source",
        course=course,
        language=language,
        source_role=role,
        trust_level="teacher_verified",
        quality_status="native_text_ok",
        status="active",
    )
    app_module.db.session.add(source)
    app_module.db.session.flush()
    chunk = app_module.KnowledgeChunk(
        chunk_uid=f"chunk-{uuid.uuid4().hex}",
        source_uid=source.source_uid,
        knowledge_source_id=source.id,
        document_id=0,
        course=course,
        language=language,
        content=f"{term} is supported by bounded governed evidence.",
        normalized_text=f"{term} is supported by bounded governed evidence.",
        source_locator="page:2;blocks:block-2;spans:0-48",
        page_number=2,
        block_type="paragraph",
        parse_uid=f"parse-{uuid.uuid4().hex}",
        parse_block_uid=f"block-{uuid.uuid4().hex}",
        quality_status="native_text_ok",
        trust_level="teacher_verified",
        status="active",
    )
    app_module.db.session.add(chunk)
    app_module.db.session.flush()
    return source, chunk


def _evidence(source, chunk, language, term, candidate_uid=""):
    value = {
        "source_uid": source.source_uid,
        "chunk_uid": chunk.chunk_uid,
        "language": language,
        "source_role": source.source_role,
        "source_status": "active",
        "quality_status": "native_text_ok",
        "source_locator": chunk.source_locator,
        "page_number": 2,
        "parse_uid": chunk.parse_uid,
        "parse_block_uid": chunk.parse_block_uid,
        "snippet": chunk.content,
        "score": 0.84,
        "rank": 1,
    }
    if candidate_uid:
        value.update({
            "candidate_uid": candidate_uid,
            "candidate_text": term,
            "chinese_term": term,
            "extraction_rank": 1,
            "retrieval_rank": 1,
            "evidence_backed": True,
            "generated": False,
        })
    return value


def _case(app_module, *, alternatives=True, fatal=False):
    course = f"Teacher Review Slice {uuid.uuid4().hex[:8]}"
    teacher = app_module.User.query.filter_by(role="teacher").first()
    policy = {
        "course": course,
        "required_evidence_sides": "both",
        "min_required_evidence_count": 2,
        "allow_teacher_override": True,
        "allow_approve_with_unverified_alignment": True,
    }
    course_review_policy.create_or_update_course_review_policy(
        app_module.db.session, app_module.CourseReviewPolicy, course, policy,
        actor=teacher, now_fn=app_module.current_time_text,
    )
    course_review_policy.grant_course_review_permission(
        app_module.db.session, app_module.CourseReviewPermission, course, teacher.id,
        {"reviewer_id": teacher.id, "reviewer_role": "teacher", "permission_level": "admin"},
        actor=teacher, now_fn=app_module.current_time_text,
    )
    en_source, en_chunk = _source_chunk(app_module, course, "en", "Electric potential")
    zh_source, zh_chunk = _source_chunk(app_module, course, "zh", "电势")
    chinese = [_evidence(zh_source, zh_chunk, "zh", "电势", "cand-primary")]
    if alternatives:
        alt_source, alt_chunk = _source_chunk(app_module, course, "zh", "电势能")
        alt = _evidence(alt_source, alt_chunk, "zh", "电势能", "cand-alternative")
        alt["rank"] = 2
        alt["extraction_rank"] = 2
        alt["retrieval_rank"] = 2
        chinese.append(alt)
    risks = ["evidence_provenance_incomplete"] if fatal else ["EVIDENCE_PAIR_UNCERTAIN"]
    card = app_module.ConceptAlignmentCard(
        card_uid=f"card-{uuid.uuid4().hex}",
        english_term="Electric potential",
        chinese_term="电势",
        course=course,
        chapter="Electrostatics",
        english_evidence=[_evidence(en_source, en_chunk, "en", "Electric potential")],
        chinese_evidence=chinese,
        risk_labels=risks,
        status="needs_review",
        confidence_score=0.78,
        retrieval_version="multilingual-e5-small@fixed",
        prompt_version="v1",
    )
    app_module.db.session.add(card)
    app_module.db.session.commit()
    return card


def test_teacher_review_case_lists_detail_and_keeps_machine_human_separate(
    client, app_module, teacher_token
):
    with app_module.app.app_context():
        card = _case(app_module)
        uid = card.card_uid
        course = card.course

    listed = client.get(
        f"/api/concept-cards/review-queue?course={course}",
        headers=bearer(teacher_token),
    )
    detail = client.get(
        f"/api/concept-cards/{uid}/review-case",
        headers=bearer(teacher_token),
    )
    assert listed.status_code == 200
    assert detail.status_code == 200
    case = detail.get_json()["data"]["case"]
    assert case["identity"]["alignment_case_uid"] == uid
    assert case["machine_decision"]["selected_candidate"]["candidate_uid"] == "cand-primary"
    assert case["human_review"]["decision"] == "UNREVIEWED"
    assert case["english"]["evidence"][0]["parse_block_uid"]
    assert len(case["chinese"]["candidate_pool"]) == 2


def test_accept_select_reject_defer_and_stale_version_contract(
    client, app_module, teacher_token
):
    with app_module.app.app_context():
        accept = _case(app_module)
        alternative = _case(app_module)
        reject = _case(app_module)
        defer = _case(app_module)
        versions = {card.card_uid: card.version for card in (accept, alternative, reject, defer)}

    def decide(card_uid, action, extra=None, expected=None, request_suffix=""):
        return client.post(
            f"/api/concept-cards/{card_uid}/review",
            json={
                "action": action,
                "expected_version": versions[card_uid] if expected is None else expected,
                "review_comment": "Teacher governed decision.",
                "reason_code": "teacher_verified" if action != "reject" else "chinese_term_wrong",
                **(extra or {}),
            },
            headers={
                **bearer(teacher_token),
                "Idempotency-Key": f"{action}-{card_uid}{request_suffix}",
            },
        )

    accepted = decide(accept.card_uid, "accept_recommendation")
    accepted_repeat = decide(accept.card_uid, "accept_recommendation")
    selected = decide(
        alternative.card_uid,
        "select_alternative_candidate",
        {"selected_candidate_uid": "cand-alternative"},
    )
    rejected = decide(reject.card_uid, "reject")
    deferred = decide(defer.card_uid, "defer_review")
    stale = decide(
        defer.card_uid,
        "defer_review",
        expected=versions[defer.card_uid],
        request_suffix="-stale",
    )

    assert accepted.status_code == 200
    assert accepted_repeat.status_code == 200
    assert accepted_repeat.get_json()["data"]["reused"] is True
    assert accepted.get_json()["data"]["case"]["business_status"] == "HUMAN_APPROVED"
    assert selected.status_code == 200
    assert selected.get_json()["data"]["case"]["machine_decision"]["selected_candidate"]["candidate_uid"] == "cand-primary"
    assert selected.get_json()["data"]["case"]["human_review"]["selected_candidate_uid"] == "cand-alternative"
    assert rejected.get_json()["data"]["case"]["business_status"] == "HUMAN_REJECTED"
    assert deferred.get_json()["data"]["case"]["business_status"] == "DEFERRED"
    assert stale.status_code == 409


def test_invalid_generated_and_fatal_candidates_cannot_be_approved(
    client, app_module, teacher_token
):
    with app_module.app.app_context():
        card = _case(app_module, fatal=True)
        uid = card.card_uid
        version = card.version
    response = client.post(
        f"/api/concept-cards/{uid}/review",
        json={
            "action": "accept_recommendation",
            "expected_version": version,
            "reason_code": "teacher_verified",
            "review_comment": "Must remain blocked.",
        },
        headers=bearer(teacher_token),
    )
    assert response.status_code == 400
    legacy_bypass = client.post(
        f"/api/concept-cards/{uid}/review",
        json={
            "action": "approve",
            "expected_version": version,
            "reason_code": "teacher_verified",
            "review_comment": "Legacy approval must not bypass fatal state.",
            "allow_risk_override": True,
            "override_reason": "This must remain blocked.",
        },
        headers=bearer(teacher_token),
    )
    assert legacy_bypass.status_code == 400

    with app_module.app.app_context():
        generated = _case(app_module)
        generated_uid = generated.card_uid
        generated_version = generated.version
        evidence = json.loads(generated.chinese_evidence)
        evidence[0]["generated"] = True
        evidence[0]["no_evidence"] = True
        evidence[0]["provenance_type"] = "GENERATED_HINT"
        generated.chinese_evidence = json.dumps(evidence, ensure_ascii=False)
        app_module.db.session.commit()
    generated_hint = client.post(
        f"/api/concept-cards/{generated_uid}/review",
        json={
            "action": "select_alternative_candidate",
            "expected_version": generated_version,
            "selected_candidate_uid": "cand-primary",
            "reason_code": "teacher_verified",
            "review_comment": "Generated hints are not evidence candidates.",
        },
        headers=bearer(teacher_token),
    )
    assert generated_hint.status_code == 400


def test_human_approval_rechecks_readiness_and_generates_one_fake_editable_draft(
    client, app_module, teacher_token
):
    with app_module.app.app_context():
        card = _case(app_module)
        uid = card.card_uid
        version = card.version
    premature_edit = client.put(
        f"/api/concept-cards/{uid}/draft",
        json={
            "expected_version": version,
            "english_explanation": "Must not bypass execution admission.",
        },
        headers=bearer(teacher_token),
    )
    assert premature_edit.status_code == 400
    accepted = client.post(
        f"/api/concept-cards/{uid}/review",
        json={
            "action": "accept_recommendation",
            "expected_version": version,
            "reason_code": "teacher_verified",
            "review_comment": "Evidence is sufficient.",
        },
        headers={**bearer(teacher_token), "Idempotency-Key": f"accept-{uid}"},
    )
    assert accepted.status_code == 200
    generated = client.post(
        f"/api/concept-cards/{uid}/generate-draft",
        json={"expected_version": accepted.get_json()["data"]["case"]["identity"]["version"]},
        headers={**bearer(teacher_token), "Idempotency-Key": f"draft-{uid}"},
    )
    repeated = client.post(
        f"/api/concept-cards/{uid}/generate-draft",
        json={"expected_version": accepted.get_json()["data"]["case"]["identity"]["version"]},
        headers={**bearer(teacher_token), "Idempotency-Key": f"draft-{uid}"},
    )
    assert generated.status_code == 200
    payload = generated.get_json()["data"]
    assert payload["readiness"]["decision"] == "READY"
    assert payload["readiness"]["approval_source"] == "HUMAN_REVIEW"
    assert payload["execution"]["status"] == "SUCCEEDED"
    assert payload["draft"]["publication_status"] == "NOT_PUBLISHED"
    assert repeated.status_code == 200
    assert repeated.get_json()["data"]["reused"] is True

    draft = client.get(f"/api/concept-cards/{uid}/draft", headers=bearer(teacher_token))
    updated = client.put(
        f"/api/concept-cards/{uid}/draft",
        json={
            "expected_version": draft.get_json()["data"]["draft"]["version"],
            "english_explanation": "Teacher-edited bounded explanation.",
        },
        headers=bearer(teacher_token),
    )
    assert updated.status_code == 200
    assert updated.get_json()["data"]["draft"]["english_explanation"].startswith("Teacher-edited")


def test_students_cannot_read_review_case_or_unpublished_draft(
    client, app_module, student_token
):
    with app_module.app.app_context():
        card = _case(app_module)
        uid = card.card_uid
    assert client.get(
        f"/api/concept-cards/{uid}/review-case", headers=bearer(student_token)
    ).status_code == 403
    assert client.get(
        f"/api/concept-cards/{uid}/draft", headers=bearer(student_token)
    ).status_code == 403
    assert client.get(
        f"/api/concept-cards/{uid}", headers=bearer(student_token)
    ).status_code == 403
