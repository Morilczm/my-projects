from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")


def _student_result_renderer():
    start = HTML.index("function renderStudentConceptResult")
    end = HTML.index("function renderPersonalConceptNotebook")
    return HTML[start:end]


def test_student_result_renders_grounded_meaning_and_alignment_rationale():
    renderer = _student_result_renderer()
    assert 'data-testid="student-meaning-here"' in renderer
    assert 'data-testid="student-alignment-rationale"' in renderer
    assert "learning_support" in renderer
    assert "只根据当前双侧证据整理" in renderer


def test_alternative_candidates_render_their_own_evidence():
    renderer = _student_result_renderer()
    assert 'data-testid="student-alternative-evidence"' in renderer
    assert "alternative.evidence" in renderer


def test_do_not_confuse_uses_concept_comparisons_not_risk_labels():
    renderer = _student_result_renderer()
    assert 'data-testid="student-concept-comparison"' in renderer
    assert "support.do_not_confuse_with" in renderer
    do_not_confuse = renderer[
        renderer.index("Do Not Confuse With") : renderer.index(
            "Confidence / Uncertainty"
        )
    ]
    assert "riskSummary" not in do_not_confuse


def test_generated_hint_is_visually_separate_from_evidence_backed_terms():
    renderer = _student_result_renderer()
    assert 'data-testid="student-generated-hint-warning"' in renderer
    assert "机器提示（非证据）" in renderer


def test_student_learning_support_does_not_surface_internal_provider_or_scores():
    renderer = _student_result_renderer()
    for forbidden in (
        "pair_score",
        "reranker_score",
        "qualification_score",
        "Prompt version",
        "Provider health",
    ):
        assert forbidden not in renderer


def test_deleted_source_is_rendered_as_historical_without_evidence_claims():
    renderer = _student_result_renderer()
    assert 'support.status === "SOURCE_UNAVAILABLE"' in renderer
    assert "历史对齐中文概念" in renderer
    assert "不再展示或解释旧证据" in renderer
