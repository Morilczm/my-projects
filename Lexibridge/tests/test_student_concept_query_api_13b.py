import uuid
from types import SimpleNamespace

import pytest


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def fake_ready_workflow(**kwargs):
    assert kwargs["allowed_source_uids"]
    return SimpleNamespace(
        english_term=kwargs["english_term"],
        english_evidence_candidates=[{
            "source_uid": kwargs["english_source_uid"],
            "chunk_uid": "english-evidence",
            "snippet": kwargs["english_context"],
            "page_number": 1,
        }],
        chinese_evidence_candidates=[{
            "source_uid": kwargs["allowed_source_uids"][0],
            "chunk_uid": "chinese-evidence",
            "snippet": "电势是单位电荷的电势能。",
            "page_number": 2,
        }],
        chinese_term_candidates=[{
            "candidate_uid": "candidate-potential",
            "chinese_term": "电势",
            "source_uid": kwargs["allowed_source_uids"][0],
            "chunk_uid": "chinese-evidence",
        }],
        selected_chinese_candidate={
            "candidate_uid": "candidate-potential",
            "chinese_term": "电势",
            "source_uid": kwargs["allowed_source_uids"][0],
            "chunk_uid": "chinese-evidence",
        },
        evidence_qualification={"decision": "QUALIFIED"},
        risk_labels=[],
    )


@pytest.fixture(autouse=True)
def restore_student_alignment_runner(app_module):
    sentinel = object()
    previous = app_module.app.config.get("STUDENT_ALIGNMENT_RUNNER", sentinel)
    yield
    if previous is sentinel:
        app_module.app.config.pop("STUDENT_ALIGNMENT_RUNNER", None)
    else:
        app_module.app.config["STUDENT_ALIGNMENT_RUNNER"] = previous


def seed_personal_material(app_module):
    suffix = uuid.uuid4().hex[:8]
    with app_module.app.app_context():
        student = app_module.User.query.filter_by(email="student.test@lexibridge.local").first()
        english = app_module.KnowledgeSource(
            source_uid=f"en-personal-{suffix}", name="Personal mechanics",
            language="en", scope_type="personal", owner_user_id=student.id,
            visibility="private", status="active", version=1,
            authorization_status="authorized", license_status="licensed",
            allow_student_search=True, source_role="english_course_material",
        )
        chinese = app_module.KnowledgeSource(
            source_uid=f"zh-personal-{suffix}", name="私人中文参考",
            language="zh", scope_type="personal", owner_user_id=student.id,
            visibility="private", status="active", version=1,
            authorization_status="authorized", license_status="licensed",
            allow_student_search=True, source_role="chinese_reference_material",
        )
        other = app_module.KnowledgeSource(
            source_uid=f"zh-other-{suffix}", name="Other private",
            language="zh", scope_type="personal", owner_user_id=student.id + 999,
            visibility="private", status="active", version=1,
            authorization_status="authorized", license_status="licensed",
            allow_student_search=True, source_role="chinese_reference_material",
        )
        app_module.db.session.add_all([english, chinese, other])
        app_module.db.session.flush()
        text = "The electric potential at a point equals potential energy per unit charge."
        chunk = app_module.KnowledgeChunk(
            chunk_uid=f"en-chunk-{suffix}", source_uid=english.source_uid,
            document_id=100000 + int(suffix[:4], 16), content=text,
            normalized_text=text.lower(), language="en", scope_type="personal",
            owner_user_id=str(student.id), visibility="private", status="active",
            quality_status="qualified", parse_block_uid=f"block-{suffix}",
            page_number=1,
        )
        app_module.db.session.add(chunk)
        app_module.db.session.commit()
        return student.id, english.source_uid, chinese.source_uid, other.source_uid, chunk.chunk_uid, text


