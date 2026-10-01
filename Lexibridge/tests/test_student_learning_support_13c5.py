import json

import pytest

from services import student_concept_queries as queries


def _raw_result(decision="QUALIFIED", *, workspace_scope="PERSONAL"):
    return {
        "query_uid": "query-learning-support",
        "result_uid": "result-learning-support",
        "workspace_scope": workspace_scope,
        "workspace_uid": (
            "personal:student-1"
            if workspace_scope == "PERSONAL"
            else "course:course-1"
        ),
        "source_uid": "source-en",
        "source_version": "1",
        "english_term": "electric potential",
        "selected_text": "electric potential",
        "bounded_context": (
            "Electric potential describes potential energy per unit charge at a point."
        ),
        "english_evidence": [
            {
                "source_uid": "source-en",
                "chunk_uid": "chunk-en-potential",
                "page_number": 3,
                "block_uid": "block-en-potential",
                "span_start": 12,
                "span_end": 85,
                "snippet": (
                    "Electric potential describes potential energy per unit charge "
                    "at a point."
                ),
            }
        ],
        "chinese_evidence": [
            {
                "source_uid": "source-zh",
                "chunk_uid": "chunk-zh-potential",
                "page_number": 8,
                "block_uid": "block-zh-potential",
                "span_start": 20,
                "span_end": 58,
                "snippet": "电势表示单位正电荷在某点具有的电势能。",
            },
            {
                "source_uid": "source-zh",
                "chunk_uid": "chunk-zh-voltage",
                "page_number": 9,
                "block_uid": "block-zh-voltage",
                "span_start": 3,
                "span_end": 45,
                "snippet": "电势差描述两点之间电势的差值，也称电压。",
            },
        ],
        "chinese_candidates": [
            {
                "candidate_uid": "candidate-potential",
                "text": "电势",
                "chinese_term": "电势",
                "source_uid": "source-zh",
                "chunk_uid": "chunk-zh-potential",
                "evidence_backed": True,
                "generated": False,
                "rank": 1,
                "score": 0.93,
            },
            {
                "candidate_uid": "candidate-voltage",
                "text": "电势差",
                "chinese_term": "电势差",
                "source_uid": "source-zh",
                "chunk_uid": "chunk-zh-voltage",
                "evidence_backed": True,
                "generated": False,
                "rank": 2,
                "score": 0.81,
            },
        ],
        "selected_candidate": {
            "candidate_uid": "candidate-potential",
            "text": "电势",
            "source_uid": "source-zh",
            "chunk_uid": "chunk-zh-potential",
        },
        "qualification": {
            "decision": decision,
            "reason_codes": ["INTERNAL_REASON_MUST_NOT_LEAK"],
        },
        "risk_labels": ["ambiguous_chinese_candidates"],
        "generated_hints": [],
    }


def test_ready_learning_support_is_evidence_grounded_and_non_official():
    payload = queries.serialize_alignment_result(_raw_result())
    support = payload["learning_support"]

    assert payload["contract_id"] == "student-alignment-result@1.2.0"
    assert support["contract_id"] == "student-learning-support@1.0.0"
    assert support["status"] == "EVIDENCE_GROUNDED"
    assert support["grounding_mode"] == "DETERMINISTIC_EVIDENCE_TEMPLATE"
    assert support["provider_used"] is False
    assert support["authority"] == "NON_OFFICIAL"
    assert support["what_it_means_here"]["text"].startswith("Electric potential")
    assert support["what_it_means_here"]["citations"] == [
        {
            "source_uid": "source-en",
            "chunk_uid": "chunk-en-potential",
            "page_number": 3,
            "block_uid": "block-en-potential",
        }
    ]
    assert support["why_they_align"]["status"] == "EVIDENCE_BACKED"
    assert {item["language"] for item in support["why_they_align"]["evidence"]} == {
        "en",
        "zh",
    }
    assert "课程官方" not in support["why_they_align"]["summary"]


def test_alternatives_carry_bounded_source_evidence_without_internal_scores():
    payload = queries.serialize_alignment_result(_raw_result())
    support = payload["learning_support"]

    assert [item["term"] for item in support["alternatives"]] == ["电势差"]
    alternative = support["alternatives"][0]
    assert alternative["evidence_backed"] is True
    assert alternative["evidence"]["source_uid"] == "source-zh"
    assert alternative["evidence"]["chunk_uid"] == "chunk-zh-voltage"
    assert alternative["evidence"]["snippet"].startswith("电势差描述")
    assert len(alternative["evidence"]["snippet"]) <= 360
    serialized = json.dumps(support, ensure_ascii=False)
    assert '"score"' not in serialized
    assert "INTERNAL_REASON_MUST_NOT_LEAK" not in serialized


