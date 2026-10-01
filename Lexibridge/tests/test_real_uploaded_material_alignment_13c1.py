import io
from pathlib import Path

import pytest
from reportlab.lib.pagesizes import letter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas


class DeterministicWorkflowEmbeddingBackend:
    """CI backend that exercises the production workflow without a model download."""

    backend_id = "local_multilingual_e5_pytorch_cpu_v1"
    model_id = "intfloat/multilingual-e5-small"
    model_revision = "614241f622f53c4eeff9890bdc4f31cfecc418b3"

    def readiness(self):
        return type("Readiness", (), {"ready": True, "reason_code": "READY"})()

    def embed_queries(self, texts):
        return [[1.0, 0.0] for _ in texts]

    def embed_passages(self, texts):
        return [
            [1.0, 0.0] if "电势" in text else [0.0, 1.0]
            for text in texts
        ]


class DeterministicWorkflowRerankerBackend:
    backend_id = "local_bge_reranker_v2_m3_cpu_v1"
    model_id = "BAAI/bge-reranker-v2-m3"
    model_revision = "79c481748842b7efa0a12db59915db91731f0b93"

    def readiness(self):
        return type("Readiness", (), {"ready": True, "reason_code": "READY"})()

    def score_pairs(self, pairs):
        return [5.0 for _ in pairs]


class DeterministicChargeEmbeddingBackend:
    """Exercise evidence-backed Student review without a reranker."""

    backend_id = "local_multilingual_e5_pytorch_cpu_v1"
    model_id = "intfloat/multilingual-e5-small"
    model_revision = "614241f622f53c4eeff9890bdc4f31cfecc418b3"

    def readiness(self):
        return type("Readiness", (), {"ready": True, "reason_code": "READY"})()

    def embed_queries(self, texts):
        return [[1.0, 0.0] for _ in texts]

    def embed_passages(self, texts):
        return [
            [1.0, 0.0] if "电荷" in text and "电势" not in text else [0.0, 1.0]
            for text in texts
        ]


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def pdf_bytes(*lines):
    buffer = io.BytesIO()
    document = canvas.Canvas(buffer, pagesize=letter)
    y = 720
    for line in lines:
        if any(ord(character) > 127 for character in line):
            pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
            document.setFont("STSong-Light", 12)
        else:
            document.setFont("Helvetica", 12)
        document.drawString(72, y, line)
        y -= 30
    document.save()
    return buffer.getvalue()


