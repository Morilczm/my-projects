import uuid

from test_concept_card_publication_integrity import _card, _source_and_chunk
from test_concept_card_review import bearer, grant_review_access
from test_student_concept_cards import grant_student_course_access


def _unique(prefix):
    return f"{prefix} {uuid.uuid4().hex[:10]}"


def test_review_and_student_apis_return_source_chunk_and_location_provenance(
    client,
    app_module,
    teacher_token,
    student_token,
):
    course = _unique("11D Provenance Course")
    with app_module.app.app_context():
        grant_review_access(app_module, course=course, permission_level="admin")
        en_source, en_chunk = _source_and_chunk(app_module, course=course, language="en", page_number=7)
        zh_source, zh_chunk = _source_and_chunk(app_module, course=course, language="zh", page_number=8)
        card = _card(
            app_module,
            course=course,
            status="approved",
            en_source=en_source,
            en_chunk=en_chunk,
            zh_source=zh_source,
            zh_chunk=zh_chunk,
        )
        # BBox is not a KnowledgeChunk column. When genuine geometry exists in
        # upstream evidence, publication APIs should preserve it without
        # inventing geometry for sources that do not provide one.
        english = card.get_english_evidence()
        english[0]["bbox"] = {
            "x0": 10,
            "y0": 20,
            "x1": 150,
            "y1": 60,
            "coordinate_origin": "top-left",
        }
        english[0]["parser"] = "native_pdf_text"
        card.set_english_evidence(english)
        app_module.db.session.commit()
        student = app_module.User.query.filter_by(role="student").first()
        grant_student_course_access(app_module, course, user=student)
        card_uid = card.card_uid

    queue = client.get(
        f"/api/concept-cards/review-queue?course={course}&status=approved&per_page=20",
        headers=bearer(teacher_token),
    )
    assert queue.status_code == 200, queue.get_data(as_text=True)
    review_card = queue.get_json()["data"]["items"][0]
    assert review_card["review_token"] == str(review_card["version"])
    en_evidence = review_card["english_evidence"][0]
    zh_evidence = review_card["chinese_evidence"][0]

    assert en_evidence["source_uid"]
    assert en_evidence["chunk_uid"]
    assert en_evidence["page_number"] == 7
    assert en_evidence["bbox"]["coordinate_origin"] == "top-left"
    assert en_evidence["bbox_available"] is True
    assert en_evidence["location_available"] is True
    assert en_evidence["block_type"] == "paragraph"
    assert en_evidence["parser"] == "native_pdf_text"
    assert en_evidence["source_status"] == "active"
    assert en_evidence["source_available"] is True

    assert zh_evidence["source_uid"]
    assert zh_evidence["chunk_uid"]
    assert zh_evidence["page_number"] == 8
    assert zh_evidence["bbox"] is None
    assert zh_evidence["bbox_available"] is False
    assert zh_evidence["location_available"] is True
    assert zh_evidence["block_type"] == "paragraph"
    assert zh_evidence["source_status"] == "active"

    student_detail = client.get(f"/api/student/concept-cards/{card_uid}", headers=bearer(student_token))
    assert student_detail.status_code == 200, student_detail.get_data(as_text=True)
    student_card = student_detail.get_json()["data"]["card"]
    assert student_card["english_evidence"][0]["source_uid"] == en_evidence["source_uid"]
    assert student_card["english_evidence"][0]["page_number"] == 7
    assert student_card["english_evidence"][0]["bbox_available"] is True
    assert student_card["chinese_evidence"][0]["language"] == "zh"
    assert student_card["chinese_evidence"][0]["bbox_available"] is False


def test_source_status_patch_deprecates_source_without_fabricating_geometry(client, app_module, admin_token):
    course = _unique("11D Source Patch Course")
    with app_module.app.app_context():
        source, chunk = _source_and_chunk(app_module, course=course, language="en", page_number=3)
        source_uid = source.source_uid
        chunk_uid = chunk.chunk_uid
        app_module.db.session.commit()

    response = client.patch(
        f"/api/knowledge-sources/{source_uid}",
        json={"status": "deprecated"},
        headers={**bearer(admin_token), "X-Request-ID": "11d-source-deprecate"},
    )
    assert response.status_code == 200, response.get_data(as_text=True)
    payload = response.get_json()["data"]["source"]
    assert payload["source_uid"] == source_uid
    assert payload["status"] == "deprecated"

    chunk_response = client.get(f"/api/knowledge-chunks/{chunk_uid}", headers=bearer(admin_token))
    assert chunk_response.status_code == 200
    chunk_payload = chunk_response.get_json()["data"]["chunk"]
    assert chunk_payload["page_number"] == 3
    assert "bbox" not in chunk_payload
