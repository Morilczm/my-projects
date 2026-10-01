import io
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def chinese_pdf_bytes():
    buffer = io.BytesIO()
    document = canvas.Canvas(buffer, pagesize=letter)
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    document.setFont("STSong-Light", 12)
    document.drawString(72, 720, "电势")
    document.drawString(72, 690, "电势表示单位电荷在电场中的电势能。")
    document.save()
    return buffer.getvalue()


def test_formula_detection_ignores_parser_page_markers_but_keeps_formula_signals():
    from services.formula_detection import contains_substantive_formula_text

    assert not contains_substantive_formula_text(
        "[Page 1]\nElectric potential is potential energy per unit charge."
    )
    assert not contains_substantive_formula_text(
        "Electric charge is measured in coulombs (C). Like charges repel - unlike charges attract."
    )
    assert not contains_substantive_formula_text(
        "电场通常以牛顿每库仑（N/C）计量，电势通常以伏特（V）计量。"
    )
    assert contains_substantive_formula_text("V = U / q")
    assert contains_substantive_formula_text("∫ f(x) dx")
    assert contains_substantive_formula_text("x^2 + y^2 = r^2")


def test_clean_layout_provenance_labels_are_not_parse_quality_failures():
    from services.bilingual_evidence_qualification import _workflow_quality_status
    from services.student_concept_queries import qualification_quality_status

    assert _workflow_quality_status(
        {
            "quality_status": "native_text_ok",
            "quality_flags": [
                "native_text_ok",
                "layout_aware_chunk",
                "layout_type_text",
                "parser_backend_pymupdf_native",
                "parser_version_parse_quality_v1",
            ],
        }
    ) == "ready"
    assert _workflow_quality_status(
        {
            "quality_status": "native_text_ok",
            "quality_flags": ["native_text_ok", "unknown_future_risk"],
        }
    ) == "native_text_ok"
    assert qualification_quality_status(
        {
            "quality_status": "native_text_ok",
            "quality_flags": ["native_text_ok", "unknown_future_risk"],
        }
    ) == "native_text_ok"


def test_qualified_pair_drops_only_stale_pre_alignment_risks():
    from services.student_concept_queries import finalize_student_alignment_risks

    risks = finalize_student_alignment_risks(
        [
            "bilingual_alignment_not_verified",
            "candidate_not_alignment_verified",
            "missing_chinese_term",
            "evidence_from_low_trust_source",
        ],
        qualification={"decision": "QUALIFIED"},
        selected_candidate={"text": "电势"},
    )

    assert "bilingual_alignment_not_verified" not in risks
    assert "candidate_not_alignment_verified" not in risks
    assert "missing_chinese_term" not in risks
    assert "evidence_from_low_trust_source" in risks


