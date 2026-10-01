"""English term candidate quality heuristics.

A set of pure, dependency-free filters and scoring signals for English term
candidates: given a candidate string they report pass/reject with reasons
(``candidate_quality_flags``) or a bounded quality score
(``term_quality_score``). These heuristics reject full sentences, verb
phrases, OCR placeholders, and merged OCR artifacts such as "convertsa
signal" without depending on any external extractor.
"""

from __future__ import annotations

import re


PLACEHOLDER_PATTERN = re.compile(
    r"\b(?:ocr_required|ocr\s+required)\b",
    re.IGNORECASE,
)

TOKEN_PATTERN = re.compile(r"[a-z]+", re.IGNORECASE)

BAD_START_WORDS = {
    "the", "this", "that", "these", "those",
    "a", "an", "and", "or", "but",
    "if", "when", "where", "why", "how", "what", "which",
    "we", "you", "they", "he", "she", "it",
    "suppose", "choose", "find", "show", "prove", "let",
    "in", "on", "at", "for", "with", "by", "from", "to", "of",
    "as", "is", "are", "was", "were",
}

BAD_END_WORDS = {
    "the", "a", "an", "and", "or", "but",
    "is", "are", "was", "were", "be", "been",
    "in", "on", "at", "for", "with", "by", "from", "to", "of",
    "this", "that", "these", "those", "each",
}

FINITE_VERBS = {
    "be", "been", "being", "is", "are", "was", "were",
    "can", "will", "would", "could", "should", "may", "might", "must",
    "have", "has", "had", "do", "does", "did",
    "converts", "converted", "converting",
    "maps", "mapped", "mapping",
    "stores", "stored", "storing",
    "uses", "used", "using",
    "returns", "returned", "returning",
    "computes", "computed", "computing",
    "calculates", "calculated", "calculating",
    "represents", "represented", "representing",
    "refers", "referred", "referring",
    "defines", "defined", "defining",
    "contains", "contained", "containing",
    "consists", "consisted", "consisting",
    "produces", "produced", "producing",
    "generates", "generated", "generating",
    "describes", "described", "describing",
    "appears", "appeared", "appearing",
    "sorts", "sorted", "sorting",
    "searches", "searched", "searching",
    "inserts", "inserted", "inserting",
    "deletes", "deleted", "deleting",
    "builds", "built", "building",
    "divides", "divided", "dividing",
    "runs", "ran", "running",
    "works", "worked", "working",
}

FRAGMENT_CONNECTORS = {
    "after", "again", "as", "because", "before", "during",
    "if", "than", "then", "while", "when", "where",
}

DESCRIPTIVE_FRAGMENT_WORDS = {
    "final", "less", "more", "most", "much", "least",
}

MORPHOLOGY_SUFFIXES = (
    "tion", "sion", "ment", "ness", "ity", "ics",
    "ism", "ance", "ence", "ing", "al", "ive", "ous",
)

DEFINITION_CLUES = (
    "is called", "is defined as", "means", "refers to",
    "denoted by", "known as", "consists of",
)

OCR_MERGED_ARTICLE_PATTERN = re.compile(
    r"^(?:convert|map|store|use|return|compute|calculate|represent|refer|define|contain|consist|produce|generate|describe|sort|search|insert|delete)s?(?:a|an|the)$"
)


def normalize_space(value):
    return re.sub(r"\s+", " ", value or "").strip()


def has_blocking_placeholder(text):
    return bool(PLACEHOLDER_PATTERN.search(text or ""))


def token_words(term):
    return [token.lower() for token in TOKEN_PATTERN.findall(term or "")]


def looks_like_ocr_merged_article(token):
    return bool(OCR_MERGED_ARTICLE_PATTERN.match((token or "").lower()))


def candidate_quality_flags(term):
    clean_term = normalize_space(term)
    lower = clean_term.lower()
    words = token_words(clean_term)
    flags = []

    if not clean_term:
        return ["empty"]

    if PLACEHOLDER_PATTERN.search(clean_term):
        flags.append("placeholder")

    if any(looks_like_ocr_merged_article(word) for word in words):
        flags.append("ocr_merged_article")

    if words and words[0] in BAD_START_WORDS:
        flags.append("bad_start")

    if words and words[-1] in BAD_END_WORDS:
        flags.append("bad_end")

    if words and words[0] in FRAGMENT_CONNECTORS:
        flags.append("connector_start")

    if words and words[-1] in FRAGMENT_CONNECTORS:
        flags.append("connector_end")

    if words and words[0] in FINITE_VERBS:
        flags.append("verb_phrase")

    if any(word in FINITE_VERBS for word in words[1:]):
        flags.append("sentence_fragment")

    if any(word in FRAGMENT_CONNECTORS for word in words[1:-1]):
        flags.append("connector_fragment")

    if any(word in DESCRIPTIVE_FRAGMENT_WORDS for word in words):
        flags.append("descriptive_fragment")

    if len(words) >= 4 and clean_term.islower():
        flags.append("long_lowercase_fragment")

    letters = sum(ch.isalpha() for ch in clean_term)
    digits = sum(ch.isdigit() for ch in clean_term)
    if digits > letters:
        flags.append("too_numeric")

    if "__" in lower or "==" in lower:
        flags.append("symbol_noise")

    return flags


def is_valid_term_candidate(term):
    return len(candidate_quality_flags(term)) == 0


def is_acronym(term):
    return term.isupper() and 2 <= len(term) <= 10


def is_title_case_phrase(term):
    words = term.split()

    if len(words) < 2:
        return False

    return all(word[:1].isupper() for word in words if word)


def has_morphology_signal(term):
    return any(word.lower().endswith(MORPHOLOGY_SUFFIXES) for word in term.split())


def has_definition_clue(context):
    lower_context = (context or "").lower()
    return any(clue in lower_context for clue in DEFINITION_CLUES)


def has_termhood_signal(term, count=1):
    return (
        count >= 2
        or is_title_case_phrase(term)
        or is_acronym(term)
        or "-" in term
        or has_morphology_signal(term)
    )


def term_quality_score(term, count=1, context=""):
    """Bounded 0-95 quality score from surface, frequency, and context cues."""
    words = term.split()
    score = 45

    if count >= 2:
        score += min(25, 8 + count * 3)

    if len(words) >= 2:
        score += 12

    if len(words) >= 3:
        score += 4

    if term.isupper() and len(term) >= 3:
        score += 10

    if is_title_case_phrase(term):
        score += 14

    if "-" in term:
        score += 5

    if has_morphology_signal(term):
        score += 6

    if has_definition_clue(context):
        score += 5

    return max(0, min(score, 95))
