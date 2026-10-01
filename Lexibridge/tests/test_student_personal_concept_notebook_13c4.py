import json
import uuid


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def _raw_result(*, query_uid, result_uid, scope, workspace_uid, source_uid, term, chinese, decision):
    return {
        "query_uid": query_uid,
        "result_uid": result_uid,
        "result_version": 1,
        "workspace_scope": scope,
        "workspace_uid": workspace_uid,
        "source_uid": source_uid,
        "source_version": "1",
        "english_term": term,
        "selected_text": term,
        "bounded_context": f"A bounded course explanation of {term}.",
        "english_evidence": [{
            "source_uid": source_uid,
            "chunk_uid": f"{source_uid}-en",
            "page_number": 1,
            "block_uid": f"{source_uid}-block",
            "span_start": 0,
            "span_end": len(term),
            "snippet": f"A bounded course explanation of {term}.",
        }],
        "chinese_evidence": ([{
            "source_uid": f"{source_uid}-zh",
            "chunk_uid": f"{source_uid}-zh-chunk",
            "page_number": 2,
            "block_uid": f"{source_uid}-zh-block",
            "snippet": f"{chinese}的有界中文证据。",
        }] if chinese else []),
        "chinese_candidates": ([{
            "candidate_uid": f"candidate-{result_uid}",
            "text": chinese,
            "source_uid": f"{source_uid}-zh",
            "chunk_uid": f"{source_uid}-zh-chunk",
            "evidence_backed": True,
        }] if chinese else []),
        "selected_candidate": ({
            "candidate_uid": f"candidate-{result_uid}",
            "text": chinese,
            "source_uid": f"{source_uid}-zh",
            "chunk_uid": f"{source_uid}-zh-chunk",
        } if chinese else None),
        "qualification": {"decision": decision},
        "risk_labels": [],
        "generated_hints": [],
        "created_at": "2026-08-15T10:00:00Z",
        "updated_at": "2026-08-15T10:00:00Z",
    }


