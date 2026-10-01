import json
from pathlib import Path

from services.text_normalization import normalize_term


VALID_SPLITS = {"train", "dev", "test"}
OCR_NOISE_MARKERS = {
    "ocr_required",
    "ocr_fallback",
    "[ocr_required]",
    "[ocr_fallback]",
}


def read_evaluation_jsonl(file_path):
    records = []
    errors = []
    path = Path(file_path)
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                errors.append({
                    "line": line_number,
                    "error": str(exc),
                    "content": line[:200],
                })
    return records, errors


def normalize_evaluation_record(record):
    split = str(record.get("split", "test") or "test").strip().lower()
    if split not in VALID_SPLITS:
        split = "test"
    tags = record.get("tags", record.get("tags_json", []))
    if isinstance(tags, str):
        try:
            tags = json.loads(tags)
        except Exception:
            tags = [item.strip() for item in tags.split(",") if item.strip()]
    return {
        "item_id": str(record.get("item_id", "")).strip(),
        "split": split,
        "discipline": str(record.get("discipline", "")).strip(),
        "course_id": record.get("course_id"),
        "english_term": str(record.get("english_term", "")).strip(),
        "expected_chinese_term": str(record.get("expected_chinese_term", "")).strip(),
        "english_context": str(record.get("english_context", "")).strip(),
        "expected_english_evidence": str(record.get("expected_english_evidence", record.get("english_evidence", ""))).strip(),
        "expected_chinese_evidence": str(record.get("expected_chinese_evidence", record.get("chinese_evidence", ""))).strip(),
        "expected_alignment_status": str(record.get("expected_alignment_status", "")).strip(),
        "negative_english_evidence": str(record.get("negative_english_evidence", "")).strip(),
        "negative_chinese_evidence": str(record.get("negative_chinese_evidence", "")).strip(),
        "difficulty": str(record.get("difficulty", "medium")).strip() or "medium",
        "tags": tags if isinstance(tags, list) else [],
        "annotator": str(record.get("annotator", "")).strip(),
        "reviewed_by": str(record.get("reviewed_by", "")).strip(),
        "disagreement_note": str(record.get("disagreement_note", "")).strip(),
        "version": str(record.get("version", "v1")).strip() or "v1",
    }


def term_matches(expected, actual):
    expected_norm = normalize_term(expected)
    actual_norm = normalize_term(actual)
    return bool(expected_norm and actual_norm and (expected_norm == actual_norm or expected_norm in actual_norm or actual_norm in expected_norm))


def evidence_contains(expected_text, evidence_items):
    expected_norm = normalize_term(expected_text)
    if not expected_norm:
        return bool(evidence_items)
    for item in evidence_items or []:
        if not isinstance(item, dict):
            continue
        content = " ".join([
            str(item.get("content_excerpt", "")),
            str(item.get("content", "")),
            str(item.get("source_citation", "")),
            str(item.get("source_title", "")),
        ])
        content_norm = normalize_term(content)
        if expected_norm and (expected_norm in content_norm or content_norm in expected_norm):
            return True
        expected_tokens = {token for token in expected_norm.split() if len(token) > 1}
        content_tokens = set(content_norm.split())
        if expected_tokens and len(expected_tokens & content_tokens) / len(expected_tokens) >= 0.6:
            return True
    return False


def evidence_hits_negative(negative_text, evidence_items):
    negative_norm = normalize_term(negative_text)
    if not negative_norm:
        return False
    for item in evidence_items or []:
        content = normalize_term(" ".join([
            str(item.get("content_excerpt", "")),
            str(item.get("content", "")),
        ]))
        if negative_norm and negative_norm in content:
            return True
    return False


def is_ocr_noise_term(term):
    normalized = normalize_term(term).lower()
    if not normalized:
        return False
    if normalized in OCR_NOISE_MARKERS:
        return True
    return "ocr required" in normalized or "ocr fallback" in normalized


