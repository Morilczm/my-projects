def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def api_evidence(score=0.87):
    return [{
        "source": "API Signal Processing Notes",
        "page": 3,
        "text": "Sampling theorem links continuous and discrete signal representations.",
        "chunk_id": 33,
        "score": score,
    }]


def create_api_card(client, token, headers_extra=None, **overrides):
    payload = {
        "english_term": "Sampling Theorem",
        "chinese_term": "采样定理",
        "course": "API Signal Processing",
        "chapter": "Sampling",
        "status": "needs_review",
        "confidence_score": 0.82,
        "risk_labels": ["needs_teacher_review"],
        "english_evidence": api_evidence(),
    }
    payload.update(overrides)
    headers = bearer(token)
    headers.update(headers_extra or {})
    response = client.post("/api/concept-cards", json=payload, headers=headers)
    assert response.status_code == 200, response.get_data(as_text=True)
    assert response.get_json()["request_id"]
    return response.get_json()["data"]["card"]


def audit_items_for_request(client, token, request_id):
    response = client.get(f"/api/audit-records?request_id={request_id}&per_page=20", headers=bearer(token))
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()["data"]["items"]


def test_api_create_concept_card_success(client, teacher_token):
    request_id = "api-create-success-request-id"
    card = create_api_card(
        client,
        teacher_token,
        headers_extra={"X-Request-ID": request_id},
        english_term="API Create Term",
    )

    assert card["card_uid"]
    assert card["english_term"] == "API Create Term"
    assert card["risk_labels"] == ["needs_teacher_review"]
    assert card["english_evidence"][0]["chunk_id"] == 33
    records = audit_items_for_request(client, teacher_token, request_id)
    assert records[0]["event_type"] == "concept_card_created"
    assert records[0]["request_id"] == request_id


def test_api_create_concept_card_with_partial_text_risk_forces_review(client, teacher_token):
    request_id = "api-create-partial-quality-request-id"
    card = create_api_card(
        client,
        teacher_token,
        headers_extra={"X-Request-ID": request_id},
        english_term="API Partial Quality Term",
        status="draft",
        parse_uid="api-parse-partial",
        parse_quality_status="partial_text",
        parse_quality_flags=["partial_text"],
        risk_labels=["teacher_check"],
        confidence_score=0.93,
    )

    assert card["status"] == "draft"
    assert card["confidence_score"] == 0.79
    assert card["parse_uid"] == "api-parse-partial"
    assert card["parse_quality_status"] == "partial_text"
    assert card["risk_labels"] == ["teacher_check", "input_partial_text"]
    assert card["input_risk_labels"] == ["input_partial_text"]


def test_api_create_concept_card_with_risk_rejects_approved(client, teacher_token):
    request_id = "api-create-risky-approved-request-id"
    response = client.post(
        "/api/concept-cards",
        json={
            "english_term": "API Risky Approved",
            "course": "API Signal Processing",
            "status": "approved",
            "english_evidence": api_evidence(),
            "parse_uid": "api-parse-risky-approved",
            "parse_quality_status": "partial_text",
            "parse_quality_flags": ["partial_text"],
        },
        headers={**bearer(teacher_token), "X-Request-ID": request_id},
    )

    assert response.status_code == 400
    assert response.get_json()["request_id"] == request_id
    assert response.get_json()["audit_error_code"] == "concept_card_quality_gate_blocked"
    records = audit_items_for_request(client, teacher_token, request_id)
    assert any(record["event_type"] == "concept_card_quality_gate_blocked" for record in records)


def test_api_create_missing_required_fields_returns_error(client, teacher_token):
    missing_english_request_id = "api-missing-english-request-id"
    missing_course_request_id = "api-missing-course-request-id"
    missing_english = client.post(
        "/api/concept-cards",
        json={"course": "API Signal Processing"},
        headers={**bearer(teacher_token), "X-Request-ID": missing_english_request_id},
    )
    missing_course = client.post(
        "/api/concept-cards",
        json={"english_term": "Sampling Theorem"},
        headers={**bearer(teacher_token), "X-Request-ID": missing_course_request_id},
    )

    assert missing_english.status_code == 400
    assert missing_english.get_json()["status"] == "error"
    assert missing_english.get_json()["request_id"] == missing_english_request_id
    assert "english_term" in missing_english.get_json()["message"]
    assert missing_course.status_code == 400
    assert missing_course.get_json()["request_id"] == missing_course_request_id
    assert "course" in missing_course.get_json()["message"]
    english_audits = audit_items_for_request(client, teacher_token, missing_english_request_id)
    course_audits = audit_items_for_request(client, teacher_token, missing_course_request_id)
    assert english_audits[0]["error_code"] == "missing_english_term"
    assert course_audits[0]["error_code"] == "missing_course"


