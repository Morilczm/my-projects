import json

from services.scoring import calculate_confidence_score


ALIGNMENT_STATUSES = {
    "exact_match",
    "accepted_translation",
    "partial_match",
    "broader_than_source",
    "narrower_than_source",
    "ambiguous_candidate",
    "multi_translation_conflict",
    "no_en_evidence",
    "no_zh_evidence",
    "domain_mismatch",
    "ocr_low_confidence",
    "formula_evidence_missing",
    "invalid_term_candidate",
    "unverified_translation",
}


CARD_STATUSES = {
    "draft",
    "needs_more_evidence",
    "pending_quality_control",
    "conflict_detected",
    "auto_approved",
    "approved",
    "rejected",
    "archived",
}


VALID_CARD_TRANSITIONS = {
    "draft": {
        "needs_more_evidence",
        "pending_quality_control",
        "conflict_detected",
        "auto_approved",
        "rejected",
    },
    "needs_more_evidence": {"pending_quality_control", "approved"},
    "pending_quality_control": {"approved", "rejected", "needs_more_evidence"},
    "conflict_detected": {"approved", "rejected"},
    "auto_approved": {"pending_quality_control"},
    "approved": {"pending_quality_control", "archived"},
    "rejected": {"archived"},
    "archived": set(),
}


NON_LIVE_AI_PROVIDERS = {
    "",
    "mock",
    "none",
    "local_heuristic",
    "local_mock_fallback",
    "provider_failed",
    "provider_unavailable",
}


FORBIDDEN_AUTO_FLAGS = {
    "formula_evidence_missing",
    "no_en_evidence",
    "no_zh_evidence",
    "domain_mismatch",
    "ocr_low_confidence",
    "invalid_term_candidate",
    "multi_translation_conflict",
    "mock_or_local_ai",
    "model_not_evaluated",
}


FORMULA_DEPENDENT_TERMS = {
    "fourier transform",
    "convolution",
    "integral",
    "derivative",
    "laplace transform",
    "z transform",
    "gradient",
    "divergence",
}


def _as_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _items(value):
    return value if isinstance(value, list) else []


def _evidence_score(items):
    scores = [_as_float(item.get("evidence_score", item.get("score", 0))) for item in _items(items) if isinstance(item, dict)]
    return max(scores) if scores else 0.0


def _evidence_strength(items):
    score = _evidence_score(items)
    if score >= 0.80:
        return "strong"
    if score >= 0.65:
        return "weak"
    return "none"


def _collect_evidence_risk_flags(items):
    flags = set()
    for item in _items(items):
        if isinstance(item, dict):
            flags.update(str(flag) for flag in item.get("risk_flags", []) if str(flag).strip())
    return flags


def _best_score_breakdown(items):
    best = {}
    best_score = -1
    for item in _items(items):
        if not isinstance(item, dict):
            continue
        score = _as_float(item.get("evidence_score", item.get("score", 0)))
        if score > best_score:
            best_score = score
            best = item.get("score_breakdown") or {}
    return best


def evidence_snapshot(items):
    snapshots = []
    for item in _items(items):
        if not isinstance(item, dict):
            continue
        content = (
            item.get("content_excerpt")
            or item.get("content")
            or item.get("definition")
            or ""
        )
        snapshots.append({
            "chunk_id": item.get("chunk_id"),
            "source_title": item.get("source_title") or item.get("title") or item.get("source") or "",
            "source_citation": item.get("source_citation") or "",
            "page_number": item.get("page_number"),
            "language": item.get("language") or "",
            "knowledge_base_type": item.get("knowledge_base_type") or "",
            "visibility": item.get("visibility") or "",
            "content_excerpt": str(content)[:1200],
            "evidence_score": _as_float(item.get("evidence_score", item.get("score", 0))),
            "evidence_strength": item.get("evidence_strength") or _evidence_strength([item]),
            "score_breakdown": item.get("score_breakdown") or {},
            "risk_flags": item.get("risk_flags") or [],
        })
    return snapshots


def provider_is_live(ai_provider="", provider_status="", ai_model="", is_real_provider=None):
    if is_real_provider is True:
        return True
    provider = str(ai_provider or "").strip().lower()
    status = str(provider_status or "").strip().lower()
    model = str(ai_model or "").strip().lower()
    if status == "real_provider" and model and model not in NON_LIVE_AI_PROVIDERS:
        return True
    if provider in NON_LIVE_AI_PROVIDERS or status in NON_LIVE_AI_PROVIDERS or model in NON_LIVE_AI_PROVIDERS:
        return False
    return provider not in NON_LIVE_AI_PROVIDERS


