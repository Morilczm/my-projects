import io

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def pdf_bytes():
    buffer = io.BytesIO()
    document = canvas.Canvas(buffer, pagesize=letter)
    document.drawString(72, 720, "Electric charge")
    document.drawString(
        72,
        690,
        "Electric charge is a conserved property of matter measured in coulombs.",
    )
    document.save()
    return buffer.getvalue()


def test_personal_upload_is_pdf_only(client, student_token):
    response = client.post(
        "/api/documents/upload",
        headers=auth(student_token),
        data={
            "scope_type": "personal",
            "language": "en",
            "personal_workspace_contract": "13C",
            "file": (io.BytesIO(b"not a document"), "notes.txt"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 415
    assert response.get_json()["error_code"] == "PERSONAL_MATERIAL_PDF_REQUIRED"


def test_personal_pdf_reuses_governed_ingestion_and_private_index(
    client, app_module, student_token
):
    response = client.post(
        "/api/documents/upload",
        headers=auth(student_token),
        data={
            "scope_type": "personal",
            "language": "en",
            "source_type": "student_upload",
            "file": (io.BytesIO(pdf_bytes()), "physics-notes.pdf"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    data = response.get_json()["data"]
    with app_module.app.app_context():
        app_module.run_background_job(data["job_id"], worker_id="pytest-13c")
        document = app_module.db.session.get(app_module.Document, data["document_id"])
        source = app_module.KnowledgeSource.query.filter_by(
            document_id=document.id
        ).first()
        chunks = app_module.KnowledgeChunk.query.filter_by(
            source_uid=source.source_uid
        ).all()
        assert document.scope_type == "personal"
        assert document.parsing_status in {"parsed", "parsed_with_warnings"}
        assert source.knowledge_base_type == "student_personal_kb"
        assert source.visibility == "private"
        assert source.authorization_status == "allowed_for_private_use"
        assert source.allow_student_search is True
        assert source.allow_derivative_cards is False
        assert chunks
        assert all(chunk.parse_uid and chunk.parse_block_uid for chunk in chunks)
        assert all(chunk.page_number is not None for chunk in chunks)

    listing = client.get("/api/student/personal-materials", headers=auth(student_token))
    assert listing.status_code == 200
    item = next(
        entry
        for entry in listing.get_json()["data"]["items"]
        if entry["material_id"] == data["document_id"]
    )
    assert item["workspace_scope"] == "PERSONAL"
    assert item["visibility"] == "PRIVATE"
    assert item["processing_status"] == "READY"
    assert item["mime_type"] == "application/pdf"
    assert item["chunk_count"] > 0
    # The session-scoped test database is shared with legacy quota tests.
    # Remove only this test's metering so the test does not alter their baseline.
    with app_module.app.app_context():
        app_module.UsageRecord.query.filter_by(
            related_document_id=data["document_id"]
        ).delete(synchronize_session=False)
        app_module.db.session.commit()


def test_personal_material_access_and_soft_delete_preserve_history(
    client, app_module, student_token, teacher_token
):
    with app_module.app.app_context():
        owner = app_module.User.query.filter_by(
            email="student.test@lexibridge.local"
        ).first()
        other = app_module.User(
            username="other_13c",
            email="other.13c@lexibridge.local",
            password_hash=app_module.generate_password_hash(
                "Other1234", method="pbkdf2:sha256"
            ),
            role="student",
            is_verified=True,
            created_at=app_module.current_time_text(),
        )
        app_module.db.session.add(other)
        app_module.db.session.flush()
        document = app_module.Document(
            owner_user_id=owner.id,
            scope_type="personal",
            filename="private.pdf",
            original_filename="private.pdf",
            content_type="application/pdf",
            file_type="pdf",
            language="en",
            parsing_status="parsed",
            upload_time=app_module.current_time_text(),
        )
        app_module.db.session.add(document)
        app_module.db.session.flush()
        source = app_module.KnowledgeSource(
            source_uid="personal-delete-source-13c",
            document_id=document.id,
            owner_user_id=owner.id,
            scope_type="personal",
            visibility="private",
            language="en",
            title="Private source",
            name="Private source",
            status="active",
            allow_student_search=True,
            authorization_status="allowed_for_private_use",
            license_status="restricted",
            knowledge_base_type="student_personal_kb",
        )
        app_module.db.session.add(source)
        query = app_module.StudentConceptQuery(
            query_uid="history-query-13c",
            result_uid="history-result-13c",
            student_id=owner.id,
            workspace_scope="PERSONAL",
            workspace_uid=f"personal:{owner.id}",
            source_uid=source.source_uid,
            source_version="1",
            chunk_uid="historical-chunk",
            selected_text="charge",
            selection_start=0,
            selection_end=6,
            query_fingerprint="f" * 64,
            result_json=(
                '{"query_uid":"history-query-13c",'
                '"result_uid":"history-result-13c",'
                f'"workspace_scope":"PERSONAL","workspace_uid":"personal:{owner.id}",'
                '"source_uid":"personal-delete-source-13c",'
                '"source_version":"1","english_term":"charge",'
                '"selected_text":"charge","bounded_context":"charge",'
                '"english_evidence":[],"chinese_evidence":[],'
                '"chinese_candidates":[],"selected_candidate":null,'
                '"qualification":null,"generated_hints":[]}'
            ),
        )
        app_module.db.session.add(query)
        app_module.db.session.commit()
        material_id = document.id

    other_login = client.post(
        "/api/auth/login",
        json={"email": "other.13c@lexibridge.local", "password": "Other1234"},
    )
    other_token = other_login.get_json()["token"]
    assert client.get(
        f"/api/student/personal-materials/{material_id}", headers=auth(other_token)
    ).status_code == 404
    assert client.delete(
        f"/api/student/personal-materials/{material_id}", headers=auth(other_token)
    ).status_code == 404
    assert client.get(
        f"/api/student/personal-materials/{material_id}", headers=auth(teacher_token)
    ).status_code == 403

    deleted = client.delete(
        f"/api/student/personal-materials/{material_id}", headers=auth(student_token)
    )
    assert deleted.status_code == 200
    assert deleted.get_json()["data"]["material"]["lifecycle_status"] == "DELETED"

    history = client.get(
        "/api/student/concept-queries/history-query-13c",
        headers=auth(student_token),
    )
    assert history.status_code == 200
    assert history.get_json()["data"]["query"]["source_availability"] == "SOURCE_UNAVAILABLE"

    with app_module.app.app_context():
        source = app_module.KnowledgeSource.query.filter_by(
            source_uid="personal-delete-source-13c"
        ).first()
        assert source.status == "deprecated"
        assert source.allow_student_search is False


def test_owned_unready_or_unprovenanced_material_fails_closed_as_not_ready(
    client, app_module, student_token
):
    with app_module.app.app_context():
        owner = app_module.User.query.filter_by(
            email="student.test@lexibridge.local"
        ).first()
        source = app_module.KnowledgeSource(
            source_uid="personal-unready-source-13c",
            owner_user_id=owner.id,
            scope_type="personal",
            visibility="private",
            language="en",
            title="Unready source",
            name="Unready source",
            status="active",
            allow_student_search=False,
        )
        app_module.db.session.add(source)
        app_module.db.session.commit()

    response = client.post(
        "/api/student/concept-queries",
        headers=auth(student_token),
        json={
            "workspace_scope": "PERSONAL",
            "source_uid": "personal-unready-source-13c",
            "chunk_uid": "missing",
            "selected_text": "charge",
            "selection_start": 0,
            "selection_end": 6,
        },
    )
    assert response.status_code == 200
    result = response.get_json()["data"]["query"]
    assert result["alignment_status"] == "NOT_READY"
    assert result["reason_code"] == "STUDENT_CONCEPT_SOURCE_NOT_READY"
    assert result["recommended_chinese_concept"] is None
    assert result["learning_support"]["contract_id"] == (
        "student-learning-support@1.0.0"
    )
    assert result["learning_support"]["status"] == "NO_RELIABLE_ALIGNMENT"
    assert result["learning_support"]["provider_used"] is False
