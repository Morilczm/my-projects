from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "index.html"
BROWSER_RUNNER = ROOT / "scripts" / "run_browser_e2e.py"


def test_teacher_review_page_exposes_one_governed_vertical_slice():
    source = FRONTEND.read_text(encoding="utf-8")
    for marker in (
        'data-testid="teacher-alignment-review-case"',
        'data-testid="review-action-accept-recommendation"',
        'data-testid="review-action-select-alternative"',
        'data-testid="review-action-reject-alignment"',
        'data-testid="review-action-defer"',
        'data-testid="review-generate-draft"',
        'data-testid="teacher-draft-editor"',
        "/review-case",
        "/generate-draft",
        "/draft",
    ):
        assert marker in source
    assert "GENERATED_HINT" not in source


def test_teacher_review_ui_surfaces_loading_empty_error_and_conflict_states():
    source = FRONTEND.read_text(encoding="utf-8")
    assert 'data-testid="teacher-review-loading"' in source
    assert 'data-testid="teacher-review-empty"' in source
    assert 'data-testid="review-error"' in source
    assert "This case is stale; refresh and try again." in source
    assert "No reviewable cards, or this account has no permission" in source


def test_reviewer_detail_loader_discards_stale_card_responses():
    source = FRONTEND.read_text(encoding="utf-8")
    loader = source.split("async function loadReviewCard(cardUid)", 1)[1].split(
        "async function loadStudentConceptCards", 1
    )[0]
    assert "const loadSequence = ++reviewCardLoadSequence;" in loader
    assert (
        "loadSequence !== reviewCardLoadSequence || state.selectedReviewCardUid !== cardUid"
        in loader
    )
    assert loader.index("loadSequence !== reviewCardLoadSequence") < loader.index(
        "state.cache.reviewCard ="
    )


def test_browser_e2e_covers_review_approval_fake_draft_and_edit():
    source = BROWSER_RUNNER.read_text(encoding="utf-8")
    for expected in (
        "unified teacher alignment case visible",
        "human approval saved",
        "fake draft editor visible",
        "fake draft generated, edited, saved, and left unpublished",
    ):
        assert expected in source
    assert "DeterministicFakeProviderTransport" not in source
