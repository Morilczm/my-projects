from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FINAL_DIR = ROOT / "final_delivery"


def read(name: str) -> str:
    return (FINAL_DIR / name).read_text(encoding="utf-8")


def test_final_course_report_materials_cover_required_thinking():
    content = read("final_course_report_materials.md").lower()
    assert "computational thinking" in content
    assert "design thinking" in content
    assert "knowledge alignment" in content
    assert "evidence_score" in content


def test_final_presentation_outline_has_at_least_eight_slides_and_evolution():
    content = read("final_presentation_outline.md")
    assert content.count("## Slide") >= 8
    assert "Project Evolution" in content
    assert "From AI Translation Website to AI Knowledge Alignment Platform" in content


def test_final_poster_copy_contains_evaluation_metrics():
    content = read("final_poster_copy.md")
    assert "Evaluation" in content
    assert "no_evidence_forced_alignment_rate" in content


def test_final_demo_script_contains_all_roles():
    content = read("final_demo_script.md")
    assert "教师端演示" in content
    assert "学生端演示" in content
    assert "管理员端演示" in content


def test_limitations_and_next_steps_are_explicit():
    limitations = read("final_known_limitations.md").lower()
    assert "not production-ready" in limitations
    next_steps = read("final_next_steps.md")
    assert "Stage 1" in next_steps
    assert "Stage 2" in next_steps
    assert "Stage 3" in next_steps
    assert "Stage 4" in next_steps
