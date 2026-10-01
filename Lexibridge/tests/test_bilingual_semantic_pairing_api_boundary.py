from services import bilingual_evidence_workflow


def test_api_query_rejects_pairing_model_and_gold_controls():
    query = bilingual_evidence_workflow.build_bilingual_evidence_query({
        "english_term": "electric potential",
        "english_context": "energy per unit charge",
        "discipline": "physics",
        "pairing_backend": "external",
        "pairing_model_path": "/tmp/arbitrary-model",
        "reranker_backend": "external",
        "reranker_model_path": "/tmp/arbitrary-reranker",
        "gold_chinese_term": "禁止值",
        "accepted_chinese_aliases": ["禁止别名"],
        "required_propositions": ["禁止命题"],
    })
    for key in (
        "pairing_backend",
        "pairing_model_path",
        "reranker_backend",
        "reranker_model_path",
        "gold_chinese_term",
        "accepted_chinese_aliases",
        "required_propositions",
    ):
        assert key not in query


def test_pairing_query_context_is_bounded():
    query = bilingual_evidence_workflow.build_bilingual_evidence_query({
        "english_term": "mass",
        "english_context": "x" * 5000,
        "discipline": "physics",
    })
    assert len(query["english_context"]) <= 800