def validate_card_status_transition(old_status, new_status, actor_role, system_action=False):
    old = str(old_status or "draft").strip() or "draft"
    new = str(new_status or "").strip()
    role = str(actor_role or "").strip().lower()
    if old == new:
        return True
    if old not in CARD_STATUSES or new not in CARD_STATUSES:
        return False
    if old == "rejected" and new == "auto_approved":
        return False
    if system_action and new == "auto_approved" and old != "draft":
        return False
    if new == "approved" and role not in {"teacher", "admin", "system"}:
        return False
    if new == "rejected" and role not in {"teacher", "admin", "system"}:
        return False
    return new in VALID_CARD_TRANSITIONS.get(old, set())


def can_auto_approve(card_input):
    reasons = []
    flags = set(card_input.get("risk_flags") or card_input.get("quality_flags") or [])
    confidence = _as_int(card_input.get("confidence_score"))
    term_quality = _as_float(card_input.get("term_quality_score"))
    english_score = _as_float(card_input.get("english_evidence_score"))
    chinese_score = _as_float(card_input.get("chinese_evidence_score"))
    alignment_status = str(card_input.get("alignment_status", "")).strip()
    ai_provider = str(card_input.get("ai_provider", "")).strip()
    provider_status = str(card_input.get("provider_status", "")).strip()
    ai_model = str(card_input.get("ai_model", "")).strip()
    ocr_status = str(card_input.get("ocr_status", "not_required") or "not_required").strip()
    ocr_confidence = card_input.get("ocr_confidence")

    if confidence < 85:
        reasons.append("confidence score below 85")
    if term_quality < 0.80:
        reasons.append("term quality score below 0.80")
    if english_score < 0.80:
        reasons.append("english evidence score below 0.80")
    if chinese_score < 0.80:
        reasons.append("chinese evidence score below 0.80")
    if alignment_status not in {"exact_match", "accepted_translation"}:
        reasons.append(f"alignment status {alignment_status or 'unknown'} is not auto-approvable")
    if not provider_is_live(ai_provider, provider_status, ai_model, card_input.get("is_real_provider")):
        reasons.append(f"AI provider is {ai_provider or provider_status or ai_model or 'not live'}")
    if ocr_status not in {"", "not_required", "ok"}:
        reasons.append(f"OCR status is {ocr_status}")
    if ocr_confidence is not None and _as_float(ocr_confidence, 100) < 60:
        reasons.append("OCR confidence below 60")

    for flag in sorted(flags & FORBIDDEN_AUTO_FLAGS):
        reasons.append(f"risk flag {flag} exists")

    return len(reasons) == 0, reasons


def _term_needs_formula(term):
    normalized = str(term or "").strip().lower()
    return normalized in FORMULA_DEPENDENT_TERMS


def collect_quality_flags(alignment, min_ocr_confidence=100):
    flags = set(str(flag) for flag in (alignment.get("quality_flags") or []) if str(flag).strip())
    english_items = alignment.get("english_evidence_items") or []
    chinese_items = alignment.get("chinese_evidence_items") or []
    english_score = _evidence_score(english_items)
    chinese_score = _evidence_score(chinese_items)

    if english_score < 0.65:
        flags.add("no_en_evidence")
    elif english_score < 0.80:
        flags.add("weak_evidence")

    if chinese_score < 0.65:
        flags.add("no_zh_evidence")
    elif chinese_score < 0.80:
        flags.add("weak_evidence")

    flags.update(_collect_evidence_risk_flags(english_items))
    flags.update(_collect_evidence_risk_flags(chinese_items))
    if "domain_mismatch" in flags:
        flags.add("domain_mismatch")

    provider_status = alignment.get("provider_status", "")
    ai_provider = alignment.get("ai_provider", "")
    ai_model = alignment.get("ai_model", "")
    if not provider_is_live(ai_provider, provider_status, ai_model, alignment.get("is_real_provider")):
        flags.add("mock_or_local_ai")

    if _as_float(min_ocr_confidence, 100) < 60:
        flags.add("ocr_low_confidence")

    if alignment.get("invalid_term_candidate"):
        flags.add("invalid_term_candidate")
    if alignment.get("multi_translation_conflict"):
        flags.add("multi_translation_conflict")
    if alignment.get("ambiguous_candidate"):
        flags.add("ambiguous_candidate")

    formula_status = str(alignment.get("formula_status", "") or "").strip()
    if formula_status in {"needs_formula_ocr_engine", "formula_ocr_failed", "low_confidence"}:
        flags.add("formula_evidence_missing")
    elif alignment.get("formula_evidence_required") or _term_needs_formula(alignment.get("english_term")):
        for block in alignment.get("formula_blocks") or []:
            if isinstance(block, dict) and block.get("status") in {"needs_formula_ocr_engine", "formula_ocr_failed", "low_confidence"}:
                flags.add("formula_evidence_missing")
                break

    return sorted(flags)