def test_concept_differentiation_is_side_by_side_and_does_not_invent_a_boundary():
    support = queries.serialize_alignment_result(_raw_result())["learning_support"]
    comparisons = support["do_not_confuse_with"]

    assert len(comparisons) == 1
    comparison = comparisons[0]
    assert comparison["recommended_term"] == "电势"
    assert comparison["alternative_term"] == "电势差"
    assert comparison["comparison_mode"] == "EVIDENCE_SIDE_BY_SIDE"
    assert comparison["boundary_conclusion"] == "UNRESOLVED"
    assert comparison["recommended_evidence"]["snippet"].startswith("电势表示")
    assert comparison["alternative_evidence"]["snippet"].startswith("电势差描述")
    assert "不足以安全概括" in comparison["student_message"]


def test_review_required_keeps_all_candidates_tentative_and_viewable():
    raw = _raw_result("REVIEW_REQUIRED")
    payload = queries.serialize_alignment_result(raw)
    support = payload["learning_support"]

    assert payload["alignment_status"] == "REVIEW_REQUIRED"
    assert payload["uncertain"] is True
    assert support["status"] == "ALTERNATIVES_UNRESOLVED"
    assert support["why_they_align"]["status"] == "UNRESOLVED"
    assert support["recommendation_claim"] == "TENTATIVE"
    assert {item["term"] for item in support["candidate_evidence"]} == {
        "电势",
        "电势差",
    }
    assert "无法唯一确认" in support["why_they_align"]["summary"]


def test_not_ready_has_no_alignment_rationale_or_concept_comparison():
    raw = _raw_result("REJECTED")
    raw["generated_hints"] = [
        {
            "text": "电位",
            "generated": True,
            "no_evidence": True,
            "provenance_type": "GENERATED_HINT",
            "provider_id": "offline-hint",
            "provider_version": "1",
        }
    ]
    payload = queries.serialize_alignment_result(raw)
    support = payload["learning_support"]

    assert payload["alignment_status"] == "NOT_READY"
    assert payload["recommended_chinese_concept"] is None
    assert support["status"] == "NO_RELIABLE_ALIGNMENT"
    assert support["why_they_align"]["status"] == "UNAVAILABLE"
    assert support["candidate_evidence"] == []
    assert support["alternatives"] == []
    assert support["do_not_confuse_with"] == []
    assert payload["generated_hints"][0]["evidence_backed"] is False


def test_candidate_without_allowed_chinese_provenance_cannot_enter_learning_support():
    raw = _raw_result()
    raw["chinese_candidates"].append(
        {
            "candidate_uid": "candidate-forged",
            "text": "伪造候选",
            "source_uid": "unknown-source",
            "chunk_uid": "unknown-chunk",
            "evidence_backed": True,
            "generated": False,
        }
    )
    support = queries.serialize_alignment_result(raw)["learning_support"]

    assert "伪造候选" not in {
        item["term"] for item in support["candidate_evidence"]
    }
    assert "伪造候选" not in {
        item["term"] for item in support["alternatives"]
    }


@pytest.mark.parametrize("scope", ["PERSONAL", "MANAGED_COURSE"])
def test_workspaces_share_the_same_learning_support_contract(scope):
    support = queries.serialize_alignment_result(
        _raw_result(workspace_scope=scope)
    )["learning_support"]
    assert support["contract_id"] == "student-learning-support@1.0.0"
    assert support["workspace_behavior"] == "SHARED_STUDENT_EXPERIENCE"


def test_learning_support_is_deterministic_and_contains_no_evaluation_answers():
    raw = _raw_result()
    first = queries.serialize_alignment_result(raw)["learning_support"]
    second = queries.serialize_alignment_result(raw)["learning_support"]
    assert first == second
    serialized = json.dumps(first, ensure_ascii=False).lower()
    for forbidden in (
        "gold.json",
        "accepted_chinese_aliases",
        "required_propositions",
        "benchmark concept",
    ):
        assert forbidden not in serialized