def seed_notebook(app_module):
    marker = uuid.uuid4().hex[:10]
    with app_module.app.app_context():
        student = app_module.User.query.filter_by(
            email="student.test@lexibridge.local"
        ).one()
        course = app_module.Course.query.filter_by(name="OCR Test Course").one()
        membership = app_module.CourseMember.query.filter_by(
            user_id=student.id, course_id=course.id
        ).first()
        if membership is None:
            membership = app_module.CourseMember(
                user_id=student.id,
                course_id=course.id,
                role="student",
                role_in_course="student",
                status="active",
                created_at=app_module.current_time_text(),
                joined_at=app_module.current_time_text(),
            )
            app_module.db.session.add(membership)
        else:
            membership.status = "active"

        personal_source = app_module.KnowledgeSource(
            source_uid=f"notebook-personal-{marker}",
            name=f"Personal notebook source {marker}",
            title=f"Personal notebook source {marker}",
            language="en",
            scope_type="personal",
            owner_user_id=student.id,
            visibility="private",
            status="active",
            version=1,
            authorization_status="authorized",
            license_status="licensed",
            allow_student_search=True,
            source_role="english_course_material",
        )
        course_source = app_module.KnowledgeSource(
            source_uid=f"notebook-course-{marker}",
            name=f"Managed notebook source {marker}",
            title=f"Managed notebook source {marker}",
            language="en",
            scope_type="course",
            course_id=course.id,
            course=course.name,
            visibility="course",
            status="active",
            version=1,
            authorization_status="authorized",
            license_status="licensed",
            allow_student_search=True,
            source_role="english_course_material",
        )
        app_module.db.session.add_all([personal_source, course_source])
        app_module.db.session.flush()

        definitions = [
            ("PERSONAL", f"personal:{student.id}", personal_source, None,
             f"electric potential {marker}", "电势", "QUALIFIED", True,
             f"Connect potential to energy {marker}.", "UNDERSTOOD"),
            ("MANAGED_COURSE", f"course:{course.id}", course_source, course.id,
             f"electric field {marker}", "电场", "REVIEW_REQUIRED", True,
             f"Compare the two candidates {marker}.", "STILL_CONFUSED"),
            ("PERSONAL", f"personal:{student.id}", personal_source, None,
             f"field line {marker}", "", "REJECTED", False, "", ""),
        ]
        seeded = []
        for index, (
            scope, workspace_uid, source, course_id, term, chinese, decision,
            saved, note, understanding,
        ) in enumerate(definitions):
            query_uid = f"query-{marker}-{index}"
            result_uid = f"result-{marker}-{index}"
            raw = _raw_result(
                query_uid=query_uid,
                result_uid=result_uid,
                scope=scope,
                workspace_uid=workspace_uid,
                source_uid=source.source_uid,
                term=term,
                chinese=chinese,
                decision=decision,
            )
            query = app_module.StudentConceptQuery(
                query_uid=query_uid,
                result_uid=result_uid,
                student_id=student.id,
                workspace_scope=scope,
                workspace_uid=workspace_uid,
                course_id=course_id,
                source_uid=source.source_uid,
                source_version="1",
                chunk_uid=f"chunk-{marker}-{index}",
                selected_text=term,
                selection_start=0,
                selection_end=len(term),
                query_fingerprint=f"fingerprint-{marker}-{index}",
                result_json=json.dumps(raw, ensure_ascii=False, sort_keys=True),
                processing_status="completed",
                version=1,
                created_at=f"2026-08-15T10:0{index}:00Z",
                updated_at=f"2026-08-15T10:0{index}:00Z",
            )
            app_module.db.session.add(query)
            if saved:
                app_module.db.session.add(app_module.PersonalLearningRecord(
                    record_uid=f"record-{marker}-{index}",
                    student_id=student.id,
                    query_uid=query_uid,
                    result_uid=result_uid,
                    workspace_scope=scope,
                    workspace_uid=workspace_uid,
                    saved=True,
                    personal_note=note,
                    understanding_state=understanding,
                    last_viewed_at=f"2026-08-15T11:0{index}:00Z",
                    version=1,
                    created_at=f"2026-08-15T10:0{index}:00Z",
                    updated_at=f"2026-08-15T11:0{index}:00Z",
                ))
            seeded.append({
                "query_uid": query_uid,
                "result_uid": result_uid,
                "scope": scope,
                "source_uid": source.source_uid,
                "term": term,
                "chinese": chinese,
            })
        app_module.db.session.commit()
        return {
            "marker": marker,
            "student_id": student.id,
            "course_id": course.id,
            "membership_id": membership.id,
            "items": seeded,
        }


def test_notebook_lists_saved_personal_and_managed_results_with_private_dimensions(
    app_module, client, student_token
):
    seeded = seed_notebook(app_module)
    response = client.get(
        f"/api/student/personal-concept-notebook?q={seeded['marker']}",
        headers=auth(student_token),
    )
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["contract_id"] == "personal-concept-notebook@1.0.0"
    assert data["filters"]["view"] == "SAVED"
    assert data["pagination"]["total"] == 2
    assert {item["workspace_scope"] for item in data["items"]} == {
        "PERSONAL", "MANAGED_COURSE"
    }
    assert all(item["visibility"] == "PRIVATE" for item in data["items"])
    assert all(item["authority"] == "NON_OFFICIAL" for item in data["items"])
    assert all(item["publication_status"] == "NOT_APPLICABLE" for item in data["items"])
    assert all("note" not in item["personal_state"] for item in data["items"])
    assert all(len(item["note_preview"]) <= 240 for item in data["items"])


