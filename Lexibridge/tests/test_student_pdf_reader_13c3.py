import json
import uuid
from types import SimpleNamespace

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def pdf_bytes(path):
    pdf = canvas.Canvas(str(path), pagesize=letter)
    pdf.drawString(72, 720, "Electric potential")
    pdf.drawString(72, 690, "Electric potential is potential energy per unit charge.")
    pdf.showPage()
    pdf.drawString(72, 720, "Electric field")
    pdf.drawString(72, 690, "Electric field is force per unit charge.")
    pdf.save()
    return path.read_bytes()


def seed_reader_source(
    app_module,
    tmp_path,
    *,
    scope="personal",
    owner_id=None,
    course_id=None,
    with_file=True,
    complete_provenance=True,
):
    suffix = uuid.uuid4().hex[:10]
    student = app_module.User.query.filter_by(
        email="student.test@lexibridge.local"
    ).one()
    owner_id = student.id if owner_id is None else owner_id
    storage = {}
    if with_file:
        source_path = tmp_path / f"reader-{suffix}.pdf"
        pdf_bytes(source_path)
        storage = app_module.storage_service().save_file(
            str(source_path),
            purpose="uploaded_document",
            owner_user_id=owner_id,
            course_id=course_id,
            original_filename=f"reader-{suffix}.pdf",
        )
    parse_uid = f"parse-reader-{suffix}"
    document = app_module.Document(
        owner_user_id=owner_id,
        course_id=course_id,
        scope_type=scope,
        filename=f"reader-{suffix}.pdf",
        original_filename=f"reader-{suffix}.pdf",
        file_type="pdf",
        content_type="application/pdf",
        size_bytes=int(storage.get("size_bytes") or 0),
        sha256=str(storage.get("sha256") or ""),
        storage_backend=str(storage.get("storage_backend") or ""),
        storage_key=str(storage.get("storage_key") or ""),
        language="en",
        parsing_status="parsed",
        parse_uid=parse_uid,
        deleted_at="",
    )
    parse = app_module.DocumentParseRecord(
        parse_uid=parse_uid,
        source_filename=document.filename,
        file_type="pdf",
        mime_type="application/pdf",
        parser_name="pymupdf_native",
        parser_version="parse_quality_v1",
        parse_status="parsed",
        quality_status="native_text_ok",
        page_count=2,
        block_count=2,
    )
    app_module.db.session.add_all([document, parse])
    app_module.db.session.flush()
    source = app_module.KnowledgeSource(
        source_uid=f"reader-source-{suffix}",
        name="Reader fixture",
        title="Reader fixture",
        language="en",
        scope_type=scope,
        owner_user_id=owner_id,
        course_id=course_id,
        document_id=document.id,
        visibility="private" if scope == "personal" else "course",
        status="active",
        version=1,
        authorization_status="authorized",
        license_status="licensed",
        allow_student_search=True,
        source_role="english_course_material",
        parse_uid=parse_uid,
        file_type="pdf",
    )
    app_module.db.session.add(source)
    app_module.db.session.flush()
    texts = (
        "Electric potential is potential energy per unit charge.",
        "Electric field is force per unit charge.",
    )
    chunks = []
    for index, text in enumerate(texts, start=1):
        chunk = app_module.KnowledgeChunk(
            chunk_uid=f"reader-chunk-{suffix}-{index}",
            source_uid=source.source_uid,
            document_id=document.id,
            course_id=course_id,
            scope_type=scope,
            owner_user_id=str(owner_id),
            visibility=source.visibility,
            content=text,
            normalized_text=text.casefold(),
            content_hash=app_module.hashlib.sha256(text.encode()).hexdigest(),
            chunk_index=index - 1,
            language="en",
            status="active",
            is_active=True,
            page_number=index if complete_provenance else None,
            parse_block_uid=f"reader-block-{suffix}-{index}" if complete_provenance else "",
            source_section="Electrostatics",
            block_type="paragraph",
            quality_status="qualified",
        )
        chunks.append(chunk)
    app_module.db.session.add_all(chunks)
    app_module.db.session.commit()
    return student, source, document, chunks


def create_user_and_token(app_module, client, *, role, suffix):
    email = f"reader-{role}-{suffix}@lexibridge.local"
    password = "Reader1234"
    with app_module.app.app_context():
        user = app_module.User(
            username=f"reader_{role}_{suffix}",
            email=email,
            password_hash=app_module.generate_password_hash(
                password, method="pbkdf2:sha256"
            ),
            role=role,
            is_verified=True,
            created_at=app_module.current_time_text(),
        )
        app_module.db.session.add(user)
        app_module.db.session.commit()
        user_id = user.id
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return user_id, response.get_json()["token"]


