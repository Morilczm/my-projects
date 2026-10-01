from scripts.evaluations.bilingual_knowledge_quality import metrics


def _gold(concept_id, english, chinese, *, en_refs=None, zh_refs=None):
    return metrics.GoldConcept(
        concept_id=concept_id,
        english_term=english,
        accepted_chinese_terms=tuple(chinese),
        rejected_confusions=("冲量", "力矩"),
        required_english_evidence_ids=tuple(en_refs or (f"{concept_id}-en",)),
        required_chinese_evidence_ids=tuple(zh_refs or (f"{concept_id}-zh",)),
        required_propositions=("definition",),
        forbidden_claims=("unsupported energy equivalence",),
        domain="mechanics",
    )


def test_top_k_metrics_count_missing_results_in_denominator():
    gold = [
        _gold("physics-01", "momentum", ("动量",), en_refs=("en-momentum",), zh_refs=("zh-momentum",)),
        _gold("physics-02", "impulse", ("冲量",), en_refs=("en-impulse",), zh_refs=("zh-impulse",)),
    ]
    results = {
        "physics-01": metrics.SystemConceptResult(
            concept_id="physics-01",
            english_term="momentum",
            chinese_term="动量",
            chinese_candidates=("动量", "冲量"),
            english_evidence_ids=("wrong", "en-momentum"),
            chinese_evidence_ids=("zh-momentum",),
            explanation_score=2,
            unsupported_claim_count=0,
            contradiction_count=0,
            source_reference_complete=True,
            chunk_reference_complete=True,
        )
    }

    summary = metrics.compute_quality_metrics(gold, results)

    assert summary["evaluated_concept_count"] == 2
    assert summary["candidate_recall"] == 0.5
    assert summary["english_hit_at_1"] == 0.0
    assert summary["english_hit_at_3"] == 0.5
    assert summary["missing_result_count"] == 1


def test_chinese_term_metrics_accept_aliases_but_reject_confusions():
    gold = [
        _gold("physics-01", "momentum", ("动量",)),
        _gold("physics-02", "torque", ("力矩", "转矩")),
    ]
    results = {
        "physics-01": metrics.SystemConceptResult(
            concept_id="physics-01",
            english_term="momentum",
            chinese_term="冲量",
            chinese_candidates=("冲量", "动量"),
            english_evidence_ids=("physics-01-en",),
            chinese_evidence_ids=("physics-01-zh",),
        ),
        "physics-02": metrics.SystemConceptResult(
            concept_id="physics-02",
            english_term="torque",
            chinese_term="转矩",
            chinese_candidates=("角动量", "转矩"),
            english_evidence_ids=("physics-02-en",),
            chinese_evidence_ids=("physics-02-zh",),
        ),
    }

    summary = metrics.compute_quality_metrics(gold, results)
    momentum = summary["concept_results"]["physics-01"]
    torque = summary["concept_results"]["physics-02"]

    assert momentum["top1_chinese_term_correct"] is False
    assert momentum["top3_chinese_term_correct"] is True
    assert momentum["critical_confusion"] is True
    assert torque["term_pair_correct"] is True
    assert summary["chinese_term_top1_accuracy"] == 0.5
    assert summary["chinese_term_top3_accuracy"] == 1.0
    assert summary["critical_confusion_count"] == 1


def test_evidence_completeness_requires_independent_english_and_chinese_refs():
    gold = [_gold("physics-01", "momentum", ("动量",), en_refs=("en-def",), zh_refs=("zh-def",))]
    results = {
        "physics-01": metrics.SystemConceptResult(
            concept_id="physics-01",
            english_term="momentum",
            chinese_term="动量",
            chinese_candidates=("动量",),
            english_evidence_ids=("en-def",),
            chinese_evidence_ids=("wrong-zh",),
            explanation_score=2,
            unsupported_claim_count=0,
            contradiction_count=0,
            source_reference_complete=True,
            chunk_reference_complete=True,
        )
    }

    summary = metrics.compute_quality_metrics(gold, results)
    concept = summary["concept_results"]["physics-01"]

    assert concept["english_evidence_hit_at_3"] is True
    assert concept["chinese_evidence_hit_at_3"] is False
    assert concept["bilingual_evidence_complete"] is False
    assert summary["bilingual_evidence_completeness"] == 0.0


