from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")


def test_student_concept_query_is_a_student_first_navigation_and_page():
    assert '["conceptQuery", bilingual("概念查询", "Concept Query")]' in HTML
    assert 'data-testid="student-concept-query-page"' in HTML
    assert 'data-testid="student-concept-material-select"' in HTML
    assert 'data-testid="student-concept-align-action"' in HTML


def test_student_result_has_evidence_uncertainty_and_non_official_label():
    assert 'data-testid="student-concept-result"' in HTML
    assert 'data-testid="student-query-english-evidence"' in HTML
    assert 'data-testid="student-query-chinese-evidence"' in HTML
    assert "个人学习结果 · 非课程官方答案 · PRIVATE · NON_OFFICIAL" in HTML
    assert 'data-testid="student-result-uncertain"' in HTML
    for heading in (
        "What It Means Here",
        "Why They Align",
        "Alternatives",
        "Do Not Confuse With",
        "Confidence / Uncertainty",
    ):
        assert heading in HTML


def test_student_can_save_note_and_understanding_without_reviewer_command():
    assert 'data-testid="student-query-save"' in HTML
    assert 'data-testid="student-query-note"' in HTML
    assert 'data-testid="student-query-understood"' in HTML
    assert 'data-testid="student-query-confused"' in HTML
    concept_section = HTML[HTML.index("function renderStudentConceptQuery"):HTML.index("function renderSubscription")]
    assert "/review" not in concept_section
    assert "Provider" not in concept_section
