import pytest

from services import controlled_provider_evaluation as cpe


def _json(extra=""):
    return (
        '{"chinese_term":"特征值","chinese_explanation":"线性变换的标量因子。",'
        '"alignment_rationale":"The bounded context describes eigenvalues.",'
        '"alternative_candidates":["本征值"],"risk_labels":["provider_generated_candidate"],'
        '"abstain":false,"abstain_reason":"","provider_name":"loopback-provider",'
        '"model_name":"candidate-model","prompt_version":"provider-chinese-candidate-evaluation-v1",'
        '"output_schema_version":"provider-chinese-candidate-proposal-v1"'
        f"{extra}" "}"
    )


def test_parser_accepts_only_strict_provider_proposal_json():
    proposal = cpe.parse_provider_proposal(
        _json(),
        expected_provider="loopback-provider",
        expected_model="candidate-model",
    )

    assert proposal.chinese_term == "特征值"
    assert proposal.alternative_candidates == ("本征值",)


@pytest.mark.parametrize("raw,error_code", [
    ("```json\n{}\n```", "provider_output_code_fence"),
    (_json() + " trailing", "provider_output_not_json"),
    (_json(',"unexpected":"field"'), "provider_output_unknown_fields"),
    ("not json", "provider_output_not_json"),
    ('{"chinese_term":"x","chinese_term":"y"}', "provider_output_duplicate_key"),
])
def test_parser_rejects_untrusted_output_shapes(raw, error_code):
    with pytest.raises(cpe.ProviderProposalParserError) as exc:
        cpe.parse_provider_proposal(raw, expected_provider="loopback-provider", expected_model="candidate-model")

    assert exc.value.error_code == error_code


def test_parser_rejects_non_abstain_empty_candidate_and_unsafe_content():
    empty_candidate = _json().replace('"chinese_term":"特征值"', '"chinese_term":""')
    header_leak = _json().replace("线性变换的标量因子。", f"Authorization: Bearer {cpe.test_sentinel_value()}")

    with pytest.raises(cpe.ProviderProposalParserError) as exc:
        cpe.parse_provider_proposal(empty_candidate, expected_provider="loopback-provider", expected_model="candidate-model")
    assert exc.value.error_code == "provider_output_candidate_missing"

    with pytest.raises(cpe.ProviderProposalParserError) as exc:
        cpe.parse_provider_proposal(header_leak, expected_provider="loopback-provider", expected_model="candidate-model")
    assert exc.value.error_code == "provider_output_unsafe_content"
