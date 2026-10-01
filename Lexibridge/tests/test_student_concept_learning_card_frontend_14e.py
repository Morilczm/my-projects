from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")


def _learning_card_renderer() -> str:
    start = HTML.index("function renderStudentConceptResult")
    end = HTML.index("function renderStudentMaterialReader")
    return HTML[start:end]


def test_alignment_result_is_presented_as_a_progressive_learning_card():
    renderer = _learning_card_renderer()
    for test_id in (
        "student-learning-card",
        "student-learning-card-front",
        "student-learning-card-answer",
        "student-learning-card-status-label",
        "student-learning-card-evidence-toggle",
        "student-learning-card-evidence",
        "student-learning-card-note-toggle",
        "student-learning-card-note-panel",
    ):
        assert f'data-testid="{test_id}"' in renderer


def test_student_status_uses_product_language_not_raw_machine_state_as_heading():
    assert "function studentAlignmentDisplay" in HTML
    assert 'READY: {label: "证据充分"' in HTML
    assert 'REVIEW_REQUIRED: {label: "存在多个有证据的候选"' in HTML
    assert 'NOT_READY: {label: "暂无可靠中文对应"' in HTML
    renderer = _learning_card_renderer()
    assert "studentAlignmentDisplay(result.alignment_status)" in renderer
    assert ">${escapeHtml(result.alignment_status)}<" not in renderer


def test_saved_result_has_active_recall_review_mode():
    renderer = _learning_card_renderer()
    assert 'data-testid="student-learning-card-review-toggle"' in renderer
    assert 'data-testid="student-learning-card-reveal"' in renderer
    assert "learningCard.reviewMode" in renderer
    assert "learningCard.answerRevealed" in renderer
    assert "先回忆中文概念，再显示答案" in renderer


def test_card_reuses_existing_personal_record_and_evidence_contracts():
    renderer = _learning_card_renderer()
    for existing_test_id in (
        "student-query-save",
        "student-query-note",
        "student-query-understood",
        "student-query-confused",
        "student-query-english-evidence",
        "student-query-chinese-evidence",
        "student-alignment-rationale",
    ):
        assert f'data-testid="{existing_test_id}"' in renderer
    assert "updatePersonalConceptState" in HTML
    assert "/api/student/concept-queries/${encodeURIComponent(result.query_uid)}/personal-record" in HTML
    assert "/api/student/learning-cards" not in HTML


def test_learning_card_interaction_state_is_ephemeral_not_a_second_domain_state():
    assert "learningCard:" in HTML
    assert "toggleLearningCardSection" in HTML
    assert "startLearningCardReview" in HTML
    assert "revealLearningCardAnswer" in HTML
    assert "PersonalLearningRecord" not in _learning_card_renderer()


def test_new_material_or_selection_clears_the_previous_result_card():
    assert "function resetStudentConceptResult" in HTML
    assert "resetStudentConceptResult();" in HTML
    select_start = HTML.index("async selectConceptMaterial(sourceUid)")
    select_end = HTML.index("async changeStudentReaderPage", select_start)
    assert "resetStudentConceptResult();" in HTML[select_start:select_end]
    submit_start = HTML.index("async submitStudentConceptQuery()")
    submit_end = HTML.index("toggleLearningCardSection", submit_start)
    assert "resetStudentConceptResult();" in HTML[submit_start:submit_end]
