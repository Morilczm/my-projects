def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def create_card_for_audit_api(client, token, headers_extra=None, **overrides):
    payload = {
        "english_term": "Audit API Term",
        "chinese_term": "审计接口术语",
        "course": "Audit API Course",
        "chapter": "Observable Events",
        "status": "needs_review",
        "confidence_score": 0.79,
        "risk_labels": ["api_review"],
        "english_evidence": [{
            "source": "Audit API Notes",
            "page": 9,
            "text": "Observable behavior can be recorded without internal model reasoning.",
            "chunk_id": 909,
            "score": 0.86,
        }],
    }
    payload.update(overrides)
    headers = bearer(token)
    headers.update(headers_extra or {})
    response = client.post("/api/concept-cards", json=payload, headers=headers)
    assert response.status_code == 200, response.get_data(as_text=True)
    assert response.get_json()["request_id"]
    return response.get_json()["data"]["card"]


def test_api_list_audit_records_returns_list(client, teacher_token):
    card = create_card_for_audit_api(client, teacher_token, english_term="Audit API List Term")

    response = client.get(f"/api/audit-records?target_uid={card['card_uid']}", headers=bearer(teacher_token))

    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert payload["pagination"]["total"] >= 1
    assert payload["items"][0]["target_uid"] == card["card_uid"]


def test_api_filter_audit_records_by_target_uid_and_event_type(client, teacher_token):
    create_request_id = "audit-api-filter-create-request-id"
    update_request_id = "audit-api-filter-update-request-id"
    card = create_card_for_audit_api(
        client,
        teacher_token,
        headers_extra={"X-Request-ID": create_request_id},
        english_term="Audit API Filter Term",
    )
    client.patch(
        f"/api/concept-cards/{card['card_uid']}",
        json={"expected_version": card["review_token"], "chinese_term": "筛选后的审计接口术语"},
        headers={**bearer(teacher_token), "X-Request-ID": update_request_id},
    )

    by_target = client.get(
        f"/api/audit-records?target_uid={card['card_uid']}&per_page=20",
        headers=bearer(teacher_token),
    )
    by_event = client.get(
        f"/api/audit-records?target_uid={card['card_uid']}&event_type=concept_card_updated&result=success",
        headers=bearer(teacher_token),
    )
    by_request = client.get(
        f"/api/audit-records?request_id={update_request_id}",
        headers=bearer(teacher_token),
    )

    assert by_target.status_code == 200
    assert by_target.get_json()["request_id"]
    assert by_target.get_json()["data"]["pagination"]["total"] == 2
    assert by_event.status_code == 200
    items = by_event.get_json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["request_id"] == update_request_id
    assert items[0]["changed_fields"]
    assert items[0]["before_snapshot"]["chinese_term"] == "审计接口术语"
    assert items[0]["after_snapshot"]["chinese_term"] == "筛选后的审计接口术语"
    assert by_request.status_code == 200
    assert by_request.get_json()["data"]["items"][0]["request_id"] == update_request_id


def test_api_get_single_audit_record(client, teacher_token):
    request_id = "audit-api-detail-request-id"
    card = create_card_for_audit_api(
        client,
        teacher_token,
        headers_extra={"X-Request-ID": request_id},
        english_term="Audit API Detail Term",
    )
    list_response = client.get(
        f"/api/audit-records?target_uid={card['card_uid']}&event_type=concept_card_created",
        headers=bearer(teacher_token),
    )
    audit_uid = list_response.get_json()["data"]["items"][0]["audit_uid"]

    response = client.get(f"/api/audit-records/{audit_uid}", headers=bearer(teacher_token))

    assert response.status_code == 200
    assert response.get_json()["request_id"]
    record = response.get_json()["data"]["audit_record"]
    assert record["audit_uid"] == audit_uid
    assert record["event_type"] == "concept_card_created"
    assert record["target_uid"] == card["card_uid"]
    assert record["request_id"] == request_id


def test_api_get_missing_audit_record_returns_json_error(client, teacher_token):
    request_id = "audit-api-missing-request-id"
    response = client.get(
        "/api/audit-records/not-a-real-audit-uid",
        headers={**bearer(teacher_token), "X-Request-ID": request_id},
    )

    assert response.status_code == 404
    assert response.get_json()["status"] == "error"
    assert response.get_json()["request_id"] == request_id
    assert response.get_json()["error_code"] == "RESOURCE_NOT_FOUND"


def test_api_audit_records_requires_authentication(client):
    response = client.get("/api/audit-records", headers={"X-Request-ID": "audit-api-auth-required-request-id"})

    assert response.status_code == 401
    assert response.get_json()["status"] == "error"
    assert response.get_json()["request_id"] == "audit-api-auth-required-request-id"
    assert response.get_json()["error_code"] == "AUTH_REQUIRED"


def test_api_audit_record_payload_does_not_store_sensitive_headers(client, teacher_token):
    request_id = "audit-api-sensitive-header-request-id"
    card = create_card_for_audit_api(
        client,
        teacher_token,
        headers_extra={"X-Request-ID": request_id, "Cookie": "session=should-not-be-stored"},
        english_term="Audit API Sensitive Header Term",
    )
    response = client.get(
        f"/api/audit-records?target_uid={card['card_uid']}&request_id={request_id}",
        headers=bearer(teacher_token),
    )

    assert response.status_code == 200
    record_text = str(response.get_json()["data"]["items"][0])
    assert "should-not-be-stored" not in record_text
    assert "Bearer " not in record_text
