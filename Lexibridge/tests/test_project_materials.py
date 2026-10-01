from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

MATERIALS = [
    ROOT / "docs" / "final-project-summary.md",
    ROOT / "docs" / "course-report-materials.md",
    ROOT / "docs" / "poster-content-outline.md",
    ROOT / "docs" / "presentation-script-outline.md",
]


def test_final_project_materials_exist_and_are_nonempty():
    for path in MATERIALS:
        assert path.exists(), path
        assert path.read_text(encoding="utf-8").strip(), path


def test_course_report_materials_include_thinking_frameworks():
    content = (ROOT / "docs" / "course-report-materials.md").read_text(encoding="utf-8")
    assert "Computational Thinking" in content
    assert "Design Thinking" in content
    assert "decomposition" in content
    assert "abstraction" in content


def test_presentation_outline_includes_project_pivot():
    content = (ROOT / "docs" / "presentation-script-outline.md").read_text(encoding="utf-8")
    assert "翻译网站" in content
    assert "课程知识对齐平台" in content


def test_poster_outline_includes_evaluation_metrics():
    content = (ROOT / "docs" / "poster-content-outline.md").read_text(encoding="utf-8")
    assert "Evaluation Metrics" in content
    assert "no_evidence_forced_alignment_rate" in content


def test_project_materials_do_not_contain_unresolved_markers():
    disallowed = ["TODO", "FIXME", "placeholder", "your-name-here"]
    for path in MATERIALS:
        content = path.read_text(encoding="utf-8").lower()
        for marker in disallowed:
            assert marker.lower() not in content, f"{marker} in {path}"
