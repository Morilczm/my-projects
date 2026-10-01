from dataclasses import replace

from services import bilingual_evidence_qualification as qualification
from test_bilingual_evidence_qualification_contract import _input


def test_low_margin_and_score_component_conflict_require_review():
    low_margin = qualification.qualify_bilingual_evidence(
        replace(_input(), pair_score_margin=0.01, pair_consistency_score=7.0)
    )
    conflict = qualification.qualify_bilingual_evidence(
        replace(
            _input(),
            bi_encoder_score=0.88,
            reranker_score=-0.5,
            pair_consistency_score=7.0,
        )
    )

    assert low_margin.decision == qualification.REVIEW_REQUIRED
    assert conflict.decision == qualification.REVIEW_REQUIRED
    assert qualification.EVIDENCE_PAIR_MARGIN_INSUFFICIENT in low_margin.reason_codes
    assert qualification.EVIDENCE_SCORE_COMPONENT_CONFLICT in conflict.reason_codes


def test_generic_related_but_non_equivalent_scope_pair_cannot_qualify():
    result = qualification.qualify_bilingual_evidence(
        replace(
            _input(),
            english_term="density",
            normalized_english_term="density",
            english_context="Density is the mass contained per unit volume.",
            english_evidence_span="Density is the mass contained per unit volume.",
            chinese_term="体积",
            normalized_chinese_term="体积",
            chinese_context="体积描述物体占据空间的大小。",
            chinese_evidence_span="体积描述物体占据空间的大小。",
            pair_consistency_score=3.85,
        )
    )

    assert result.decision == qualification.REVIEW_REQUIRED
    assert qualification.EVIDENCE_TERM_SCOPE_RISK in result.reason_codes


def test_generic_equivalent_pair_can_remain_qualified():
    result = qualification.qualify_bilingual_evidence(
        replace(
            _input(),
            english_term="density",
            normalized_english_term="density",
            english_context="Density is the mass contained per unit volume.",
            english_evidence_span="Density is the mass contained per unit volume.",
            chinese_term="密度",
            normalized_chinese_term="密度",
            chinese_context="密度表示单位体积中所含物质的质量。",
            chinese_evidence_span="密度表示单位体积中所含物质的质量。",
            pair_consistency_score=7.69,
        )
    )

    assert result.decision == qualification.QUALIFIED
    assert qualification.EVIDENCE_TERM_SCOPE_RISK not in result.reason_codes


def test_unknown_consistency_never_maps_to_qualified():
    result = qualification.qualify_bilingual_evidence(
        replace(_input(), pair_consistency_score=None)
    )
    assert result.decision != qualification.QUALIFIED
    assert qualification.EVIDENCE_PAIR_UNCERTAIN in result.reason_codes


def test_mass_to_impulse_is_not_qualified_and_policy_does_not_replace_it():
    result = qualification.qualify_bilingual_evidence(
        replace(
            _input(),
            english_term="mass",
            normalized_english_term="mass",
            english_context="Mass measures the amount of matter in an object.",
            english_evidence_span="Mass measures the amount of matter in an object.",
            chinese_term="冲量",
            normalized_chinese_term="冲量",
            chinese_context="冲量等于力对时间的累积作用。",
            chinese_evidence_span="冲量等于力对时间的累积作用。",
            pair_consistency_score=0.96,
        )
    )
    assert result.decision == qualification.REVIEW_REQUIRED
    assert result.chinese_provenance["chunk_uid"] == "zh-chunk-1"
    assert qualification.EVIDENCE_TERM_SCOPE_RISK in result.reason_codes
