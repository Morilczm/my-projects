from services.text_normalization import (
    alias_terms_for_query,
    core_tokens,
    expanded_core_tokens,
    normalize_term,
)


SIGNAL_TERMS = {
    "fourier", "transform", "convolution", "signal", "frequency", "domain",
    "angular", "wavelength", "wave", "radians", "phase", "time",
    "傅里叶", "变换", "卷积", "信号", "频率", "角频率", "波长", "时域", "频域",
}

DATA_STRUCTURE_TERMS = {
    "hash", "table", "bucket", "buckets", "key", "keys", "collision", "resolution",
    "binary", "search", "tree", "stack", "哈希", "哈希表", "散列", "关键字", "桶",
    "冲突", "二叉", "搜索树", "栈",
}


def infer_domain_from_tokens(tokens):
    token_set = set(tokens)
    signal_hits = len(token_set & SIGNAL_TERMS)
    data_hits = len(token_set & DATA_STRUCTURE_TERMS)
    if signal_hits and signal_hits > data_hits:
        return "signal_processing"
    if data_hits and data_hits > signal_hits:
        return "data_structures"
    return ""


def term_exact_or_alias_match(query, content):
    normalized_query = normalize_term(query)
    normalized_content = normalize_term(content)
    if normalized_query and normalized_query in normalized_content:
        return 1.0
    for alias in alias_terms_for_query(query):
        alias_norm = normalize_term(alias)
        if alias_norm and alias_norm in normalized_content:
            return 1.0
    query_tokens = set(expanded_core_tokens(query))
    content_tokens = set(expanded_core_tokens(content))
    if not query_tokens:
        return 0.0
    overlap = query_tokens & content_tokens
    if not overlap:
        return 0.0
    ratio = len(overlap) / len(query_tokens)
    if ratio >= 0.75:
        return 0.8
    return 0.5 if ratio >= 0.5 else 0.0


def lexical_overlap_score(query, content, context=None):
    query_tokens = set(expanded_core_tokens(query))
    if context:
        query_tokens.update(expanded_core_tokens(context))
    content_tokens = set(expanded_core_tokens(content))
    if not query_tokens or not content_tokens:
        return 0.0
    overlap = query_tokens & content_tokens
    if not overlap:
        return 0.0
    core_query_tokens = set(expanded_core_tokens(query))
    core_overlap = overlap & core_query_tokens
    weighted = len(overlap) + len(core_overlap)
    denominator = len(query_tokens) + max(1, len(core_query_tokens))
    return round(min(weighted / denominator, 1.0), 4)


def course_scope_score(chunk, course_id=None):
    visibility = str(getattr(chunk, "visibility", "") or "").lower()
    chunk_course_id = getattr(chunk, "course_id", None)
    if visibility == "global":
        return 0.7
    if visibility == "private":
        return 1.0
    if course_id is None:
        return 0.5
    return 1.0 if str(chunk_course_id) == str(course_id) else 0.0


def discipline_match_score(query, chunk, discipline=None):
    query_domain = infer_domain_from_tokens(expanded_core_tokens(query))
    chunk_text = " ".join([
        str(getattr(chunk, "discipline", "") or ""),
        str(getattr(chunk, "chapter", "") or ""),
        str(getattr(chunk, "title", "") or ""),
        str(getattr(chunk, "keywords", "") or ""),
        str(getattr(chunk, "content", "") or ""),
    ])
    chunk_domain = infer_domain_from_tokens(expanded_core_tokens(chunk_text))
    if discipline:
        discipline_domain = infer_domain_from_tokens(expanded_core_tokens(discipline))
        if query_domain and discipline_domain and query_domain != discipline_domain:
            return 0.0, ["domain_mismatch"]
    if query_domain and chunk_domain and query_domain != chunk_domain:
        return 0.0, ["domain_mismatch"]
    if query_domain and chunk_domain == query_domain:
        return 1.0, []
    return 0.5, []