def evaluate_single_item(item, extracted_terms, alignment_result):
    extracted_terms = extracted_terms or []
    alignment_result = alignment_result or {}
    english_evidence = alignment_result.get("english_evidence_items") or []
    chinese_evidence = alignment_result.get("chinese_evidence_items") or []
    expected_term = item.get("english_term", "")
    expected_chinese = item.get("expected_chinese_term", "")
    expected_status = item.get("expected_alignment_status", "")

    extracted_count = len(extracted_terms)
    expected_found = any(term_matches(expected_term, term.get("english_term", term) if isinstance(term, dict) else term) for term in extracted_terms)
    correct_extracted = 1 if expected_found else 0
    ocr_noise_count = sum(1 for term in extracted_terms if is_ocr_noise_term(term.get("english_term", term) if isinstance(term, dict) else term))

    english_returned = bool(english_evidence)
    chinese_returned = bool(chinese_evidence)
    english_correct = evidence_contains(item.get("expected_english_evidence", ""), english_evidence)
    chinese_correct = evidence_contains(item.get("expected_chinese_evidence", ""), chinese_evidence)
    negative_hit = evidence_hits_negative(item.get("negative_english_evidence", ""), english_evidence) or evidence_hits_negative(item.get("negative_chinese_evidence", ""), chinese_evidence)
    actual_status = alignment_result.get("alignment_status", "")
    card_status = alignment_result.get("review_status", alignment_result.get("status", ""))
    alignment_correct = bool(expected_status and actual_status == expected_status)
    expected_chinese_hit = term_matches(expected_chinese, alignment_result.get("final_chinese_term", ""))
    wrongly_auto = card_status == "auto_approved" and expected_status not in {"exact_match", "accepted_translation"}
    forced_alignment = (
        (not english_returned or not chinese_returned)
        and (actual_status in {"exact_match", "accepted_translation"} or card_status == "auto_approved")
    )

    failure_reasons = []
    if not expected_found:
        failure_reasons.append("expected term not extracted")
    if english_returned and not english_correct:
        failure_reasons.append("english evidence mismatch")
    if chinese_returned and not chinese_correct:
        failure_reasons.append("chinese evidence mismatch")
    if negative_hit:
        failure_reasons.append("negative evidence matched")
    if not alignment_correct:
        failure_reasons.append("alignment status mismatch")
    if wrongly_auto:
        failure_reasons.append("wrong auto approval")
    if forced_alignment:
        failure_reasons.append("no evidence forced alignment")
    if ocr_noise_count:
        failure_reasons.append("OCR noise term extracted")

    return {
        "item_id": item.get("item_id") or str(item.get("id", "")),
        "english_term": expected_term,
        "expected_chinese_term": expected_chinese,
        "expected_alignment_status": expected_status,
        "actual_chinese_term": alignment_result.get("final_chinese_term", ""),
        "actual_alignment_status": actual_status,
        "card_status": card_status,
        "confidence_score": alignment_result.get("confidence_score", 0),
        "quality_flags": alignment_result.get("quality_flags", []),
        "system_extracted_term_count": extracted_count,
        "correct_extracted_term_count": correct_extracted,
        "expected_term_found": expected_found,
        "english_evidence_returned": english_returned,
        "chinese_evidence_returned": chinese_returned,
        "english_evidence_correct": english_correct,
        "chinese_evidence_correct": chinese_correct,
        "alignment_status_correct": alignment_correct,
        "expected_chinese_term_found": expected_chinese_hit,
        "wrongly_auto_approved": wrongly_auto,
        "no_evidence_forced_alignment": forced_alignment,
        "ocr_noise_detected": bool(ocr_noise_count),
        "ocr_term_candidate_count": ocr_noise_count,
        "ocr_noise_term_count": ocr_noise_count,
        "retrieval_error": "negative evidence matched" if negative_hit else "",
        "failure_reason": "; ".join(failure_reasons),
        "english_evidence_items": english_evidence,
        "chinese_evidence_items": chinese_evidence,
    }
