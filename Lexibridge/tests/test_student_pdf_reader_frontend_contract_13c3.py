from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")


def test_shared_student_pdf_reader_replaces_flat_chunk_picker():
    for marker in (
        'data-testid="student-material-reader"',
        'data-testid="student-pdf-preview"',
        'data-testid="student-pdf-canvas"',
        'data-testid="student-pdf-text-layer"',
        'data-testid="student-reader-page"',
        'data-testid="student-reader-prev"',
        'data-testid="student-reader-next"',
        'data-testid="student-reader-selection-action"',
        "function renderStudentMaterialReader",
        "/reader?page=",
    ):
        assert marker in HTML
    assert ".limit(100)" not in HTML
    assert "<iframe" not in HTML[
        HTML.index("function renderStudentMaterialReader"):
        HTML.index("function renderSubscription")
    ]


def test_reader_uses_authorized_pdf_blob_without_bearer_token_in_url():
    assert "/api/student/concept-materials/${encodeURIComponent(sourceUid)}/file" in HTML
    assert "URL.createObjectURL" in HTML
    assert "URL.revokeObjectURL" in HTML
    assert 'headers.Authorization = `Bearer ${state.token}`' in HTML
    reader_section = HTML[
        HTML.index("function renderStudentMaterialReader"):
        HTML.index("function renderSubscription")
    ]
    assert "?token=" not in reader_section
    assert "storage_key" not in reader_section


def test_personal_and_managed_materials_enter_the_same_reader_and_query_contract():
    assert "openPersonalMaterialReader" in HTML
    assert "selectConceptMaterial" in HTML
    assert "capturePdfConceptSelection" in HTML
    assert "/api/student/concept-queries" in HTML
    assert "PERSONAL" in HTML
    assert "MANAGED_COURSE" in HTML


def test_reader_keeps_student_boundary_and_has_no_review_or_provider_controls():
    reader_section = HTML[
        HTML.index("function renderStudentMaterialReader"):
        HTML.index("function renderSubscription")
    ]
    assert "Reviewer Console" not in reader_section
    assert "review-action-approve" not in reader_section
    assert "Provider" not in reader_section
    assert "Prompt" not in reader_section