def derive_alignment_status(risk_flags, ai_alignment_status="", confidence_score=0):
    flags = set(risk_flags or [])
    priority = [
        "invalid_term_candidate",
        "no_en_evidence",
        "no_zh_evidence",
        "domain_mismatch",
        "ocr_low_confidence",
        "formula_evidence_missing",
        "multi_translation_conflict",
        "ambiguous_candidate",
    ]
    for flag in priority:
        if flag in flags:
            return flag
    ai_status = str(ai_alignment_status or "").strip()
    if ai_status in ALIGNMENT_STATUSES:
        return ai_status
    if "weak_evidence" in flags:
        return "accepted_translation" if _as_int(confidence_score) >= 70 else "unverified_translation"
    if not flags and _as_int(confidence_score) >= 85:
        return "exact_match"
    return "unverified_translation"


def derive_card_status(alignment_status, risk_flags, auto_approval_allowed):
    flags = set(risk_flags or [])
    if "invalid_term_candidate" in flags or alignment_status == "invalid_term_candidate":
        return "rejected"
    if "no_en_evidence" in flags or "no_zh_evidence" in flags or alignment_status in {"no_en_evidence", "no_zh_evidence"}:
        return "needs_more_evidence"
    if "multi_translation_conflict" in flags or alignment_status == "multi_translation_conflict":
        return "conflict_detected"
    if auto_approval_allowed:
        return "auto_approved"
    return "pending_quality_control"


def finalize_alignment_decision(alignment, min_ocr_confidence=100):
    result = dict(alignment or {})
    english_items = result.get("english_evidence_items") or []
    chinese_items = result.get("chinese_evidence_items") or []
    english_score = _evidence_score(english_items)
    chinese_score = _evidence_score(chinese_items)
    result["english_evidence_score"] = english_score
    result["chinese_evidence_score"] = chinese_score
    result["english_evidence_snapshot"] = evidence_snapshot(english_items)
    result["chinese_evidence_snapshot"] = evidence_snapshot(chinese_items)

    flags = collect_quality_flags(result, min_ocr_confidence=min_ocr_confidence)
    ai_raw_score = _as_float(result.get("confidence_score"), 0) / 100.0
    if ai_raw_score == 0:
        ai_raw_score = _as_float(result.get("ai_alignment_score"), 0.0)
    term_quality = _as_float(result.get("term_quality_score"), 0.86)

    en_breakdown = _best_score_breakdown(english_items)
    zh_breakdown = _best_score_breakdown(chinese_items)
    course_scope = max(
        _as_float(en_breakdown.get("course_scope_score"), 0.5),
        _as_float(zh_breakdown.get("course_scope_score"), 0.5),
    )
    source_quality = max(
        _as_float(en_breakdown.get("source_quality_score"), 0.5),
        _as_float(zh_breakdown.get("source_quality_score"), 0.5),
    )

    score_result = calculate_confidence_score(
        term_quality,
        english_score,
        chinese_score,
        ai_raw_score,
        course_scope,
        source_quality,
        flags,
    )
    confidence = score_result["confidence_score"]
    if "no_en_evidence" in flags or "no_zh_evidence" in flags:
        confidence = min(confidence, 45)

    ai_status = result.get("alignment_status") or result.get("ai_alignment_status")
    alignment_status = derive_alignment_status(flags, ai_status, confidence)
    gate_input = {
        "confidence_score": confidence,
        "term_quality_score": term_quality,
        "english_evidence_score": english_score,
        "chinese_evidence_score": chinese_score,
        "alignment_status": alignment_status,
        "ai_provider": result.get("ai_provider", ""),
        "provider_status": result.get("provider_status", ""),
        "ai_model": result.get("ai_model", ""),
        "ocr_status": result.get("ocr_status", "not_required"),
        "ocr_confidence": min_ocr_confidence,
        "risk_flags": flags,
        "is_real_provider": result.get("is_real_provider"),
    }
    auto_allowed, auto_reasons = can_auto_approve(gate_input)
    review_status = derive_card_status(alignment_status, flags, auto_allowed)

    result["quality_flags"] = flags
    result["confidence_score"] = confidence
    result["alignment_status"] = alignment_status
    result["review_status"] = review_status
    result["auto_approve_reasons"] = auto_reasons
    result["score_breakdown"] = {
        **score_result["score_breakdown"],
        "english_evidence_breakdown": en_breakdown,
        "chinese_evidence_breakdown": zh_breakdown,
        "auto_approval_gate": {
            "can_auto_approve": auto_allowed,
            "reasons": auto_reasons,
        },
    }
    if not result.get("risk_note") and (flags or auto_reasons):
        result["risk_note"] = "; ".join(auto_reasons[:3] or flags[:3])
    if result.get("english_evidence_snapshot") and not result.get("english_kb_evidence"):
        result["english_kb_evidence"] = result["english_evidence_snapshot"][0].get("content_excerpt", "")
    if result.get("chinese_evidence_snapshot") and not result.get("chinese_kb_evidence"):
        result["chinese_kb_evidence"] = result["chinese_evidence_snapshot"][0].get("content_excerpt", "")
    return result


def dumps_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)
