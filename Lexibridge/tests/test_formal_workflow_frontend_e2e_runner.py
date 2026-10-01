from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UI_RUNNER = ROOT / "scripts" / "run_formal_workflow_frontend_e2e.py"
RESUME_RUNNER = ROOT / "scripts" / "run_formal_workflow_frontend_resume_e2e.py"
BASE_BROWSER_RUNNER = ROOT / "scripts" / "run_browser_e2e.py"
SUPPORT = ROOT / "scripts" / "formal_workflow_frontend_e2e_support.py"


def test_formal_ui_runner_drives_real_controls_and_worker():
    source = UI_RUNNER.read_text(encoding="utf-8")
    combined = source + SUPPORT.read_text(encoding="utf-8")

    assert 'data-testid="formal-alignment-start"' in combined
    assert 'get_by_test_id("formal-alignment-next")' in source
    assert "run_formal_worker_once" in source
    assert "actual_items = int(run.total_items or 0)" in source
    assert "page.evaluate(async () => fetch" not in combined
    assert '"/api/alignment/run"' in source
    assert "legacy_alignment_requests" in source
    assert "duplicate_formal_posts" in source


def test_resume_runner_reloads_real_page_without_second_post():
    source = RESUME_RUNNER.read_text(encoding="utf-8")

    assert "page.reload" in source
    assert "post_count_before_reload" in source
    assert "post_count_after_reload" in source
    assert "run_formal_worker_once" in source
    assert "sessionStorage" in source
    assert "page.evaluate(async () => fetch" not in source


def test_browser_server_serves_formal_workflow_module():
    source = BASE_BROWSER_RUNNER.read_text(encoding="utf-8")

    assert '"pilot_browser_e2e_formal_workflow"' in source
    assert '"/js/formal-workflow.js"' in source
    assert 'ROOT / "frontend" / "js" / "formal-workflow.js"' in source
