import pytest

from services import student_concept_queries as queries


def raw_result(decision):
    return {
        "query_uid": "query-1",
        "result_uid": "result-1",
        "workspace_scope": "MANAGED_COURSE",
        "workspace_uid": "course:10",
        "source_uid": "source-en",
        "source_version": "1",
        "english_term": "electric potential",
        "selected_text": "electric potential",
        "bounded_context": "Electric potential is potential energy per charge.",
        "english_evidence": [{"source_uid": "source-en", "chunk_uid": "en-1", "snippet": "bounded"}],
        "chinese_evidence": [{"source_uid": "source-zh", "chunk_uid": "zh-1", "snippet": "有限证据"}],
        "chinese_candidates": [
            {"candidate_uid": "candidate-1", "text": "电势", "evidence_backed": True, "generated": False}
        ],
        "selected_candidate": {
            "candidate_uid": "candidate-1",
            "text": "电势",
            "source_uid": "source-zh",
            "chunk_uid": "zh-1",
        },
        "qualification": {"decision": decision},
    }


@pytest.mark.parametrize(
    ("decision", "status", "mode"),
    [
        ("QUALIFIED", "READY", "EVIDENCE_BACKED_RECOMMENDATION"),
        ("REVIEW_REQUIRED", "REVIEW_REQUIRED", "EVIDENCE_BACKED_ALTERNATIVES"),
        ("REJECTED", "NOT_READY", "NO_RELIABLE_ALIGNMENT"),
        (None, "NOT_READY", "NO_RELIABLE_ALIGNMENT"),
    ],
)
def test_qualification_maps_to_student_status_without_human_gate(decision, status, mode):
    payload = queries.serialize_alignment_result(raw_result(decision))
    assert payload["alignment_status"] == status
    assert payload["display_mode"] == mode
    assert payload["visibility"] == "PRIVATE"
    assert payload["authority"] == "NON_OFFICIAL"
    assert payload["publication_status"] == "NOT_APPLICABLE"
    assert payload["requires_human_review_before_view"] is False
    assert payload["student_explanation"]
    assert "risk_labels" not in payload
    assert "reason_codes" not in payload


def test_not_ready_never_returns_canonical_chinese_term():
    payload = queries.serialize_alignment_result(raw_result("REJECTED"))
    assert payload["recommended_chinese_concept"] is None


def test_generated_hint_is_not_evidence_or_canonical_term():
    value = raw_result("REJECTED")
    value["generated_hints"] = [{
        "text": "电位",
        "generated": True,
        "no_evidence": True,
        "provenance_type": "GENERATED_HINT",
        "provider_id": "fake",
        "provider_version": "1",
    }]
    payload = queries.serialize_alignment_result(value)
    assert payload["generated_hints"][0]["evidence_backed"] is False
    assert payload["recommended_chinese_concept"] is None


def test_private_student_result_can_show_evidence_backed_ambiguity_without_changing_formal_rejection():
    value = raw_result("REJECTED")
    value["qualification"]["reason_codes"] = [
        "EVIDENCE_PAIR_MARGIN_INSUFFICIENT",
        "EVIDENCE_PAIR_UNCERTAIN",
        "EVIDENCE_QUALIFICATION_EXECUTION_FAILED",
        "EVIDENCE_SCORE_COMPONENT_CONFLICT",
    ]
    value["chinese_candidates"][0].update(
        source_uid="source-zh", chunk_uid="zh-1"
    )

    payload = queries.serialize_alignment_result(value)

    assert value["qualification"]["decision"] == "REJECTED"
    assert payload["alignment_status"] == "REVIEW_REQUIRED"
    assert payload["display_mode"] == "EVIDENCE_BACKED_ALTERNATIVES"
    assert payload["uncertain"] is True
    assert payload["recommended_chinese_concept"]["text"] == "电势"


def test_private_student_result_does_not_promote_fatal_rejection_to_review():
    value = raw_result("REJECTED")
    value["qualification"]["reason_codes"] = [
        "EVIDENCE_PROVENANCE_INCOMPLETE",
        "EVIDENCE_PAIR_UNCERTAIN",
    ]
    value["chinese_candidates"][0].update(
        source_uid="source-zh", chunk_uid="zh-1"
    )
    payload = queries.serialize_alignment_result(value)
    assert payload["alignment_status"] == "NOT_READY"
    assert payload["recommended_chinese_concept"] is None


def test_private_student_result_does_not_promote_unbound_selected_candidate():
    value = raw_result("REJECTED")
    value["qualification"]["reason_codes"] = [
        "EVIDENCE_PAIR_MARGIN_INSUFFICIENT",
        "EVIDENCE_PAIR_UNCERTAIN",
    ]
    value["chinese_candidates"][0].update(
        source_uid="source-zh", chunk_uid="zh-1"
    )
    value["selected_candidate"] = {
        "candidate_uid": "generated-or-missing",
        "text": "电位",
        "generated": True,
    }
    payload = queries.serialize_alignment_result(value)
    assert payload["alignment_status"] == "NOT_READY"
    assert payload["recommended_chinese_concept"] is None
