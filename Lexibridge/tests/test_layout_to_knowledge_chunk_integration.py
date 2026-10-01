from types import SimpleNamespace
from io import BytesIO

from reportlab.lib.pagesizes import letter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas

from services import document_parse_quality, knowledge_governance


def _draw_pdf(path, title, definition, *, chinese=False):
    pdf = canvas.Canvas(str(path), pagesize=letter)
    font = "Helvetica"
    if chinese:
        font = "STSong-Light"
        try:
            pdfmetrics.registerFont(UnicodeCIDFont(font))
        except KeyError:
            pass
    pdf.setFont(font, 9)
    pdf.drawString(72, 766, "Synthetic Course Header" if not chinese else "合成课程页眉")
    pdf.setFont(font, 18)
    pdf.drawString(72, 710, title)
    pdf.setFont(font, 11)
    pdf.drawString(72, 680, definition)
    pdf.setFont(font, 9)
    pdf.drawString(280, 28, "1")
    pdf.save()


def _as_blocks(result):
    return [SimpleNamespace(**block) for block in result.blocks]


def test_synthetic_english_and_chinese_pdfs_reach_layout_chunk_contract(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("LAYOUT_PROVIDER", "rule_based")
    fixtures = [
        ("en-one.pdf", "Rotational Inertia", "Resistance to changes in rotational motion.", False),
        ("en-two.pdf", "Electric Current", "Rate of charge passing through a surface.", False),
        ("zh-one.pdf", "转动惯量", "描述物体抵抗转动状态改变能力的物理量。", True),
        ("zh-two.pdf", "电流", "表示单位时间通过截面的电荷量。", True),
    ]

    for filename, title, definition, chinese in fixtures:
        path = tmp_path / filename
        _draw_pdf(path, title, definition, chinese=chinese)
        result = document_parse_quality.parse_document_with_quality(
            str(path),
            filename=filename,
            language_hint="zh" if chinese else "en",
        )
        chunks = knowledge_governance.build_knowledge_chunks_from_parse_blocks(
            SimpleNamespace(**result.parse_record_data),
            _as_blocks(result),
            f"source-{filename}",
            {
                "language": "zh" if chinese else "en",
                "course": "Synthetic Mechanics",
            },
        )

        assert result.parse_record_data["parser_name"] == "pymupdf_layout_rule_based"
        assert len(chunks) == 1
        assert title in chunks[0]["text"]
        assert definition in chunks[0]["text"]
        assert chunks[0]["source_section"] == title
        assert "layout_provider_rule_based" in chunks[0]["quality_flags"]


def test_layout_fallback_keeps_provenance_and_marks_risk(tmp_path, monkeypatch):
    monkeypatch.setenv("LAYOUT_PROVIDER", "rule_based")
    path = tmp_path / "fallback.pdf"
    _draw_pdf(path, "Angular Velocity", "Rate of angular displacement.")

    def unavailable(_path):
        raise RuntimeError("layout backend unavailable")

    monkeypatch.setattr(document_parse_quality, "parse_pdf_layout", unavailable)
    result = document_parse_quality.parse_document_with_quality(
        str(path), filename=path.name
    )
    chunks = knowledge_governance.build_knowledge_chunks_from_parse_blocks(
        SimpleNamespace(**result.parse_record_data),
        _as_blocks(result),
        "source-fallback",
        {"language": "en", "course": "Synthetic Mechanics"},
    )

    assert result.parse_record_data["parser_name"] == "pymupdf_native"
    assert "layout_fallback_native" in result.parse_record_data["warnings"]
    assert chunks
    assert all(item["source_locator"] for item in chunks)
    assert all("layout_fallback_native" in item["quality_flags"] for item in chunks)


def test_pdf_upload_and_worker_persist_layout_aware_knowledge_chunk(
    tmp_path, monkeypatch, client, app_module, teacher_token, test_course
):
    monkeypatch.setenv("LAYOUT_PROVIDER", "rule_based")
    path = tmp_path / "upload-layout.pdf"
    _draw_pdf(
        path,
        "Magnetic Flux",
        "Magnetic flux measures field passing through a bounded surface.",
    )
    response = client.post(
        "/api/documents/upload",
        headers={"Authorization": f"Bearer {teacher_token}"},
        data={
            "scope_type": "course",
            "course_id": str(test_course.id),
            "language": "en",
            "discipline": "physics",
            "file": (BytesIO(path.read_bytes()), path.name),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    payload = response.get_json()["data"]

    with app_module.app.app_context():
        job = app_module.run_background_job(payload["job_id"], worker_id="layout-pytest")
        persisted = app_module.KnowledgeChunk.query.filter_by(
            document_id=payload["document_id"]
        ).all()

        assert job.status == "completed"
        assert len(persisted) == 1
        assert "Magnetic Flux" in persisted[0].content
        assert "bounded surface" in persisted[0].content
        assert persisted[0].source_section == "Magnetic Flux"
        assert "blocks:" in persisted[0].source_locator
