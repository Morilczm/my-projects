from services.scoring import score_knowledge_chunk


EVIDENCE_THRESHOLD = 0.65
STRONG_EVIDENCE_THRESHOLD = 0.80


def language_allowed(chunk_language, requested_language):
    chunk_language = str(chunk_language or "").strip().lower()
    requested_language = str(requested_language or "").strip().lower()
    if requested_language == "en":
        return chunk_language in {"en", "bilingual"}
    if requested_language == "zh":
        return chunk_language in {"zh", "bilingual"}
    return True


def hard_filter_chunk(chunk, course_id, language, knowledge_base_type, scope_type, owner_user_id=None):
    if not language_allowed(getattr(chunk, "language", ""), language):
        return False
    if knowledge_base_type and getattr(chunk, "knowledge_base_type", "") != knowledge_base_type:
        return False

    visibility = str(getattr(chunk, "visibility", "") or "").lower()
    chunk_owner = str(getattr(chunk, "owner_user_id", "") or "")
    chunk_course_id = getattr(chunk, "course_id", None)

    if visibility == "private" and str(owner_user_id or "") != chunk_owner:
        return False

    if scope_type == "personal":
        return (
            visibility == "private"
            and knowledge_base_type == "student_personal_kb"
            and str(owner_user_id or "") == chunk_owner
        )

    if scope_type == "course":
        return visibility == "course" and course_id is not None and str(chunk_course_id) == str(course_id)

    if scope_type == "global":
        return visibility == "global"

    return False


def evidence_strength(score):
    if score >= STRONG_EVIDENCE_THRESHOLD:
        return "strong"
    if score >= EVIDENCE_THRESHOLD:
        return "weak"
    return "rejected"


def result_from_chunk(chunk, score_payload):
    evidence_score = score_payload["evidence_score"]
    risk_flags = sorted(set(score_payload["risk_flags"]) | set(getattr(chunk, "_source_governance_flags", []) or []))
    source_status = getattr(chunk, "_source_status", "active")
    if source_status == "deprecated" and evidence_score >= STRONG_EVIDENCE_THRESHOLD:
        evidence_strength_value = "weak"
    else:
        evidence_strength_value = evidence_strength(evidence_score)
    return {
        "chunk_id": getattr(chunk, "id", None),
        "knowledge_base_version_id": getattr(chunk, "knowledge_base_version_id", None),
        "knowledge_source_id": getattr(chunk, "knowledge_source_id", None) or getattr(chunk, "source_id", None),
        "source_title": getattr(chunk, "title", "") or getattr(chunk, "course", "") or "KnowledgeChunk",
        "source": getattr(chunk, "title", "") or getattr(chunk, "course", "") or "KnowledgeChunk",
        "source_status": source_status,
        "authorization_status": getattr(chunk, "_authorization_status", "unknown"),
        "language": getattr(chunk, "language", ""),
        "course_id": getattr(chunk, "course_id", None),
        "course": getattr(chunk, "course", ""),
        "owner_user_id": getattr(chunk, "owner_user_id", ""),
        "knowledge_base_type": getattr(chunk, "knowledge_base_type", ""),
        "visibility": getattr(chunk, "visibility", ""),
        "content_excerpt": str(getattr(chunk, "content", "") or "")[:900],
        "content": str(getattr(chunk, "content", "") or "")[:900],
        "source_citation": getattr(chunk, "source_citation", "") or getattr(chunk, "source_page", ""),
        "page_number": getattr(chunk, "page_number", None),
        "chapter": getattr(chunk, "chapter", "") or getattr(chunk, "source_page", ""),
        "content_hash": getattr(chunk, "content_hash", ""),
        "index_status": getattr(chunk, "index_status", ""),
        "is_duplicate": bool(getattr(chunk, "is_duplicate", False)),
        "evidence_score": evidence_score,
        "similarity_score": evidence_score,
        "score": evidence_score,
        "evidence_strength": evidence_strength_value,
        "score_breakdown": score_payload["score_breakdown"],
        "risk_flags": risk_flags,
        "retrieval_version": "local_lexical_v1",
        "index_version": "local_lexical_v1",
        "retrieval_reason": "metadata hard filter + local lexical evidence scoring",
    }


def retrieve_evidence_results(
    query,
    course_id,
    language,
    knowledge_base_type,
    scope_type,
    owner_user_id=None,
    discipline=None,
    limit=5,
    chunks=None,
):
    if not str(query or "").strip():
        return []

    candidates = chunks or []
    scored = []
    for chunk in candidates:
        if not hard_filter_chunk(
            chunk,
            course_id=course_id,
            language=language,
            knowledge_base_type=knowledge_base_type,
            scope_type=scope_type,
            owner_user_id=owner_user_id,
        ):
            continue
        score_payload = score_knowledge_chunk(
            query,
            chunk,
            course_id=course_id,
            discipline=discipline,
        )
        breakdown = score_payload["score_breakdown"]
        risk_flags = set(score_payload["risk_flags"])

        if breakdown["term_exact_or_alias_match"] == 0 and breakdown["lexical_overlap_score"] < 0.20:
            continue
        if breakdown["course_scope_score"] == 0:
            continue
        if scope_type != "personal" and "restricted_without_derivative_permission" in risk_flags:
            continue
        if "domain_mismatch" in risk_flags and breakdown["term_exact_or_alias_match"] == 0:
            continue
        if score_payload["evidence_score"] < EVIDENCE_THRESHOLD:
            continue

        scored.append((score_payload["evidence_score"], chunk, score_payload))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [result_from_chunk(chunk, payload) for _, chunk, payload in scored[:limit]]