def test_notebook_history_search_filters_and_pagination(app_module, client, student_token):
    seeded = seed_notebook(app_module)
    base = "/api/student/personal-concept-notebook"
    history = client.get(
        f"{base}?view=HISTORY&q={seeded['marker']}&per_page=2&page=1",
        headers=auth(student_token),
    ).get_json()["data"]
    assert history["pagination"]["total"] == 3
    assert len(history["items"]) == 2
    assert history["pagination"]["has_next"] is True

    managed = client.get(
        f"{base}?view=SAVED&workspace_scope=MANAGED_COURSE&alignment_status=REVIEW_REQUIRED&q={seeded['marker']}",
        headers=auth(student_token),
    ).get_json()["data"]
    assert [item["english_concept"] for item in managed["items"]] == [
        f"electric field {seeded['marker']}"
    ]

    note_search = client.get(
        f"{base}?view=SAVED&q=Compare%20the%20two%20candidates%20{seeded['marker']}",
        headers=auth(student_token),
    ).get_json()["data"]
    assert len(note_search["items"]) == 1
    assert note_search["items"][0]["understanding_state"] == "STILL_CONFUSED"

    not_ready = client.get(
        f"{base}?view=HISTORY&alignment_status=NOT_READY&q={seeded['marker']}",
        headers=auth(student_token),
    ).get_json()["data"]
    assert len(not_ready["items"]) == 1
    assert not_ready["items"][0]["recommended_chinese_concept"] is None


def test_notebook_detail_and_revisit_are_owner_only_versioned_and_idempotent(
    app_module, client, student_token, teacher_token, admin_token
):
    seeded = seed_notebook(app_module)
    query_uid = seeded["items"][0]["query_uid"]
    detail_url = f"/api/student/personal-concept-notebook/{query_uid}"
    detail = client.get(detail_url, headers=auth(student_token))
    assert detail.status_code == 200
    assert detail.get_json()["data"]["query"]["query_uid"] == query_uid
    assert len(detail.get_json()["data"]["query"]["english_evidence"][0]["snippet"]) <= 800

    before = detail.get_json()["data"]["query"]["personal_state"]
    revisit_url = f"{detail_url}/revisit"
    key = f"revisit-{uuid.uuid4()}"
    first = client.post(
        revisit_url,
        json={"expected_version": before["version"]},
        headers={**auth(student_token), "Idempotency-Key": key},
    )
    assert first.status_code == 200
    assert first.get_json()["data"]["idempotent_replay"] is False
    after = first.get_json()["data"]["query"]["personal_state"]
    assert after["last_viewed_at"]
    assert after["version"] == before["version"] + 1

    replay = client.post(
        revisit_url,
        json={"expected_version": before["version"]},
        headers={**auth(student_token), "Idempotency-Key": key},
    )
    assert replay.status_code == 200
    assert replay.get_json()["data"]["idempotent_replay"] is True
    assert replay.get_json()["data"]["query"]["personal_state"]["version"] == after["version"]

    for token in (teacher_token, admin_token):
        assert client.get(detail_url, headers=auth(token)).status_code == 403


def test_personal_record_update_replays_same_key_and_rejects_conflicting_payload(
    app_module, client, student_token
):
    seeded = seed_notebook(app_module)
    query_uid = seeded["items"][2]["query_uid"]
    url = f"/api/student/concept-queries/{query_uid}/personal-record"
    key = f"record-{uuid.uuid4()}"
    headers = {**auth(student_token), "Idempotency-Key": key}
    first = client.put(
        url,
        json={"saved": True, "note": "A private note.", "expected_version": 0},
        headers=headers,
    )
    assert first.status_code == 200
    assert first.get_json()["data"]["idempotent_replay"] is False
    replay = client.put(
        url,
        json={"saved": True, "note": "A private note.", "expected_version": 0},
        headers=headers,
    )
    assert replay.status_code == 200
    assert replay.get_json()["data"]["idempotent_replay"] is True
    conflict = client.put(
        url,
        json={"saved": False, "note": "A different note.", "expected_version": 0},
        headers=headers,
    )
    assert conflict.status_code == 409
    assert conflict.get_json()["error_code"] == "STUDENT_PERSONAL_RECORD_IDEMPOTENCY_CONFLICT"

    with app_module.app.app_context():
        audits = app_module.AuditRecord.query.filter_by(
            target_uid=query_uid,
            event_type="personal_learning_record_updated",
            request_id=key,
        ).all()
        assert len(audits) == 1
        assert "A private note" not in audits[0].input_payload