def fake_ready_workflow(**kwargs):
    chinese_uid = kwargs["allowed_source_uids"][0]
    return SimpleNamespace(
        english_term=kwargs["english_term"],
        english_evidence_candidates=[{
            "source_uid": kwargs["english_source_uid"],
            "chunk_uid": "reader-english-evidence",
            "snippet": kwargs["english_context"],
            "page_number": 1,
        }],
        chinese_evidence_candidates=[{
            "source_uid": chinese_uid,
            "chunk_uid": "reader-chinese-evidence",
            "snippet": "电势表示单位电荷的电势能。",
            "page_number": 1,
        }],
        chinese_term_candidates=[{
            "candidate_uid": "reader-potential",
            "chinese_term": "电势",
            "source_uid": chinese_uid,
            "chunk_uid": "reader-chinese-evidence",
        }],
        selected_chinese_candidate={
            "candidate_uid": "reader-potential",
            "chinese_term": "电势",
            "source_uid": chinese_uid,
            "chunk_uid": "reader-chinese-evidence",
        },
        evidence_qualification={"decision": "QUALIFIED"},
        risk_labels=[],
    )


def test_personal_pdf_reader_returns_page_aware_selectable_provenance_and_file(
    app_module, client, student_token, tmp_path
):
    with app_module.app.app_context():
        _, source, _, chunks = seed_reader_source(app_module, tmp_path)
        source_uid = source.source_uid
        expected_chunk_uid = chunks[0].chunk_uid

    response = client.get(
        f"/api/student/concept-materials/{source_uid}/reader?page=1",
        headers=auth(student_token),
    )
    assert response.status_code == 200
    reader = response.get_json()["data"]["reader"]
    assert reader["contract_id"] == "student-material-reader@1.0.0"
    assert reader["source"]["workspace_scope"] == "PERSONAL"
    assert reader["source"]["file_type"] == "pdf"
    assert reader["source"]["file_available"] is True
    assert reader["page"] == {
        "number": 1,
        "page_count": 2,
        "available_pages": [1, 2],
        "previous_page": None,
        "next_page": 2,
        "block_count": 1,
    }
    assert reader["items"][0]["chunk_uid"] == expected_chunk_uid
    assert reader["items"][0]["page_number"] == 1
    assert reader["items"][0]["block_uid"]
    assert reader["items"][0]["heading_path"] == "Electrostatics"
    assert len(reader["items"][0]["content_hash"]) == 64
    assert reader["items"][0]["span_start"] == 0
    assert reader["items"][0]["span_end"] == len(reader["items"][0]["text"])
    assert reader["items"][0]["selectable"] is True
    serialized = json.dumps(reader)
    assert "storage_key" not in serialized
    assert str(tmp_path) not in serialized

    file_response = client.get(
        f"/api/student/concept-materials/{source_uid}/file",
        headers=auth(student_token),
    )
    assert file_response.status_code == 200
    assert file_response.mimetype == "application/pdf"
    assert file_response.data.startswith(b"%PDF")
    assert "inline" in file_response.headers["Content-Disposition"]
    assert file_response.headers["Cache-Control"] == "private, no-store"
    assert file_response.headers["X-Content-Type-Options"] == "nosniff"


