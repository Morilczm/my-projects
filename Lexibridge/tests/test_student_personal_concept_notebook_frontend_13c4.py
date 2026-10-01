from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")


def test_student_navigation_has_private_concept_notebook():
    assert '["conceptNotebook", bilingual("个人概念本", "My Concept Notebook")]' in HTML
    assert 'data-testid="personal-concept-notebook-nav"' in HTML
    assert 'data-testid="personal-concept-notebook-page"' in HTML


def test_notebook_has_search_workspace_status_and_learning_filters():
    for test_id in (
        "notebook-search",
        "notebook-workspace-filter",
        "notebook-view-filter",
        "notebook-alignment-filter",
        "notebook-result-row",
        "notebook-summary",
        "notebook-empty",
    ):
        assert f'data-testid="{test_id}"' in HTML
    assert "PERSONAL" in HTML
    assert "MANAGED_COURSE" in HTML
    assert "STILL_CONFUSED" in HTML


def test_notebook_reuses_student_result_and_personal_record_editor():
    notebook_start = HTML.index("function renderPersonalConceptNotebook")
    notebook_end = HTML.index("function renderStudentSourceSummary")
    notebook = HTML[notebook_start:notebook_end]
    assert "renderStudentConceptResult" in notebook
    assert "/api/student/personal-concept-notebook" in HTML
    assert "/revisit" in HTML
    assert "updatePersonalConceptState" in HTML


def test_notebook_does_not_expose_reviewer_provider_or_official_controls():
    notebook_start = HTML.index("function renderPersonalConceptNotebook")
    notebook_end = HTML.index("function renderStudentSourceSummary")
    notebook = HTML[notebook_start:notebook_end]
    for forbidden in (
        "Reviewer Console",
        "review-action-approve",
        "Provider",
        "Prompt",
        "COURSE_SHARED",
        "authority=OFFICIAL",
    ):
        assert forbidden not in notebook
