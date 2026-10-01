from services.alignment import finalize_alignment_decision
from services.text_normalization import normalize_term


def build_terminology_card_from_candidate(
    candidate,
    english_evidence,
    chinese_evidence,
    ai_result,
    alignment_run=None,
    min_ocr_confidence=100,
    formula_status="",
    formula_blocks=None,
    provider_metadata=None,
):
    """
    Build a persistence-ready TerminologyCard payload without touching the database.
    The API layer can pass this payload to its ORM update function.
    """
    candidate = candidate or {}
    ai_result = ai_result or {}
    provider_metadata = provider_metadata or {}
    english_term = str(candidate.get("english_term") or ai_result.get("english_term") or "").strip()
    final_chinese = str(ai_result.get("final_chinese_term") or ai_result.get("chinese_term") or "").strip()
    alignment = {
        "english_term": english_term,
        "final_chinese_term": final_chinese,
        "chinese_term": final_chinese,
        "ai_translation_candidate": ai_result.get("ai_translation_candidate", final_chinese),
        "courseware_sentence": candidate.get("context_sentence") or candidate.get("context") or ai_result.get("courseware_sentence", ""),
        "explanation": ai_result.get("explanation", ""),
        "alignment_reason": ai_result.get("alignment_reason", ""),
        "alignment_status": ai_result.get("alignment_status", "unverified_translation"),
        "confidence_score": ai_result.get("confidence_score", ai_result.get("confidence", 0)),
        "english_evidence_items": english_evidence or [],
        "chinese_evidence_items": chinese_evidence or [],
        "term_quality_score": candidate.get("confidence", candidate.get("term_quality_score", 86)) / 100
        if isinstance(candidate.get("confidence"), int)
        else candidate.get("term_quality_score", 0.86),
        "formula_status": formula_status,
        "formula_blocks": formula_blocks or [],
        "risk_note": ai_result.get("risk_note", ""),
        "ai_provider": provider_metadata.get("ai_provider", ai_result.get("ai_provider", "")),
        "ai_model": provider_metadata.get("ai_model", ai_result.get("ai_model", "")),
        "provider_status": provider_metadata.get("provider_status", ai_result.get("provider_status", "")),
        "prompt_version": provider_metadata.get("prompt_version", ai_result.get("prompt_version", "alignment_v1")),
        "retrieval_version": provider_metadata.get("retrieval_version", ai_result.get("retrieval_version", "local_lexical_v1")),
    }
    if alignment_run is not None:
        run_id = getattr(alignment_run, "id", alignment_run)
        alignment["alignment_run_id"] = run_id
        alignment["source_alignment_run_id"] = run_id

    finalized = finalize_alignment_decision(alignment, min_ocr_confidence=min_ocr_confidence)
    finalized["normalized_english_term"] = normalize_term(english_term)
    finalized["normalized_chinese_term"] = normalize_term(final_chinese)
    return finalized