def test_reader_keeps_governed_text_when_original_pdf_is_unavailable(
    app_module, client, student_token, tmp_path
):
    with app_module.app.app_context():
        _, source, _, _ = seed_reader_source(
            app_module, tmp_path, with_file=False
        )
        source_uid = source.source_uid

    response = client.get(
        f"/api/student/concept-materials/{source_uid}/reader?page=1",
        headers=auth(student_token),
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["reader"]["source"]["file_available"] is False
    assert response.get_json()["data"]["reader"]["items"]

    file_response = client.get(
        f"/api/student/concept-materials/{source_uid}/file",
        headers=auth(student_token),
    )
    assert file_response.status_code == 404
    assert file_response.get_json()["error_code"] == "STUDENT_MATERIAL_FILE_NOT_AVAILABLE"


def test_reader_access_is_student_owned_and_non_student_roles_are_denied(
    app_module, client, student_token, teacher_token, tmp_path
):
    with app_module.app.app_context():
        _, source, _, _ = seed_reader_source(app_module, tmp_path)
        source_uid = source.source_uid
    _, other_token = create_user_and_token(
        app_module, client, role="student", suffix=uuid.uuid4().hex[:6]
    )
    _, reviewer_token = create_user_and_token(
        app_module, client, role="reviewer", suffix=uuid.uuid4().hex[:6]
    )
    for token, expected in (
        (other_token, 404),
        (teacher_token, 403),
        (reviewer_token, 403),
    ):
        reader = client.get(
            f"/api/student/concept-materials/{source_uid}/reader?page=1",
            headers=auth(token),
        )
        file_response = client.get(
            f"/api/student/concept-materials/{source_uid}/file",
            headers=auth(token),
        )
        assert reader.status_code == expected
        assert file_response.status_code == expected


def test_managed_course_and_personal_use_the_same_reader_contract(
    app_module, client, student_token, tmp_path
):
    with app_module.app.app_context():
        student = app_module.User.query.filter_by(
            email="student.test@lexibridge.local"
        ).one()
        course = app_module.Course(
            name=f"Reader course {uuid.uuid4().hex[:6]}",
            status="active",
            created_at=app_module.current_time_text(),
        )
        app_module.db.session.add(course)
        app_module.db.session.flush()
        app_module.db.session.add(
            app_module.CourseMember(
                course_id=course.id,
                user_id=student.id,
                role="student",
                role_in_course="student",
                status="active",
                created_at=app_module.current_time_text(),
                joined_at=app_module.current_time_text(),
            )
        )
        _, source, _, _ = seed_reader_source(
            app_module,
            tmp_path,
            scope="course",
            owner_id=999999,
            course_id=course.id,
        )
        source.visibility = "course"
        app_module.db.session.commit()
        source_uid = source.source_uid
        course_id = course.id

    response = client.get(
        f"/api/student/concept-materials/{source_uid}/reader?page=2",
        headers=auth(student_token),
    )
    assert response.status_code == 200
    reader = response.get_json()["data"]["reader"]
    assert reader["contract_id"] == "student-material-reader@1.0.0"
    assert reader["source"]["workspace_scope"] == "MANAGED_COURSE"
    assert reader["source"]["workspace_uid"] == f"course:{course_id}"
    assert reader["page"]["number"] == 2
    assert {item["page_number"] for item in reader["items"]} == {2}


def test_reader_selection_roundtrips_through_existing_concept_query(
    app_module, client, student_token, tmp_path
):
    with app_module.app.app_context():
        student, source, _, _ = seed_reader_source(app_module, tmp_path)
        chinese = app_module.KnowledgeSource(
            source_uid=f"reader-zh-{uuid.uuid4().hex[:8]}",
            name="Reader Chinese evidence",
            language="zh",
            scope_type="personal",
            owner_user_id=student.id,
            visibility="private",
            status="active",
            authorization_status="authorized",
            license_status="licensed",
            allow_student_search=True,
            source_role="chinese_reference_material",
        )
        app_module.db.session.add(chinese)
        app_module.db.session.commit()
        source_uid = source.source_uid
    previous = app_module.app.config.get("STUDENT_ALIGNMENT_RUNNER")
    app_module.app.config["STUDENT_ALIGNMENT_RUNNER"] = fake_ready_workflow
    try:
        reader_response = client.get(
            f"/api/student/concept-materials/{source_uid}/reader?page=1",
            headers=auth(student_token),
        )
        item = reader_response.get_json()["data"]["reader"]["items"][0]
        start = item["text"].index("Electric potential")
        payload = {
            "workspace_scope": "PERSONAL",
            "source_uid": source_uid,
            "chunk_uid": item["chunk_uid"],
            "selected_text": "Electric potential",
            "selection_start": start,
            "selection_end": start + len("Electric potential"),
        }
        result = client.post(
            "/api/student/concept-queries",
            json=payload,
            headers={**auth(student_token), "Idempotency-Key": f"reader-{uuid.uuid4()}"},
        )
        assert result.status_code == 200
        query = result.get_json()["data"]["query"]
        assert query["alignment_status"] == "READY"
        assert query["source_uid"] == source_uid
        assert query["recommended_chinese_concept"]["text"] == "电势"
        assert query["visibility"] == "PRIVATE"
        assert query["authority"] == "NON_OFFICIAL"
    finally:
        if previous is None:
            app_module.app.config.pop("STUDENT_ALIGNMENT_RUNNER", None)
        else:
            app_module.app.config["STUDENT_ALIGNMENT_RUNNER"] = previous


def test_reader_fails_closed_for_invalid_page_and_missing_provenance(
    app_module, client, student_token, tmp_path
):
    with app_module.app.app_context():
        _, source, _, _ = seed_reader_source(
            app_module, tmp_path, complete_provenance=False
        )
        source_uid = source.source_uid
    invalid = client.get(
        f"/api/student/concept-materials/{source_uid}/reader?page=0",
        headers=auth(student_token),
    )
    assert invalid.status_code == 400
    assert invalid.get_json()["error_code"] == "STUDENT_MATERIAL_READER_PAGE_INVALID"

    missing = client.get(
        f"/api/student/concept-materials/{source_uid}/reader?page=1",
        headers=auth(student_token),
    )
    assert missing.status_code == 409
    assert (
        missing.get_json()["error_code"]
        == "STUDENT_MATERIAL_READER_PROVENANCE_INCOMPLETE"
    )