def upload_and_process(client, app_module, token, *, filename, language, lines):
    response = client.post(
        "/api/documents/upload",
        headers=auth(token),
        data={
            "scope_type": "personal",
            "language": language,
            "source_type": "student_upload",
            "personal_workspace_contract": "13C",
            "file": (io.BytesIO(pdf_bytes(*lines)), filename),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    data = response.get_json()["data"]
    with app_module.app.app_context():
        app_module.run_background_job(data["job_id"], worker_id="pytest-13c1")
        source = app_module.KnowledgeSource.query.filter_by(
            document_id=data["document_id"]
        ).one()
        chunks = app_module.KnowledgeChunk.query.filter_by(
            source_uid=source.source_uid
        ).order_by(app_module.KnowledgeChunk.id.asc()).all()
        assert chunks
        return source.source_uid, [(chunk.chunk_uid, chunk.content) for chunk in chunks]


@pytest.fixture()
def isolated_workflow_test_state(app_module):
    """Keep session-scoped app quota/config state unchanged for later tests."""
    missing = object()
    config_keys = (
        "STUDENT_ALIGNMENT_RUNNER",
        "STUDENT_CROSS_LANGUAGE_EMBEDDING_BACKEND",
        "STUDENT_BILINGUAL_RERANKER_BACKEND",
    )
    previous_config = {
        key: app_module.app.config.get(key, missing)
        for key in config_keys
    }
    with app_module.app.app_context():
        plan = app_module.SubscriptionPlan.query.filter_by(name="Free").one()
        previous_plan = (plan.monthly_pages, plan.monthly_ai_calls)
        maximum_usage_id = max(
            (record.id for record in app_module.UsageRecord.query.all()),
            default=0,
        )
        plan.monthly_pages = max(int(plan.monthly_pages or 0), 100)
        plan.monthly_ai_calls = max(int(plan.monthly_ai_calls or 0), 100)
        app_module.db.session.commit()
    try:
        yield
    finally:
        for key, value in previous_config.items():
            if value is missing:
                app_module.app.config.pop(key, None)
            else:
                app_module.app.config[key] = value
        with app_module.app.app_context():
            app_module.UsageRecord.query.filter(
                app_module.UsageRecord.id > maximum_usage_id
            ).delete(synchronize_session=False)
            plan = app_module.SubscriptionPlan.query.filter_by(name="Free").one()
            plan.monthly_pages, plan.monthly_ai_calls = previous_plan
            app_module.db.session.commit()


def test_newly_uploaded_english_pdf_runs_same_source_through_production_workflow(
    client, app_module, student_token, monkeypatch, isolated_workflow_test_state
):
    monkeypatch.setenv("FORMULA_DETECTION_MODE", "off")
    chinese_source_uid, _ = upload_and_process(
        client,
        app_module,
        student_token,
        filename="personal-chinese-reference.pdf",
        language="zh",
        lines=("电势", "电势表示单位电荷在电场中的电势能。"),
    )
    english_source_uid, english_chunks = upload_and_process(
        client,
        app_module,
        student_token,
        filename="personal-english-course.pdf",
        language="en",
        lines=(
            "Electric potential",
            "Electric potential is potential energy per unit charge.",
        ),
    )
    chunk_uid, chunk_text = next(
        (uid, text)
        for uid, text in english_chunks
        if "electric potential" in text.casefold()
    )
    selected = "Electric potential"
    start = chunk_text.index(selected)

    app_module.app.config.pop("STUDENT_ALIGNMENT_RUNNER", None)
    app_module.app.config["STUDENT_CROSS_LANGUAGE_EMBEDDING_BACKEND"] = (
        DeterministicWorkflowEmbeddingBackend()
    )
    app_module.app.config["STUDENT_BILINGUAL_RERANKER_BACKEND"] = (
        DeterministicWorkflowRerankerBackend()
    )
    response = client.post(
        "/api/student/concept-queries",
        headers={
            **auth(student_token),
            "Idempotency-Key": "13c1-same-uploaded-source",
        },
        json={
            "workspace_scope": "PERSONAL",
            "source_uid": english_source_uid,
            "chunk_uid": chunk_uid,
            "selected_text": selected,
            "selection_start": start,
            "selection_end": start + len(selected),
        },
    )
    assert response.status_code == 200
    result = response.get_json()["data"]["query"]
    assert result["source_uid"] == english_source_uid
    assert result["processing_status"] == "completed"
    assert result["english_evidence"]
    assert {item["source_uid"] for item in result["english_evidence"]} == {
        english_source_uid
    }
    assert result["chinese_evidence"]
    assert {item["source_uid"] for item in result["chinese_evidence"]} == {
        chinese_source_uid
    }
    assert result["chinese_candidates"]
    assert all("browser-" not in str(value) for value in result.values())

    with app_module.app.app_context():
        query = app_module.StudentConceptQuery.query.filter_by(
            query_uid=result["query_uid"]
        ).one()
        assert query.source_uid == english_source_uid
        assert query.processing_status == "completed"
        assert chinese_source_uid in query.allowed_source_uids_json
        raw = __import__("json").loads(query.result_json)
        qualification = raw.get("qualification") or {}
        reasons = set(qualification.get("reason_codes") or [])
        assert "EVIDENCE_QUALIFICATION_EXECUTION_FAILED" not in reasons
        assert "no_chinese_candidate_found" not in set(raw.get("risk_labels") or [])


def test_clean_native_parse_quality_adapter_does_not_hide_review_flags():
    from services import bilingual_evidence_qualification as qualification

    assert qualification._workflow_quality_status({
        "quality_status": "native_text_ok",
        "quality_flags": ["native_text_ok", "layout_aware_chunk"],
    }) == "ready"
    assert qualification._workflow_quality_status({
        "quality_status": "native_text_ok",
        "quality_flags": ["native_text_ok", "formula_ocr_required"],
    }) == "native_text_ok"
    assert qualification._workflow_quality_status({
        "quality_status": "native_text_ok",
        "quality_flags": ["native_text_ok", "formula_region_detected"],
    }) == "native_text_ok"
    assert qualification._workflow_quality_status({
        "quality_status": "native_text_ok",
        "quality_flags": ["native_text_ok", "future_unknown_risk"],
    }) == "native_text_ok"


def test_uploaded_unit_prose_yields_private_review_alternatives_without_reranker(
    client, app_module, student_token, monkeypatch, isolated_workflow_test_state
):
    monkeypatch.delenv("FORMULA_DETECTION_MODE", raising=False)
    chinese_source_uid, _ = upload_and_process(
        client,
        app_module,
        student_token,
        filename="personal-charge-reference.pdf",
        language="zh",
        lines=(
            "电荷",
            "电荷是物质的一种基本物理属性。",
            "电荷以库仑（C）计量。",
        ),
    )
    english_source_uid, english_chunks = upload_and_process(
        client,
        app_module,
        student_token,
        filename="personal-charge-course.pdf",
        language="en",
        lines=(
            "Electric charge",
            "Electric charge is a physical property of matter.",
            "Like charges repel - unlike charges attract.",
        ),
    )
    chunk_uid, chunk_text = next(
        (uid, text)
        for uid, text in english_chunks
        if "electric charge" in text.casefold()
    )
    selected = "Electric charge"
    start = chunk_text.index(selected)

    app_module.app.config.pop("STUDENT_ALIGNMENT_RUNNER", None)
    app_module.app.config["STUDENT_CROSS_LANGUAGE_EMBEDDING_BACKEND"] = (
        DeterministicChargeEmbeddingBackend()
    )
    app_module.app.config.pop("STUDENT_BILINGUAL_RERANKER_BACKEND", None)
    response = client.post(
        "/api/student/concept-queries",
        headers={
            **auth(student_token),
            "Idempotency-Key": "13c-quality-private-review-no-reranker",
        },
        json={
            "workspace_scope": "PERSONAL",
            "source_uid": english_source_uid,
            "chunk_uid": chunk_uid,
            "selected_text": selected,
            "selection_start": start,
            "selection_end": start + len(selected),
        },
    )

    assert response.status_code == 200
    result = response.get_json()["data"]["query"]
    assert result["alignment_status"] == "REVIEW_REQUIRED"
    assert result["recommended_chinese_concept"]["text"] == "电荷"
    assert result["chinese_evidence"][0]["source_uid"] == chinese_source_uid
    assert result["uncertain"] is True

    with app_module.app.app_context():
        query = app_module.StudentConceptQuery.query.filter_by(
            query_uid=result["query_uid"]
        ).one()
        raw = __import__("json").loads(query.result_json)
        assert raw["qualification"]["decision"] == "REJECTED"
        reasons = set(raw["qualification"]["reason_codes"])
        assert "EVIDENCE_QUALIFICATION_EXECUTION_FAILED" in reasons
        assert "EVIDENCE_SOURCE_NOT_ELIGIBLE" not in reasons
        documents = app_module.Document.query.filter(
            app_module.Document.id.in_([
                app_module.KnowledgeSource.query.filter_by(
                    source_uid=english_source_uid
                ).one().document_id,
                app_module.KnowledgeSource.query.filter_by(
                    source_uid=chinese_source_uid
                ).one().document_id,
            ])
        ).all()
        assert all(
            "formula_ocr_required" not in set(
                __import__("json").loads(document.quality_flags_json or "[]")
            )
            for document in documents
        )


def test_browser_contract_uses_uploaded_source_without_fake_alignment_runner():
    source = Path("scripts/run_browser_e2e.py").read_text(encoding="utf-8")
    frontend = Path("frontend/index.html").read_text(encoding="utf-8")
    assert 'app_module.app.config["STUDENT_ALIGNMENT_RUNNER"]' not in source
    assert "def browser_fake_alignment_runner" not in source
    assert "STUDENT_CROSS_LANGUAGE_EMBEDDING_BACKEND" in source
    assert "STUDENT_BILINGUAL_RERANKER_BACKEND" in source
    assert "uploaded_source_uid" in source
    assert "personal-material-query" in source
    assert '("e2e-personal-en", "PERSONAL"' not in source
    assert 'summary["card_uids"]["fourier"]' in source
    assert 'data-card-uid="${escapeHtml(card.card_uid)}"' in frontend


def test_real_model_acceptance_runner_is_offline_sanitized_and_has_no_provider():
    source = Path(
        "scripts/evaluations/real_uploaded_student_alignment_13c1.py"
    ).read_text(encoding="utf-8")
    assert 'os.environ["HF_HUB_OFFLINE"] = "1"' in source
    assert 'os.environ["TRANSFORMERS_OFFLINE"] = "1"' in source
    assert 'app_module.app.config.pop("STUDENT_ALIGNMENT_RUNNER", None)' in source
    assert '"real_provider_requests": 0' in source
    assert '"private_source_text_in_artifact": False' in source
    assert "response_body" not in source
    assert "request_body" not in source
