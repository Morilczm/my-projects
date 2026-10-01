import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "frontend" / "index.html"
FORMAL_MODULE = ROOT / "frontend" / "js" / "formal-workflow.js"


def test_teacher_alignment_entry_uses_only_formal_workflow_api():
    index = INDEX.read_text(encoding="utf-8")
    module = FORMAL_MODULE.read_text(encoding="utf-8")

    assert '<script src="./js/formal-workflow.js"></script>' in index
    assert "startFormalAlignmentForDocument" in index
    assert 'data-testid="formal-alignment-start"' in index
    assert "/api/document-alignment-runs" in module
    assert 'api("/api/alignment/run"' not in index
    assert "runAlignmentForDocument" not in index
    assert "/api/alignment/run" not in module


def test_teacher_alignment_resolves_server_governed_source_identity():
    index = INDEX.read_text(encoding="utf-8")

    assert "governedSourceForDocument" in index
    assert "source.document_id" in index
    assert "source.source_uid" in index
    assert "await loadKnowledge()" in index
    assert "filename" not in re.search(
        r"function governedSourceForDocument\(.*?\n\s*}", index, flags=re.S
    ).group(0)
    assert "parse_uid" not in re.search(
        r"function governedSourceForDocument\(.*?\n\s*}", index, flags=re.S
    ).group(0)


def test_minimal_formal_run_and_paginated_item_controls_are_present():
    index = INDEX.read_text(encoding="utf-8")

    for test_id in (
        "formal-alignment-status",
        "formal-alignment-progress",
        "formal-alignment-error",
        "formal-alignment-items",
        "formal-alignment-prev",
        "formal-alignment-next",
        "formal-alignment-resume",
    ):
        assert f'data-testid="{test_id}"' in index
    assert "page_size=20" in FORMAL_MODULE.read_text(encoding="utf-8")
    assert "reviewable_only" not in index


def test_formal_api_text_is_escaped_and_no_backend_contract_is_added():
    index = INDEX.read_text(encoding="utf-8")
    module = FORMAL_MODULE.read_text(encoding="utf-8")

    assert "escapeHtml(item.candidate_term" in index
    assert "escapeHtml(item.safe_error_message" in index
    assert "escapeHtml(item.confidence_summary" in index
    assert "innerHTML" not in module
    formal_body = re.search(
        r"body: JSON\.stringify\(\{ source_uid: ([A-Za-z]+) }\)", module
    ).group(0)
    assert "provider" not in formal_body
    assert "model" not in formal_body
    assert "prompt" not in formal_body
    assert "max_attempts" not in module


def test_teacher_gating_logout_cleanup_and_no_legacy_fallback_are_explicit():
    index = INDEX.read_text(encoding="utf-8")

    assert '["teacher", "admin"].includes(state.user.role)' in index
    assert "formalWorkflow.clear()" in index
    assert "formalWorkflow.cancel()" in index
    assert "legacy fallback" not in index.casefold()
    assert 'api("/api/alignment/run"' not in index