def test_personal_query_is_private_non_official_idempotent_and_savable(
    app_module, client, student_token
):
    student_id, source_uid, chinese_uid, other_uid, chunk_uid, text = seed_personal_material(app_module)
    app_module.app.config["STUDENT_ALIGNMENT_RUNNER"] = fake_ready_workflow
    start = text.index("electric potential")
    payload = {
        "workspace_scope": "PERSONAL",
        "source_uid": source_uid,
        "chunk_uid": chunk_uid,
        "selected_text": "electric potential",
        "selection_start": start,
        "selection_end": start + len("electric potential"),
        "request_id": "request-personal-1",
    }
    response = client.post("/api/student/concept-queries", json=payload, headers=auth(student_token))
    assert response.status_code == 200
    query = response.get_json()["data"]["query"]
    assert query["alignment_status"] == "READY"
    assert query["visibility"] == "PRIVATE"
    assert query["authority"] == "NON_OFFICIAL"
    assert query["publication_status"] == "NOT_APPLICABLE"
    assert query["recommended_chinese_concept"]["text"] == "电势"
    support = query["learning_support"]
    assert support["contract_id"] == "student-learning-support@1.0.0"
    assert support["status"] == "EVIDENCE_GROUNDED"
    assert support["provider_used"] is False
    assert support["why_they_align"]["status"] == "EVIDENCE_BACKED"

    replay = client.post("/api/student/concept-queries", json=payload, headers=auth(student_token))
    assert replay.status_code == 200
    assert replay.get_json()["data"]["idempotent_replay"] is True
    assert replay.get_json()["data"]["query"]["query_uid"] == query["query_uid"]

    saved = client.put(
        f"/api/student/concept-queries/{query['query_uid']}/personal-record",
        json={
            "saved": True, "note": "Connect this to potential energy.",
            "understanding_state": "UNDERSTOOD", "expected_version": 0,
        },
        headers=auth(student_token),
    )
    assert saved.status_code == 200
    state = saved.get_json()["data"]["personal_state"]
    assert state["saved"] is True
    assert state["understanding_state"] == "UNDERSTOOD"
    assert state["version"] == 1
    fetched = client.get(
        f"/api/student/concept-queries/{query['query_uid']}/personal-record",
        headers=auth(student_token),
    )
    assert fetched.status_code == 200
    assert fetched.get_json()["data"]["personal_state"] == state

    with app_module.app.app_context():
        row = app_module.StudentConceptQuery.query.filter_by(query_uid=query["query_uid"]).one()
        allowed = set(app_module.json.loads(row.allowed_source_uids_json))
        assert chinese_uid in allowed
        assert other_uid not in allowed
        audits = app_module.AuditRecord.query.filter_by(target_uid=query["query_uid"]).all()
        assert audits
        assert all("Connect this" not in (item.input_payload or "") for item in audits)


def test_same_selection_recomputes_after_personal_evidence_scope_changes(
    app_module, client, student_token
):
    student_id, source_uid, _, _, chunk_uid, text = seed_personal_material(app_module)
    calls = []

    def recording_runner(**kwargs):
        calls.append(tuple(kwargs["allowed_source_uids"]))
        return fake_ready_workflow(**kwargs)

    app_module.app.config["STUDENT_ALIGNMENT_RUNNER"] = recording_runner
    start = text.index("electric potential")
    payload = {
        "workspace_scope": "PERSONAL",
        "source_uid": source_uid,
        "chunk_uid": chunk_uid,
        "selected_text": "electric potential",
        "selection_start": start,
        "selection_end": start + len("electric potential"),
    }
    first = client.post(
        "/api/student/concept-queries", json=payload, headers=auth(student_token)
    )
    assert first.status_code == 200
    assert first.get_json()["data"]["idempotent_replay"] is False

    with app_module.app.app_context():
        new_source = app_module.KnowledgeSource(
            source_uid=f"zh-personal-new-{uuid.uuid4().hex[:8]}",
            name="Updated private evidence",
            language="zh", scope_type="personal", owner_user_id=student_id,
            visibility="private", status="active", version=1,
            content_hash=uuid.uuid4().hex,
            authorization_status="authorized", license_status="licensed",
            allow_student_search=True, source_role="chinese_reference_material",
        )
        app_module.db.session.add(new_source)
        app_module.db.session.commit()

    second = client.post(
        "/api/student/concept-queries", json=payload, headers=auth(student_token)
    )
    assert second.status_code == 200
    assert second.get_json()["data"]["idempotent_replay"] is False
    assert second.get_json()["data"]["query"]["query_uid"] != (
        first.get_json()["data"]["query"]["query_uid"]
    )
    assert len(calls) == 2