def test_13c2_chinese_evidence_upload_requires_private_use_attestation(
    client, student_token
):
    response = client.post(
        "/api/documents/upload",
        headers=auth(student_token),
        data={
            "scope_type": "personal",
            "personal_workspace_contract": "13C2",
            "personal_material_role": "CHINESE_REFERENCE_EVIDENCE",
            "language": "zh",
            "file": (io.BytesIO(chinese_pdf_bytes()), "reference.pdf"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 400
    assert response.get_json()["error_code"] == "PERSONAL_MATERIAL_RIGHTS_ATTESTATION_REQUIRED"


def test_13c2_material_role_cannot_disguise_submitted_language(
    client, student_token
):
    response = client.post(
        "/api/documents/upload",
        headers=auth(student_token),
        data={
            "scope_type": "personal",
            "personal_workspace_contract": "13C2",
            "personal_material_role": "CHINESE_REFERENCE_EVIDENCE",
            "usage_rights_confirmed": "true",
            "language": "en",
            "file": (io.BytesIO(chinese_pdf_bytes()), "reference.pdf"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 400
    assert response.get_json()["error_code"] == "PERSONAL_MATERIAL_LANGUAGE_ROLE_MISMATCH"


def test_13c2_chinese_reference_is_private_governed_evidence(
    client, app_module, student_token
):
    response = client.post(
        "/api/documents/upload",
        headers=auth(student_token),
        data={
            "scope_type": "personal",
            "personal_workspace_contract": "13C2",
            "personal_material_role": "CHINESE_REFERENCE_EVIDENCE",
            "usage_rights_confirmed": "true",
            "language": "zh",
            "source_type": "student_upload",
            "file": (io.BytesIO(chinese_pdf_bytes()), "private-reference.pdf"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    payload = response.get_json()["data"]

    with app_module.app.app_context():
        app_module.run_background_job(payload["job_id"], worker_id="pytest-13c2")
        source = app_module.KnowledgeSource.query.filter_by(
            document_id=payload["document_id"]
        ).one()
        assert source.language == "zh"
        assert source.source_role == "chinese_reference_material"
        assert source.scope_type == "personal"
        assert source.visibility == "private"
        assert source.trust_level == "student_uploaded"
        assert source.authorization_status == "allowed_for_private_use"
        assert source.license_status == "restricted"
        assert source.license_note == "student_attested_private_use"
        assert source.allow_student_search is True
        assert source.allow_derivative_cards is False
        assert "formula_ocr_required" not in set(
            app_module.safe_json_loads(source.quality_flags, [])
        )

    listing = client.get(
        "/api/student/personal-materials", headers=auth(student_token)
    )
    item = next(
        row
        for row in listing.get_json()["data"]["items"]
        if row["material_id"] == payload["document_id"]
    )
    assert item["material_role"] == "CHINESE_REFERENCE_EVIDENCE"
    assert item["evidence_tier"] == "PERSONAL_PRIVATE"
    assert item["search_eligible"] is True
    assert item["qualification_quality_status"] == "ready"

    deleted = client.delete(
        f"/api/student/personal-materials/{payload['document_id']}",
        headers=auth(student_token),
    )
    assert deleted.status_code == 200

    with app_module.app.app_context():
        app_module.UsageRecord.query.filter_by(
            related_document_id=payload["document_id"]
        ).delete(synchronize_session=False)
        app_module.db.session.commit()


def test_personal_chinese_evidence_scope_is_owner_isolated_and_personal_first():
    from services.student_concept_queries import resolve_evidence_scope

    def source(uid, *, owner=None, scope="personal", visibility="private"):
        return {
            "source_uid": uid,
            "language": "zh",
            "status": "active",
            "allow_student_search": True,
            "authorization_status": "allowed_for_private_use"
            if scope == "personal"
            else "authorized",
            "license_status": "restricted" if scope == "personal" else "open_licensed",
            "scope_type": scope,
            "visibility": visibility,
            "owner_user_id": owner,
        }

    sources = [
        source("mine", owner=7),
        source("other-student", owner=8),
        source("platform", scope="platform", visibility="public"),
    ]
    personal = resolve_evidence_scope(
        sources,
        workspace_scope="PERSONAL",
        student_id=7,
        course_id=None,
        allow_platform_governed=False,
    )
    fallback_allowed = resolve_evidence_scope(
        sources,
        workspace_scope="PERSONAL",
        student_id=7,
        course_id=None,
        allow_platform_governed=True,
    )

    assert personal.allowed_source_uids == ("mine",)
    assert personal.evidence_tier == "PERSONAL_PRIVATE"
    assert fallback_allowed.allowed_source_uids == ("mine", "platform")
    assert "other-student" not in fallback_allowed.allowed_source_uids


def test_personal_workspace_exposes_explicit_chinese_evidence_upload_contract():
    html = open("frontend/index.html", encoding="utf-8").read()

    assert 'name="personal_material_role"' in html
    assert 'value="CHINESE_REFERENCE_EVIDENCE"' in html
    assert 'name="usage_rights_confirmed"' in html
    assert 'value="13C2"' in html
    assert 'data-testid="personal-evidence-corpus-status"' in html


def test_offline_acceptance_runner_exercises_13c2_without_provider():
    source = Path(
        "scripts/evaluations/real_uploaded_student_alignment_13c1.py"
    ).read_text(encoding="utf-8")

    assert 'choices=("13C", "13C2")' in source
    assert '"usage_rights_confirmed": "true"' in source
    assert '"CHINESE_REFERENCE_EVIDENCE"' in source
    assert '"personal-chinese-evidence-corpus-13c2@1.0.0"' in source
    assert '"real_provider_requests": 0' in source
