import pytest

from services.term_candidate_quality import (
    candidate_quality_flags,
    has_blocking_placeholder,
    has_definition_clue,
    has_morphology_signal,
    has_termhood_signal,
    is_acronym,
    is_title_case_phrase,
    is_valid_term_candidate,
    looks_like_ocr_merged_article,
    normalize_space,
    term_quality_score,
)


def test_clean_multiword_term_passes():
    assert is_valid_term_candidate("Fourier Transform")
    assert is_valid_term_candidate("Hash Table")
    assert candidate_quality_flags("Fourier Transform") == []


@pytest.mark.parametrize(
    "term,flag",
    [
        ("the Fourier Transform", "bad_start"),
        ("Fourier Transform is", "bad_end"),
        ("converts a signal", "verb_phrase"),
        ("a signal is converted", "sentence_fragment"),
        ("signal before filtering", "connector_fragment"),
        ("before filtering stage", "connector_start"),
        ("filtering stage before", "connector_end"),
        ("the final output", "descriptive_fragment"),
        ("frequency domain transfer function", "long_lowercase_fragment"),
        ("123 456 78", "too_numeric"),
        ("signal__noise", "symbol_noise"),
        ("see ocr_required marker", "placeholder"),
    ],
)
def test_low_quality_candidates_are_flagged(term, flag):
    flags = candidate_quality_flags(term)

    assert flag in flags
    assert not is_valid_term_candidate(term)


def test_empty_candidate_is_flagged():
    assert candidate_quality_flags("") == ["empty"]
    assert candidate_quality_flags("   ") == ["empty"]


def test_ocr_merged_article_detection():
    assert looks_like_ocr_merged_article("convertsa")
    assert looks_like_ocr_merged_article("storesthe")
    assert looks_like_ocr_merged_article("mapan")
    assert not looks_like_ocr_merged_article("conversion")
    assert not looks_like_ocr_merged_article("signal")
    assert "ocr_merged_article" in candidate_quality_flags("convertsa signal")


def test_blocking_placeholder():
    assert has_blocking_placeholder("this page needs ocr required here")
    assert has_blocking_placeholder("OCR_REQUIRED")
    assert not has_blocking_placeholder("Fourier Transform")


def test_normalize_space():
    assert normalize_space("  Fourier\n\tTransform  ") == "Fourier Transform"
    assert normalize_space(None) == ""


def test_acronym_and_title_case_signals():
    assert is_acronym("FFT")
    assert not is_acronym("Fourier")
    assert not is_acronym("TOOLONGACRONYM")
    assert is_title_case_phrase("Fourier Transform")
    assert not is_title_case_phrase("fourier transform")
    assert not is_title_case_phrase("Fourier")


def test_morphology_suffix_signals():
    assert has_morphology_signal("signal transformation")
    assert has_morphology_signal("hash randomness")
    assert not has_morphology_signal("Fourier Transform")


def test_definition_clue_detection():
    assert has_definition_clue("The Fourier Transform is defined as an integral.")
    assert has_definition_clue("A hash table refers to a data structure.")
    assert not has_definition_clue("We use the Fourier Transform often.")


def test_termhood_signal():
    assert has_termhood_signal("FFT")
    assert has_termhood_signal("Fourier Transform")
    assert has_termhood_signal("back-propagation")
    assert has_termhood_signal("anything", count=2)
    assert not has_termhood_signal("fourier", count=1)


def test_term_quality_score_rewards_termhood_cues():
    plain = term_quality_score("fourier transform")
    titled = term_quality_score("Fourier Transform")

    assert titled > plain
    assert term_quality_score("FFT", count=3) > term_quality_score("FFT")
    assert term_quality_score("Fourier Transform", context="It is defined as an integral.") == titled + 5
    assert term_quality_score("signal transformation") == term_quality_score("hash table") + 6
    assert 0 <= term_quality_score("anything", count=100) <= 95