def test_other_student_and_non_student_roles_cannot_read_private_query(
    app_module, client, student_token, teacher_token, admin_token
):
    _, source_uid, _, _, chunk_uid, text = seed_personal_material(app_module)
    app_module.app.config["STUDENT_ALIGNMENT_RUNNER"] = fake_ready_workflow
    start = text.index("electric potential")
    created = client.post(
        "/api/student/concept-queries",
        json={
            "workspace_scope": "PERSONAL", "source_uid": source_uid,
            "chunk_uid": chunk_uid, "selected_text": "electric potential",
            "selection_start": start, "selection_end": start + 18,
        },
        headers=auth(student_token),
    ).get_json()["data"]["query"]

    with app_module.app.app_context():
        other = app_module.User(
            username=f"other-{uuid.uuid4().hex[:8]}",
            email=f"other-{uuid.uuid4().hex[:8]}@example.test",
            password_hash=app_module.generate_password_hash("Other1234", method="pbkdf2:sha256"),
            role="student", is_verified=True, created_at=app_module.current_time_text(),
        )
        app_module.db.session.add(other)
        app_module.db.session.commit()
        other_email = other.email
    other_token = client.post(
        "/api/auth/login", json={"email": other_email, "password": "Other1234"}
    ).get_json()["token"]
    for token in (other_token, teacher_token, admin_token):
        response = client.get(
            f"/api/student/concept-queries/{created['query_uid']}", headers=auth(token)
        )
        assert response.status_code in {403, 404}


def test_stale_personal_record_version_is_conflict(app_module, client, student_token):
    _, source_uid, _, _, chunk_uid, text = seed_personal_material(app_module)
    app_module.app.config["STUDENT_ALIGNMENT_RUNNER"] = fake_ready_workflow
    start = text.index("electric potential")
    query = client.post(
        "/api/student/concept-queries",
        json={
            "workspace_scope": "PERSONAL", "source_uid": source_uid,
            "chunk_uid": chunk_uid, "selected_text": "electric potential",
            "selection_start": start, "selection_end": start + 18,
        },
        headers=auth(student_token),
    ).get_json()["data"]["query"]
    url = f"/api/student/concept-queries/{query['query_uid']}/personal-record"
    assert client.put(url, json={"saved": True, "expected_version": 0}, headers=auth(student_token)).status_code == 200
    assert client.put(url, json={"saved": False, "expected_version": 0}, headers=auth(student_token)).status_code == 409
    assert client.put(url, json={"saved": False, "expected_version": "bad"}, headers=auth(student_token)).status_code == 409


def test_personal_query_without_governed_chinese_evidence_fails_closed_without_runner(
    app_module, client, student_token
):
    student_id, source_uid, _, _, chunk_uid, text = seed_personal_material(app_module)
    with app_module.app.app_context():
        chinese_sources = app_module.KnowledgeSource.query.filter_by(
            language="zh", scope_type="personal", owner_user_id=student_id
        ).all()
        original_search_flags = {
            source.source_uid: bool(source.allow_student_search) for source in chinese_sources
        }
        for source in chinese_sources:
            source.allow_student_search = False
        app_module.db.session.commit()

    calls = []
    app_module.app.config["STUDENT_ALIGNMENT_RUNNER"] = lambda **kwargs: calls.append(kwargs)
    start = text.index("electric potential")
    response = client.post(
        "/api/student/concept-queries",
        json={
            "workspace_scope": "PERSONAL", "source_uid": source_uid,
            "chunk_uid": chunk_uid, "selected_text": "electric potential",
            "selection_start": start, "selection_end": start + 18,
        },
        headers=auth(student_token),
    )
    with app_module.app.app_context():
        for source_uid_value, allow_search in original_search_flags.items():
            source = app_module.KnowledgeSource.query.filter_by(
                source_uid=source_uid_value
            ).one()
            source.allow_student_search = allow_search
        app_module.db.session.commit()
    assert response.status_code == 200
    result = response.get_json()["data"]["query"]
    assert result["alignment_status"] == "NOT_READY"
    assert result["recommended_chinese_concept"] is None
    assert calls == []