def test_api_list_concept_cards_and_filter_by_course_status_and_query(client, teacher_token):
    create_api_card(client, teacher_token, english_term="API Unique Spectral Term", course="API Course A", status="draft")
    create_api_card(client, teacher_token, english_term="API Z Transform", course="API Course A", status="approved")
    create_api_card(client, teacher_token, english_term="API Hash Table", course="API Course B", status="draft")

    all_cards = client.get("/api/concept-cards?per_page=50", headers=bearer(teacher_token))
    by_course = client.get("/api/concept-cards?course=API%20Course%20A&per_page=50", headers=bearer(teacher_token))
    by_status = client.get("/api/concept-cards?status=draft&per_page=50", headers=bearer(teacher_token))
    by_query = client.get("/api/concept-cards?q=Unique%20Spectral&per_page=50", headers=bearer(teacher_token))

    assert all_cards.status_code == 200
    assert len(all_cards.get_json()["data"]["items"]) >= 3
    assert {item["course"] for item in by_course.get_json()["data"]["items"]} == {"API Course A"}
    assert all(item["status"] == "draft" for item in by_status.get_json()["data"]["items"])
    assert [item["english_term"] for item in by_query.get_json()["data"]["items"]] == ["API Unique Spectral Term"]


def test_api_get_single_concept_card(client, teacher_token):
    card = create_api_card(client, teacher_token, english_term="API Detail Term")

    response = client.get(f"/api/concept-cards/{card['card_uid']}", headers=bearer(teacher_token))

    assert response.status_code == 200
    assert response.get_json()["request_id"]
    assert response.get_json()["data"]["card"]["english_term"] == "API Detail Term"


def test_api_get_missing_concept_card_writes_failure_audit(client, teacher_token):
    request_id = "api-get-missing-request-id"
    response = client.get(
        "/api/concept-cards/not-a-real-card-uid",
        headers={**bearer(teacher_token), "X-Request-ID": request_id},
    )

    assert response.status_code == 404
    assert response.get_json()["request_id"] == request_id
    records = audit_items_for_request(client, teacher_token, request_id)
    assert len(records) == 1
    assert records[0]["event_type"] == "concept_card_operation_failed"
    assert records[0]["error_code"] == "concept_card_not_found"


def test_api_patch_concept_card_updates_allowed_fields(client, teacher_token):
    card = create_api_card(client, teacher_token, english_term="API Patch Original")
    request_id = "api-patch-success-request-id"
    response = client.patch(
        f"/api/concept-cards/{card['card_uid']}",
        json={
            "expected_version": card["review_token"],
            "english_term": "API Patch Updated",
            "risk_labels": ["patched"],
        },
        headers={**bearer(teacher_token), "X-Request-ID": request_id},
    )

    assert response.status_code == 200, response.get_data(as_text=True)
    assert response.get_json()["request_id"] == request_id
    updated = response.get_json()["data"]["card"]
    assert updated["id"] == card["id"]
    assert updated["card_uid"] == card["card_uid"]
    assert updated["english_term"] == "API Patch Updated"
    assert updated["version"] == card["version"] + 1
    assert updated["risk_labels"] == ["patched"]
    records = audit_items_for_request(client, teacher_token, request_id)
    assert records[0]["event_type"] == "concept_card_updated"


def test_api_patch_illegal_field_returns_error_and_audit(client, teacher_token):
    card = create_api_card(client, teacher_token, english_term="API Patch Illegal Field")
    request_id = "api-patch-illegal-field-request-id"
    response = client.patch(
        f"/api/concept-cards/{card['card_uid']}",
        json={"id": 999999, "english_term": "Should Not Apply"},
        headers={**bearer(teacher_token), "X-Request-ID": request_id},
    )

    assert response.status_code == 400
    assert response.get_json()["request_id"] == request_id
    assert response.get_json()["audit_error_code"] == "invalid_patch_field"
    records = audit_items_for_request(client, teacher_token, request_id)
    assert records[0]["error_code"] == "invalid_patch_field"
    assert records[0]["target_uid"] == card["card_uid"]


