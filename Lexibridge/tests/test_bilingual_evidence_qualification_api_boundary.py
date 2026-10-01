from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_public_bilingual_api_cannot_submit_qualification_decision_or_threshold():
    app_text = (ROOT / "backend/app.py").read_text()
    workflow_text = (ROOT / "backend/services/bilingual_evidence_workflow.py").read_text()
    assert 'data.get("qualification_decision")' not in app_text
    assert 'data.get("qualification_score")' not in app_text
    assert 'data.get("qualification_threshold")' not in app_text
    assert 'input_data.get("qualification_threshold")' not in workflow_text


def test_existing_threshold_value_is_not_changed_by_task_12g():
    workflow_text = (ROOT / "backend/services/bilingual_evidence_workflow.py").read_text()
    assert "LOW_EVIDENCE_SCORE_THRESHOLD = 0.35" in workflow_text


def test_public_query_cannot_select_legacy_policy_or_override_safety_state():
    from services.bilingual_evidence_workflow import build_bilingual_evidence_query

    query = build_bilingual_evidence_query({
        "english_term": "density",
        "qualification_policy_version": "1.0.0",
        "qualification_decision": "QUALIFIED",
        "qualification_threshold": -1,
        "english_binding_status": "matched",
        "retrieval_status": "ready",
        "candidate_pool_status": "ready",
        "pair_execution_status": "succeeded",
    })
    assert "qualification_policy_version" not in query
    assert "qualification_decision" not in query
    assert "qualification_threshold" not in query
    assert "english_binding_status" not in query
    assert "retrieval_status" not in query
    assert "candidate_pool_status" not in query
    assert "pair_execution_status" not in query