def test_notebook_preserves_deleted_source_history_and_revoked_course_privacy(
    app_module, client, student_token
):
    seeded = seed_notebook(app_module)
    personal = seeded["items"][0]
    managed = seeded["items"][1]
    with app_module.app.app_context():
        source = app_module.KnowledgeSource.query.filter_by(
            source_uid=personal["source_uid"]
        ).one()
        source.status = "deleted"
        membership = app_module.db.session.get(
            app_module.CourseMember, seeded["membership_id"]
        )
        membership.status = "revoked"
        app_module.db.session.commit()

    data = client.get(
        f"/api/student/personal-concept-notebook?view=HISTORY&q={seeded['marker']}",
        headers=auth(student_token),
    ).get_json()["data"]
    by_uid = {item["query_uid"]: item for item in data["items"]}
    assert personal["query_uid"] in by_uid
    assert by_uid[personal["query_uid"]]["source_availability"] == "SOURCE_UNAVAILABLE"
    assert by_uid[personal["query_uid"]]["evidence_availability"] == "UNAVAILABLE"
    assert managed["query_uid"] not in by_uid

    detail = client.get(
        f"/api/student/concept-queries/{personal['query_uid']}",
        headers=auth(student_token),
    )
    assert detail.status_code == 200
    unavailable = detail.get_json()["data"]["query"]
    assert unavailable["bounded_context"] == ""
    assert unavailable["english_evidence"] == []
    assert unavailable["chinese_evidence"] == []
    assert unavailable["evidence_complete"] is False
    assert unavailable["learning_support"]["status"] == "SOURCE_UNAVAILABLE"
    assert unavailable["learning_support"]["why_they_align"]["status"] == "UNAVAILABLE"
    assert unavailable["learning_support"]["candidate_evidence"] == []
    assert unavailable["learning_support"]["do_not_confuse_with"] == []


def test_notebook_rejects_invalid_filters_and_non_student_roles(
    app_module, client, student_token, teacher_token, admin_token
):
    assert client.get(
        "/api/student/personal-concept-notebook?view=OFFICIAL",
        headers=auth(student_token),
    ).status_code == 400
    assert client.get(
        "/api/student/personal-concept-notebook?workspace_scope=COURSE_SHARED",
        headers=auth(student_token),
    ).status_code == 400
    assert client.get(
        "/api/student/personal-concept-notebook?per_page=500",
        headers=auth(student_token),
    ).status_code == 400
    for token in (teacher_token, admin_token):
        assert client.get(
            "/api/student/personal-concept-notebook", headers=auth(token)
        ).status_code == 403


def test_other_student_and_reviewer_cannot_access_private_notebook_rows(
    app_module, client, student_token
):
    seeded = seed_notebook(app_module)
    with app_module.app.app_context():
        suffix = uuid.uuid4().hex[:8]
        other = app_module.User(
            username=f"notebook-other-{suffix}",
            email=f"notebook-other-{suffix}@example.test",
            password_hash=app_module.generate_password_hash(
                "Other1234", method="pbkdf2:sha256"
            ),
            role="student",
            is_verified=True,
            created_at=app_module.current_time_text(),
        )
        reviewer = app_module.User(
            username=f"notebook-reviewer-{suffix}",
            email=f"notebook-reviewer-{suffix}@example.test",
            password_hash=app_module.generate_password_hash(
                "Reviewer1234", method="pbkdf2:sha256"
            ),
            role="reviewer",
            is_verified=True,
            created_at=app_module.current_time_text(),
        )
        app_module.db.session.add_all([other, reviewer])
        app_module.db.session.commit()
        other_email, reviewer_email = other.email, reviewer.email
    other_token = client.post(
        "/api/auth/login", json={"email": other_email, "password": "Other1234"}
    ).get_json()["token"]
    reviewer_token = client.post(
        "/api/auth/login",
        json={"email": reviewer_email, "password": "Reviewer1234"},
    ).get_json()["token"]
    other_list = client.get(
        f"/api/student/personal-concept-notebook?view=HISTORY&q={seeded['marker']}",
        headers=auth(other_token),
    )
    assert other_list.status_code == 200
    assert other_list.get_json()["data"]["items"] == []
    query_uid = seeded["items"][0]["query_uid"]
    assert client.get(
        f"/api/student/personal-concept-notebook/{query_uid}",
        headers=auth(other_token),
    ).status_code == 404
    assert client.get(
        "/api/student/personal-concept-notebook", headers=auth(reviewer_token)
    ).status_code == 403