def test_api_patch_invalid_confidence_returns_error(client, teacher_token):
    card = create_api_card(client, teacher_token, english_term="API Bad Confidence")
    request_id = "api-bad-confidence-request-id"
    response = client.patch(
        f"/api/concept-cards/{card['card_uid']}",
        json={"expected_version": card["review_token"], "confidence_score": 1.5},
        headers={**bearer(teacher_token), "X-Request-ID": request_id},
    )

    assert response.status_code == 400
    assert response.get_json()["status"] == "error"
    assert response.get_json()["request_id"] == request_id
    assert "confidence_score" in response.get_json()["message"]
    records = audit_items_for_request(client, teacher_token, request_id)
    assert records[0]["error_code"] == "invalid_confidence_score"


def test_api_status_invalid_returns_error_and_audit(client, teacher_token):
    card = create_api_card(client, teacher_token, english_term="API Invalid Status")
    request_id = "api-invalid-status-request-id"
    response = client.post(
        f"/api/concept-cards/{card['card_uid']}/status",
        json={"status": "not_a_status"},
        headers={**bearer(teacher_token), "X-Request-ID": request_id},
    )

    assert response.status_code == 400
    assert response.get_json()["request_id"] == request_id
    records = audit_items_for_request(client, teacher_token, request_id)
    assert records[0]["error_code"] == "invalid_status"


def test_api_status_change_success_and_approved_without_evidence_error(client, teacher_token):
    with_evidence = create_api_card(
        client,
        teacher_token,
        english_term="API Approve With Evidence",
        status="needs_review",
    )
    approve_request_id = "api-approve-success-request-id"
    approved = client.post(
        f"/api/concept-cards/{with_evidence['card_uid']}/status",
        json={"status": "approved"},
        headers={**bearer(teacher_token), "X-Request-ID": approve_request_id},
    )
    assert approved.status_code == 200, approved.get_data(as_text=True)
    assert approved.get_json()["request_id"] == approve_request_id
    assert approved.get_json()["data"]["card"]["status"] == "approved"
    assert approved.get_json()["data"]["card"]["reviewed_by"] is not None
    approve_audits = audit_items_for_request(client, teacher_token, approve_request_id)
    assert approve_audits[0]["event_type"] == "concept_card_status_changed"


def test_api_patch_risky_card_to_approved_returns_error(client, teacher_token):
    card = create_api_card(
        client,
        teacher_token,
        english_term="API Risky Patch Approval",
        status="needs_review",
        parse_quality_status="mixed_quality",
        parse_quality_flags=["mixed_quality"],
    )
    request_id = "api-patch-risky-approved-request-id"
    response = client.patch(
        f"/api/concept-cards/{card['card_uid']}",
        json={"expected_version": card["review_token"], "status": "approved"},
        headers={**bearer(teacher_token), "X-Request-ID": request_id},
    )

    assert response.status_code == 400
    assert response.get_json()["request_id"] == request_id
    assert response.get_json()["audit_error_code"] == "concept_card_quality_gate_blocked"
    records = audit_items_for_request(client, teacher_token, request_id)
    assert any(record["event_type"] == "concept_card_quality_gate_blocked" for record in records)

    no_evidence = create_api_card(
        client,
        teacher_token,
        english_term="API Approve Without Evidence",
        english_evidence=[],
        chinese_evidence=[],
        status="draft",
    )
    rejected_request_id = "api-approve-without-evidence-request-id"
    rejected = client.post(
        f"/api/concept-cards/{no_evidence['card_uid']}/status",
        json={"status": "approved"},
        headers={**bearer(teacher_token), "X-Request-ID": rejected_request_id},
    )
    assert rejected.status_code == 400
    assert rejected.get_json()["request_id"] == rejected_request_id
    assert "requires English or Chinese evidence" in rejected.get_json()["message"]
    rejected_audits = audit_items_for_request(client, teacher_token, rejected_request_id)
    assert rejected_audits[0]["error_code"] == "evidence_required_for_approved"
