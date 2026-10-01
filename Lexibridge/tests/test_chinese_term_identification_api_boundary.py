from pathlib import Path

from services import bilingual_evidence_workflow


ROOT = Path(__file__).resolve().parents[1]


def test_api_query_does_not_accept_gold_like_candidate_mapping():
    query = bilingual_evidence_workflow.build_bilingual_evidence_query({
        "english_term": "an English term",
        "gold_chinese_term": "禁止值",
        "accepted_chinese_aliases": ["禁止别名"],
        "required_propositions": ["禁止命题"],
        "candidate_mapping": {"x": "y"},
    })
    for key in (
        "gold_chinese_term", "accepted_chinese_aliases",
        "required_propositions", "candidate_mapping",
    ):
        assert key not in query


def test_identification_does_not_modify_retrieval_or_pairing_modules():
    service = (ROOT / "backend/services/chinese_term_candidates.py").read_text()
    assert "rank_chinese_passages" not in service
    assert "LocalMultilingualEmbeddingBackend" not in service
    assert "semantic_pair" not in service