def test_managed_course_uses_same_route_and_blocks_revoked_membership(
    app_module, client, student_token, test_course
):
    suffix = uuid.uuid4().hex[:8]
    with app_module.app.app_context():
        student = app_module.User.query.filter_by(email="student.test@lexibridge.local").first()
        membership = app_module.CourseMember.query.filter_by(
            course_id=test_course.id, user_id=student.id
        ).first()
        original_membership_status = membership.status if membership is not None else None
        if membership is None:
            membership = app_module.CourseMember(
                course_id=test_course.id, user_id=student.id, role="student",
                role_in_course="student", status="active",
                created_at=app_module.current_time_text(), joined_at=app_module.current_time_text(),
            )
            app_module.db.session.add(membership)
        else:
            membership.status = "active"
        english = app_module.KnowledgeSource(
            source_uid=f"en-course-{suffix}", name="Course mechanics", course="OCR Test Course",
            language="en", scope_type="course", course_id=test_course.id,
            visibility="course", status="active", version=1,
            authorization_status="authorized", license_status="licensed",
            allow_student_search=True, source_role="english_course_material",
        )
        chinese = app_module.KnowledgeSource(
            source_uid=f"zh-course-{suffix}", name="课程中文证据", course="OCR Test Course",
            language="zh", scope_type="course", course_id=test_course.id,
            visibility="course", status="active", version=1,
            authorization_status="authorized", license_status="licensed",
            allow_student_search=True, source_role="chinese_reference_material",
        )
        app_module.db.session.add_all([english, chinese])
        app_module.db.session.flush()
        text = "Angular velocity describes the rate of change of angular position."
        chunk = app_module.KnowledgeChunk(
            chunk_uid=f"en-course-chunk-{suffix}", source_uid=english.source_uid,
            document_id=200000 + int(suffix[:4], 16), content=text,
            normalized_text=text.lower(), language="en", scope_type="course",
            course="OCR Test Course", course_id=test_course.id, visibility="course",
            status="active", quality_status="qualified", page_number=3,
        )
        app_module.db.session.add(chunk)
        app_module.db.session.commit()
        source_uid, chunk_uid = english.source_uid, chunk.chunk_uid
    app_module.app.config["STUDENT_ALIGNMENT_RUNNER"] = fake_ready_workflow
    start = text.index("Angular velocity")
    response = client.post(
        "/api/student/concept-queries",
        json={
            "workspace_scope": "MANAGED_COURSE", "source_uid": source_uid,
            "chunk_uid": chunk_uid, "selected_text": "Angular velocity",
            "selection_start": start, "selection_end": start + len("Angular velocity"),
        },
        headers=auth(student_token),
    )
    assert response.status_code == 200
    query = response.get_json()["data"]["query"]
    assert query["workspace_scope"] == "MANAGED_COURSE"
    assert query["visibility"] == "PRIVATE"
    assert query["authority"] == "NON_OFFICIAL"
    with app_module.app.app_context():
        student = app_module.User.query.filter_by(email="student.test@lexibridge.local").first()
        membership = app_module.CourseMember.query.filter_by(
            course_id=test_course.id, user_id=student.id
        ).one()
        membership.status = "revoked"
        app_module.db.session.commit()
    assert client.get(
        f"/api/student/concept-queries/{query['query_uid']}", headers=auth(student_token)
    ).status_code == 404
    with app_module.app.app_context():
        student = app_module.User.query.filter_by(email="student.test@lexibridge.local").first()
        membership = app_module.CourseMember.query.filter_by(
            course_id=test_course.id, user_id=student.id
        ).one()
        membership.status = original_membership_status or "active"
        app_module.db.session.commit()