def test_review_proxy_distinguishes_approve_edit_and_reject():
    gold = [
        _gold("approve", "velocity", ("速度",)),
        _gold("edit", "acceleration", ("加速度",)),
        _gold("reject", "work", ("功",)),
    ]
    results = {
        "approve": metrics.SystemConceptResult(
            concept_id="approve",
            english_term="velocity",
            chinese_term="速度",
            chinese_candidates=("速度",),
            english_evidence_ids=("approve-en",),
            chinese_evidence_ids=("approve-zh",),
            explanation_score=2,
            unsupported_claim_count=0,
            contradiction_count=0,
            source_reference_complete=True,
            chunk_reference_complete=True,
        ),
        "edit": metrics.SystemConceptResult(
            concept_id="edit",
            english_term="acceleration",
            chinese_term="加速度",
            chinese_candidates=("加速度",),
            english_evidence_ids=("edit-en",),
            chinese_evidence_ids=("edit-zh",),
            explanation_score=1,
            unsupported_claim_count=0,
            contradiction_count=0,
            source_reference_complete=True,
            chunk_reference_complete=True,
        ),
        "reject": metrics.SystemConceptResult(
            concept_id="reject",
            english_term="work",
            chinese_term="能量",
            chinese_candidates=("能量",),
            english_evidence_ids=("reject-en",),
            chinese_evidence_ids=("reject-zh",),
            explanation_score=2,
            unsupported_claim_count=0,
            contradiction_count=0,
            source_reference_complete=True,
            chunk_reference_complete=True,
        ),
    }

    summary = metrics.compute_quality_metrics(gold, results)

    assert summary["concept_results"]["approve"]["review_proxy_decision"] == "approve"
    assert summary["concept_results"]["edit"]["review_proxy_decision"] == "edit"
    assert summary["concept_results"]["reject"]["review_proxy_decision"] == "reject"
    assert summary["approve_proxy_rate"] == 1 / 3
    assert summary["edit_proxy_rate"] == 1 / 3
    assert summary["reject_proxy_rate"] == 1 / 3


def test_failure_attribution_prefers_earliest_observed_stage():
    gold = [_gold("physics-01", "momentum", ("动量",))]
    result = metrics.SystemConceptResult(
        concept_id="physics-01",
        english_term="momentum",
        chinese_term="",
        chinese_candidates=(),
        english_evidence_ids=("physics-01-en",),
        chinese_evidence_ids=(),
        explanation_score=0,
        unsupported_claim_count=2,
        contradiction_count=1,
        source_reference_complete=True,
        chunk_reference_complete=True,
        workflow_error="",
    )

    concept = metrics.score_concept(gold[0], result)

    assert concept["primary_failure_attribution"] == "CHINESE_CANDIDATE_DEFECT"
    assert "CHINESE_RETRIEVAL_DEFECT" in concept["secondary_failure_attributions"]
    assert "EXPLANATION_GENERATION_DEFECT" in concept["secondary_failure_attributions"]


def test_artifact_sanitizer_removes_secrets_and_full_source_text():
    artifact = {
        "api_key": "sk-secret",
        "headers": {"Authorization": "Bearer secret"},
        "full_source_text": "Momentum is repeated in a long source.",
        "bounded_evidence_snippet": "Momentum is the product of mass and velocity.",
        "nested": [{"token": "secret-token", "chunk_uid": "chunk-1"}],
    }

    safe = metrics.sanitize_artifact(artifact)

    assert safe["api_key"] == "[REDACTED]"
    assert safe["headers"]["Authorization"] == "[REDACTED]"
    assert "full_source_text" not in safe
    assert safe["bounded_evidence_snippet"] == "Momentum is the product of mass and velocity."
    assert safe["nested"][0]["token"] == "[REDACTED]"
