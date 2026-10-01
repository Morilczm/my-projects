from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")


def test_my_workspace_exposes_pdf_lifecycle_without_reviewer_controls():
    for marker in (
        'data-testid="my-workspace-nav"',
        'data-testid="student-personal-workspace"',
        'data-testid="personal-material-upload-form"',
        'data-testid="personal-material-list"',
        'data-testid="personal-material-status"',
        'data-testid="personal-material-query"',
        'data-testid="personal-material-delete"',
        'accept=".pdf,application/pdf"',
        '"/api/student/personal-materials"',
    ):
        assert marker in HTML
    workspace_body = HTML[
        HTML.index("function renderPersonalWorkspace"):
        HTML.index("function renderStudentConceptResult")
    ]
    assert "Reviewer" in workspace_body  # Explicitly states the privacy boundary.
    assert "concept-review-nav" not in workspace_body
    assert "review-action-approve" not in workspace_body


def test_personal_workspace_uses_existing_concept_query_page():
    assert "openPersonalMaterialQuery" in HTML
    assert 'state.page = "conceptQuery"' in HTML
    assert 'await loadStudentConceptMaterials()' in HTML
    assert "/api/student/concept-queries" in HTML
