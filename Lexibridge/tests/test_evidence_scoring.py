from types import SimpleNamespace

from services.scoring import score_knowledge_chunk
from services.text_normalization import core_tokens, remove_stopwords


def chunk(content, discipline="Signal Processing", course_id=1, source_type="authorized_textbook"):
    return SimpleNamespace(
        content=content,
        visibility="course",
        course_id=course_id,
        language="en",
        knowledge_base_type="en_course_kb",
        discipline=discipline,
        title=discipline,
        keywords="",
        _source_type=source_type,
        _license_status="authorized",
        _allow_derivative_cards=True,
    )


def test_stopwords_removed_from_core_tokens():
    assert remove_stopwords(["the", "fourier", "of", "transform"]) == ["fourier", "transform"]
    assert core_tokens("Fourier Transform") == ["fourier", "transform"]
    assert core_tokens("Hash Table") == ["hash", "table"]


def test_fourier_scores_strong_against_fourier_not_hash_table():
    fourier_chunk = chunk("Fourier Transform converts a time-domain signal into a frequency-domain representation.")
    hash_chunk = chunk(
        "A hash table maps keys to buckets using a hash function.",
        discipline="Data Structures"
    )

    fourier_score = score_knowledge_chunk("Fourier Transform", fourier_chunk, course_id=1)
    hash_score = score_knowledge_chunk("Fourier Transform", hash_chunk, course_id=1)

    assert fourier_score["evidence_score"] >= 0.80
    assert fourier_score["score_breakdown"]["term_exact_or_alias_match"] == 1.0
    assert hash_score["evidence_score"] < 0.65
    assert "domain_mismatch" in hash_score["risk_flags"]


def test_semantic_similarity_cannot_pass_gate_by_itself():
    unrelated = chunk(
        "The course material discusses general learning objectives and classroom activities.",
        discipline=""
    )
    score = score_knowledge_chunk("the and of", unrelated, course_id=1)
    assert score["score_breakdown"]["semantic_similarity_score"] == 0.0
    assert score["score_breakdown"]["term_exact_or_alias_match"] == 0.0
    assert score["evidence_score"] < 0.65