def source_quality_score(chunk):
    explicit_quality = getattr(chunk, "_source_quality", None)
    if explicit_quality is not None:
        try:
            flags = list(getattr(chunk, "_source_governance_flags", []) or [])
            return max(0.0, min(float(explicit_quality), 1.0)), flags
        except (TypeError, ValueError):
            pass
    source_type = str(getattr(chunk, "_source_type", "") or getattr(chunk, "source_type", "") or "").lower()
    license_status = str(getattr(chunk, "_license_status", "") or getattr(chunk, "license_status", "") or "").lower()
    allow_derivative = getattr(chunk, "_allow_derivative_cards", None)
    if license_status == "restricted" and allow_derivative is False:
        return 0.0, ["restricted_without_derivative_permission"]
    if source_type in {"authorized_textbook", "textbook"} or license_status == "authorized":
        return 1.0, []
    if source_type in {"teacher_upload", "lecture_notes"}:
        return 0.9, []
    if source_type == "platform_seed" or license_status in {"open_licensed", "public_domain"}:
        return 0.7, []
    return 0.4, []


def score_knowledge_chunk(query, chunk, context=None, course_id=None, discipline=None):
    content = str(getattr(chunk, "content", "") or "")
    exact_score = term_exact_or_alias_match(query, content)
    lexical_score = lexical_overlap_score(query, content, context=context)
    semantic_score = 0.0
    scope_score = course_scope_score(chunk, course_id=course_id)
    discipline_score, discipline_flags = discipline_match_score(query, chunk, discipline=discipline)
    source_score, source_flags = source_quality_score(chunk)

    risk_flags = []
    risk_flags.extend(discipline_flags)
    risk_flags.extend(source_flags)

    if exact_score == 0 and lexical_score < 0.20:
        risk_flags.append("insufficient_core_token_overlap")
    if scope_score == 0:
        risk_flags.append("wrong_course_scope")

    evidence_score = (
        0.30 * exact_score
        + 0.20 * lexical_score
        + 0.20 * semantic_score
        + 0.15 * scope_score
        + 0.10 * discipline_score
        + 0.05 * source_score
    )

    return {
        "evidence_score": round(max(0.0, min(evidence_score, 1.0)), 4),
        "score_breakdown": {
            "term_exact_or_alias_match": round(exact_score, 4),
            "lexical_overlap_score": round(lexical_score, 4),
            "semantic_similarity_score": round(semantic_score, 4),
            "course_scope_score": round(scope_score, 4),
            "discipline_match_score": round(discipline_score, 4),
            "source_quality_score": round(source_score, 4),
        },
        "risk_flags": sorted(set(risk_flags)),
    }


RISK_PENALTIES_POINTS = {
    "no_zh_evidence": 40,
    "no_en_evidence": 40,
    "domain_mismatch": 50,
    "ocr_low_confidence": 25,
    "formula_evidence_missing": 25,
    "mock_or_local_ai": 30,
    "model_not_evaluated": 30,
    "ambiguous_candidate": 20,
    "multi_translation_conflict": 30,
    "invalid_term_candidate": 60,
    "weak_evidence": 15,
    "unverified_translation": 35,
}


def _clamp_unit(value):
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = 0.0
    return max(0.0, min(numeric, 1.0))


def calculate_confidence_score(
    term_quality_score,
    english_evidence_score,
    chinese_evidence_score,
    ai_alignment_score,
    course_scope_score,
    source_quality_score,
    risk_flags,
):
    """
    Final card confidence is intentionally separate from retrieval evidence score.
    Inputs are 0-1 quality signals; risk penalties are direct 0-100 point deductions.
    """
    flags = sorted({str(flag) for flag in (risk_flags or []) if str(flag).strip()})
    term_quality = _clamp_unit(term_quality_score)
    english_score = _clamp_unit(english_evidence_score)
    chinese_score = _clamp_unit(chinese_evidence_score)
    ai_score = _clamp_unit(ai_alignment_score)
    course_scope = _clamp_unit(course_scope_score)
    source_quality = _clamp_unit(source_quality_score)

    weighted = (
        0.25 * term_quality
        + 0.25 * english_score
        + 0.25 * chinese_score
        + 0.15 * ai_score
        + 0.05 * course_scope
        + 0.05 * source_quality
    )
    risk_penalty = sum(RISK_PENALTIES_POINTS.get(flag, 0) for flag in flags)
    confidence = int(round(weighted * 100 - risk_penalty))
    confidence = max(0, min(confidence, 100))

    return {
        "confidence_score": confidence,
        "score_breakdown": {
            "term_quality_score": round(term_quality, 4),
            "english_evidence_score": round(english_score, 4),
            "chinese_evidence_score": round(chinese_score, 4),
            "ai_alignment_score": round(ai_score, 4),
            "course_scope_score": round(course_scope, 4),
            "source_quality_score": round(source_quality, 4),
            "risk_penalty": risk_penalty,
        },
        "risk_flags": flags,
    }
