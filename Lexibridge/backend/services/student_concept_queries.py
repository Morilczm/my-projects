"""Student self-service one-concept query contracts and safe adapters.

The module composes the governed Task 12 services.  It does not implement a
student-only retrieval or alignment algorithm and never treats published cards
as query results.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from typing import Any, Iterable

from services import bilingual_evidence_qualification, student_first_boundaries


CONTRACT_VERSION = "student-concept-query@1.0.0"
ALIGNMENT_RESULT_CONTRACT_VERSION = "student-alignment-result@1.2.0"
ALIGNMENT_POLICY_VERSION = "governed-bilingual-evidence-qualification@1.1.0"
MATERIAL_READER_CONTRACT_VERSION = "student-material-reader@1.0.0"
PERSONAL_NOTEBOOK_CONTRACT_VERSION = "personal-concept-notebook@1.0.0"
LEARNING_SUPPORT_CONTRACT_VERSION = "student-learning-support@1.0.0"
MAX_SELECTION_CHARS = 180
MAX_CONTEXT_CHARS = 800
CONTEXT_WINDOW_CHARS = 360
MAX_READER_CHUNK_CHARS = 8000
MAX_NOTEBOOK_QUERY_CHARS = 120
MAX_NOTEBOOK_NOTE_PREVIEW_CHARS = 240
MAX_NOTEBOOK_PER_PAGE = 50
MAX_LEARNING_EVIDENCE_ITEMS = 4
MAX_LEARNING_SNIPPET_CHARS = 360
MAX_LEARNING_SUMMARY_CHARS = 720

NOTEBOOK_VIEWS = {"SAVED", "HISTORY", "UNDERSTOOD", "STILL_CONFUSED"}
NOTEBOOK_WORKSPACE_SCOPES = {"", "PERSONAL", "MANAGED_COURSE"}
NOTEBOOK_ALIGNMENT_STATUSES = {"", "READY", "REVIEW_REQUIRED", "NOT_READY"}


class StudentConceptQueryError(ValueError):
    def __init__(self, reason_code: str, message: str):
        super().__init__(message)
        self.reason_code = reason_code


@dataclass(frozen=True)
class ValidatedSelection:
    selected_text: str
    selection_start: int
    selection_end: int
    bounded_context: str
    provenance: dict[str, Any]


@dataclass(frozen=True)
class EvidenceScope:
    scope_id: str
    workspace_scope: str
    allowed_source_uids: tuple[str, ...]
    platform_governed_included: bool
    evidence_tier: str = "NONE"


PERSONAL_MATERIAL_ROLES = {
    "ENGLISH_COURSE_MATERIAL": "en",
    "CHINESE_REFERENCE_EVIDENCE": "zh",
}


def validate_personal_material_upload(
    *, material_role: Any, language: Any, rights_confirmed: Any
) -> dict[str, str]:
    role = _text(material_role).upper()
    if role not in PERSONAL_MATERIAL_ROLES:
        raise StudentConceptQueryError(
            "PERSONAL_MATERIAL_ROLE_INVALID",
            "Personal material role is invalid.",
        )
    expected_language = PERSONAL_MATERIAL_ROLES[role]
    submitted_language = _text(language).lower()
    if submitted_language and submitted_language != expected_language:
        raise StudentConceptQueryError(
            "PERSONAL_MATERIAL_LANGUAGE_ROLE_MISMATCH",
            "Personal material language does not match its evidence role.",
        )
    confirmed = rights_confirmed is True or _text(rights_confirmed).lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if not confirmed:
        raise StudentConceptQueryError(
            "PERSONAL_MATERIAL_RIGHTS_ATTESTATION_REQUIRED",
            "Confirm that you may use this material in your private workspace.",
        )
    return {
        "material_role": role,
        "language": expected_language,
        "license_note": "student_attested_private_use",
    }


def personal_material_role(source: Any = None, *, language: Any = "") -> str:
    normalized_language = _text(_field(source, "language", language)).lower()
    source_role = _text(_field(source, "source_role")).lower()
    if normalized_language == "zh" or source_role == "chinese_reference_material":
        return "CHINESE_REFERENCE_EVIDENCE"
    return "ENGLISH_COURSE_MATERIAL"


def qualification_quality_status(source: Any) -> str:
    raw = _text(_field(source, "quality_status")).lower()
    flags_value = _field(source, "quality_flags", [])
    if isinstance(flags_value, str):
        try:
            flags_value = json.loads(flags_value)
        except (TypeError, ValueError):
            flags_value = []
    adapted = bilingual_evidence_qualification._workflow_quality_status(
        {
            "quality_status": raw,
            "quality_flags": list(flags_value or []),
        }
    )
    return adapted or "unknown"


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _text(value: Any) -> str:
    return str(value or "").strip()


def personal_record_mutation_fingerprint(
    *, query_uid: Any, action: Any, changes: dict[str, Any], secret: Any
) -> str:
    """Key private mutations so audits can prove idempotency without storing notes."""
    normalized = {
        "query_uid": _text(query_uid),
        "action": _text(action).upper(),
        "saved": changes.get("saved") if "saved" in changes else None,
        "note": str(changes.get("note") or "") if "note" in changes else None,
        "understanding_state": (
            _text(changes.get("understanding_state")).upper()
            if "understanding_state" in changes
            else None
        ),
    }
    secret_bytes = str(secret or "").encode()
    if not secret_bytes:
        raise StudentConceptQueryError(
            "STUDENT_PERSONAL_RECORD_IDEMPOTENCY_POLICY_UNAVAILABLE",
            "Personal record idempotency policy is unavailable.",
        )
    return hmac.new(
        secret_bytes,
        json.dumps(normalized, ensure_ascii=False, sort_keys=True).encode(),
        hashlib.sha256,
    ).hexdigest()


def validate_notebook_filters(values: dict[str, Any]) -> dict[str, Any]:
    view = _text(values.get("view") or "SAVED").upper()
    workspace_scope = _text(values.get("workspace_scope")).upper()
    alignment_status = _text(values.get("alignment_status")).upper()
    query_text = _text(values.get("q"))
    try:
        page = int(values.get("page") or 1)
        per_page = int(values.get("per_page") or 20)
    except (TypeError, ValueError) as exc:
        raise StudentConceptQueryError(
            "STUDENT_NOTEBOOK_PAGINATION_INVALID",
            "Notebook pagination is invalid.",
        ) from exc
    if view not in NOTEBOOK_VIEWS:
        raise StudentConceptQueryError(
            "STUDENT_NOTEBOOK_VIEW_INVALID", "Notebook view is invalid."
        )
    if workspace_scope not in NOTEBOOK_WORKSPACE_SCOPES:
        raise StudentConceptQueryError(
            "STUDENT_NOTEBOOK_WORKSPACE_INVALID", "Notebook workspace is invalid."
        )
    if alignment_status not in NOTEBOOK_ALIGNMENT_STATUSES:
        raise StudentConceptQueryError(
            "STUDENT_NOTEBOOK_ALIGNMENT_STATUS_INVALID",
            "Notebook alignment status is invalid.",
        )
    if len(query_text) > MAX_NOTEBOOK_QUERY_CHARS:
        raise StudentConceptQueryError(
            "STUDENT_NOTEBOOK_QUERY_TOO_LONG", "Notebook search is too long."
        )
    if page < 1 or per_page < 1 or per_page > MAX_NOTEBOOK_PER_PAGE:
        raise StudentConceptQueryError(
            "STUDENT_NOTEBOOK_PAGINATION_INVALID",
            "Notebook pagination is invalid.",
        )
    return {
        "view": view,
        "workspace_scope": workspace_scope,
        "alignment_status": alignment_status,
        "q": query_text,
        "page": page,
        "per_page": per_page,
    }


def source_search_eligible(source: Any, *, expected_language: Any = "") -> bool:
    expected = _text(expected_language).lower()
    language = _text(_field(source, "language")).lower()
    expected_languages = {
        "en": {"en", "english"},
        "zh": {"zh", "chinese"},
    }.get(expected, {expected})
    if expected and language not in expected_languages:
        return False
    if _text(_field(source, "status", "active")).lower() != "active":
        return False
    if not bool(_field(source, "allow_student_search", False)):
        return False
    authorization = _text(_field(source, "authorization_status")).lower()
    license_status = _text(_field(source, "license_status")).lower()
    return authorization in {
        "authorized",
        "approved",
        "granted",
        "allowed_for_private_use",
        "allowed_for_course_use",
    } and license_status not in {
        "", "unknown", "blocked", "rejected",
    }


def serialize_material_reader_item(chunk: Any) -> dict[str, Any]:
    """Serialize one governed, selectable chunk without exposing storage data."""
    text = str(_field(chunk, "content", "") or "")
    if len(text) > MAX_READER_CHUNK_CHARS:
        raise StudentConceptQueryError(
            "STUDENT_MATERIAL_READER_CONTENT_UNBOUNDED",
            "A parsed material block exceeds the student reader boundary.",
        )
    page_number = _field(chunk, "page_number")
    block_uid = _text(_field(chunk, "parse_block_uid"))
    if page_number is None or not block_uid:
        raise StudentConceptQueryError(
            "STUDENT_MATERIAL_READER_PROVENANCE_INCOMPLETE",
            "A parsed material block is missing page or block provenance.",
        )
    return {
        "chunk_uid": _text(_field(chunk, "chunk_uid")) or str(_field(chunk, "id", "")),
        "text": text,
        "page_number": int(page_number),
        "block_uid": block_uid,
        "heading_path": _text(
            _field(chunk, "source_section") or _field(chunk, "chapter")
        ),
        "block_type": _text(_field(chunk, "block_type")) or "text",
        "chunk_index": int(_field(chunk, "chunk_index", 0) or 0),
        "content_hash": (
            _text(_field(chunk, "content_hash"))
            or hashlib.sha256(text.encode()).hexdigest()
        ),
        "span_start": 0,
        "span_end": len(text),
        "selectable": bool(text.strip()),
    }


def _source_is_governed(source: Any) -> bool:
    if _text(_field(source, "language")).lower() not in {"zh", "chinese"}:
        return False
    return source_search_eligible(source, expected_language="zh")


def validate_selection(
    chunk: Any,
    *,
    selected_text: Any,
    selection_start: Any,
    selection_end: Any,
) -> ValidatedSelection:
    content = str(_field(chunk, "content", "") or "")
    selected = str(selected_text or "")
    if not selected.strip():
        raise StudentConceptQueryError(
            "STUDENT_CONCEPT_SELECTION_EMPTY", "Select an English concept."
        )
    try:
        start, end = int(selection_start), int(selection_end)
    except (TypeError, ValueError) as exc:
        raise StudentConceptQueryError(
            "STUDENT_CONCEPT_SELECTION_SPAN_INVALID", "Selection offsets are invalid."
        ) from exc
    if start < 0 or end <= start or end > len(content):
        raise StudentConceptQueryError(
            "STUDENT_CONCEPT_SELECTION_SPAN_INVALID", "Selection offsets are outside the source chunk."
        )
    if len(selected) > MAX_SELECTION_CHARS:
        raise StudentConceptQueryError(
            "STUDENT_CONCEPT_SELECTION_TOO_LONG", "Select a bounded term or short phrase."
        )
    if not re.search(r"[A-Za-z]", selected) or not re.search(r"[A-Za-z]{2,}", selected):
        raise StudentConceptQueryError(
            "STUDENT_CONCEPT_SELECTION_NOT_CONCEPT", "Selection must contain a meaningful English term."
        )
    if content[start:end] != selected:
        raise StudentConceptQueryError(
            "STUDENT_CONCEPT_SELECTION_TEXT_MISMATCH", "Selected text does not match the source."
        )
    left = max(0, start - CONTEXT_WINDOW_CHARS)
    right = min(len(content), end + CONTEXT_WINDOW_CHARS)
    context = content[left:right][:MAX_CONTEXT_CHARS]
    return ValidatedSelection(
        selected_text=selected.strip(),
        selection_start=start,
        selection_end=end,
        bounded_context=context,
        provenance={
            "chunk_uid": _text(_field(chunk, "chunk_uid")) or str(_field(chunk, "id", "")),
            "block_uid": _text(_field(chunk, "parse_block_uid")),
            "page_number": _field(chunk, "page_number"),
            "span_start": start,
            "span_end": end,
            "heading_path": _text(_field(chunk, "section_title") or _field(chunk, "source_section")),
        },
    )


def build_query_fingerprint(**values: Any) -> str:
    identity = {
        "student_uid": _text(values.get("student_uid")),
        "workspace_scope": _text(values.get("workspace_scope")).upper(),
        "workspace_uid": _text(values.get("workspace_uid")),
        "source_uid": _text(values.get("source_uid")),
        "source_version": _text(values.get("source_version")),
        "chunk_uid": _text(values.get("chunk_uid")),
        "selection_start": int(values.get("selection_start") or 0),
        "selection_end": int(values.get("selection_end") or 0),
        "selected_text": " ".join(_text(values.get("selected_text")).casefold().split()),
        "evidence_scope_id": _text(values.get("evidence_scope_id")),
        "alignment_policy_version": _text(
            values.get("alignment_policy_version") or ALIGNMENT_POLICY_VERSION
        ),
    }
    return hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def resolve_evidence_scope(
    sources: Iterable[Any],
    *,
    workspace_scope: Any,
    student_id: int,
    course_id: int | None,
    allow_platform_governed: bool,
) -> EvidenceScope:
    scope = _text(workspace_scope).upper()
    if scope not in {"PERSONAL", "MANAGED_COURSE"}:
        raise StudentConceptQueryError(
            "STUDENT_CONCEPT_WORKSPACE_INVALID", "Workspace scope is invalid."
        )
    allowed: list[str] = []
    personal_or_course_count = 0
    platform_count = 0
    platform_included = False
    evidence_identities: list[str] = []
    for source in sources:
        if not _source_is_governed(source):
            continue
        source_scope = _text(_field(source, "scope_type")).lower()
        visibility = _text(_field(source, "visibility")).lower()
        owner_id = _field(source, "owner_user_id")
        source_course_id = _field(source, "course_id")
        is_platform = source_scope in {"global", "platform"} and visibility in {
            "global", "platform", "public",
        }
        permitted = False
        if scope == "PERSONAL":
            permitted = source_scope == "personal" and str(owner_id) == str(student_id)
        else:
            permitted = (
                source_scope in {"course", "managed_course"}
                and course_id is not None
                and str(source_course_id) == str(course_id)
                and visibility in {"course", "course_shared"}
            )
        if is_platform and allow_platform_governed:
            permitted = True
            platform_included = True
        if permitted:
            uid = _text(_field(source, "source_uid"))
            if uid:
                allowed.append(uid)
                evidence_identities.append(":".join((
                    uid,
                    _text(_field(source, "version")),
                    _text(_field(source, "content_hash")),
                )))
                if is_platform:
                    platform_count += 1
                else:
                    personal_or_course_count += 1
    allowed_uids = tuple(sorted(set(allowed)))
    scope_material = (
        f"{scope}:{student_id}:{course_id or ''}:"
        f"{'|'.join(sorted(set(evidence_identities)))}"
    )
    if scope == "PERSONAL" and personal_or_course_count:
        evidence_tier = (
            "PERSONAL_PRIVATE_WITH_PLATFORM_FALLBACK"
            if platform_count
            else "PERSONAL_PRIVATE"
        )
    elif scope == "MANAGED_COURSE" and personal_or_course_count:
        evidence_tier = (
            "MANAGED_COURSE_WITH_PLATFORM_FALLBACK"
            if platform_count
            else "MANAGED_COURSE"
        )
    elif platform_count:
        evidence_tier = "PLATFORM_GOVERNED"
    else:
        evidence_tier = "NONE"
    return EvidenceScope(
        scope_id=hashlib.sha256(scope_material.encode()).hexdigest()[:24],
        workspace_scope=scope,
        allowed_source_uids=allowed_uids,
        platform_governed_included=platform_included,
        evidence_tier=evidence_tier,
    )


_STUDENT_REVIEW_ONLY_REASONS = frozenset({
    bilingual_evidence_qualification.EVIDENCE_PAIR_MARGIN_INSUFFICIENT,
    bilingual_evidence_qualification.EVIDENCE_PAIR_UNCERTAIN,
    bilingual_evidence_qualification.EVIDENCE_QUALIFICATION_EXECUTION_FAILED,
    bilingual_evidence_qualification.EVIDENCE_SCORE_COMPONENT_CONFLICT,
    bilingual_evidence_qualification.EVIDENCE_TERM_SCOPE_RISK,
})


def _has_bounded_selected_candidate(
    selected_candidate: Any, chinese_evidence: Any, chinese_candidates: Any
) -> bool:
    if not isinstance(selected_candidate, dict) or bool(
        _field(selected_candidate, "generated")
    ):
        return False
    selected_uid = _text(_field(selected_candidate, "candidate_uid"))
    selected_source_uid = _text(_field(selected_candidate, "source_uid"))
    selected_chunk_uid = _text(_field(selected_candidate, "chunk_uid"))
    selected_text = _text(
        _field(selected_candidate, "text")
        or _field(selected_candidate, "chinese_term")
    )
    evidence_refs = {
        (_text(_field(item, "source_uid")), _text(_field(item, "chunk_uid")))
        for item in chinese_evidence or []
        if isinstance(item, dict)
    }
    return any(
        not bool(_field(candidate, "generated"))
        and bool(_field(candidate, "evidence_backed"))
        and bool(_text(_field(candidate, "text") or _field(candidate, "chinese_term")))
        and (
            _text(_field(candidate, "source_uid")),
            _text(_field(candidate, "chunk_uid")),
        ) in evidence_refs
        and (
            bool(selected_uid)
            and _text(_field(candidate, "candidate_uid")) == selected_uid
            or (
                not selected_uid
                and _text(_field(candidate, "source_uid")) == selected_source_uid
                and _text(_field(candidate, "chunk_uid")) == selected_chunk_uid
                and _text(
                    _field(candidate, "text")
                    or _field(candidate, "chinese_term")
                ) == selected_text
            )
        )
        for candidate in chinese_candidates or []
        if isinstance(candidate, dict)
    )


def alignment_status_from_qualification(
    qualification: Any,
    *,
    selected_candidate: Any = None,
    chinese_evidence: Any = (),
    chinese_candidates: Any = (),
) -> str:
    decision = _text(
        qualification.get("decision") if isinstance(qualification, dict) else qualification
    ).upper()
    if decision == "QUALIFIED":
        return "READY"
    if decision == "REVIEW_REQUIRED":
        return "REVIEW_REQUIRED"
    reasons = {
        _text(reason)
        for reason in (
            qualification.get("reason_codes", [])
            if isinstance(qualification, dict)
            else []
        )
        if _text(reason)
    }
    if (
        decision == "REJECTED"
        and reasons
        and reasons <= _STUDENT_REVIEW_ONLY_REASONS
        and _has_bounded_selected_candidate(
            selected_candidate, chinese_evidence, chinese_candidates
        )
    ):
        # This is a PRIVATE/NON_OFFICIAL display decision only.  The governed
        # qualification remains REJECTED, so readiness and Provider execution
        # stay fail-closed while the student may inspect bounded alternatives.
        return "REVIEW_REQUIRED"
    return "NOT_READY"


def finalize_student_alignment_risks(
    risks: Any, *, qualification: Any, selected_candidate: Any
) -> list[str]:
    """Remove stale pre-pairing labels only in the Student read model."""
    labels = list(dict.fromkeys(_text(value) for value in risks or [] if _text(value)))
    selected_text = _text(
        _field(selected_candidate, "text")
        or _field(selected_candidate, "chinese_term")
    )
    if selected_text:
        labels = [label for label in labels if label != "missing_chinese_term"]
    decision = _text(
        qualification.get("decision")
        if isinstance(qualification, dict)
        else qualification
    ).upper()
    if decision == "QUALIFIED":
        stale = {
            "bilingual_alignment_not_verified",
            "candidate_not_alignment_verified",
        }
        labels = [label for label in labels if label not in stale]
    return labels


def _learning_citation(evidence: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_uid": _text(evidence.get("source_uid")),
        "chunk_uid": _text(evidence.get("chunk_uid")),
        "page_number": evidence.get("page_number"),
        "block_uid": _text(
            evidence.get("block_uid") or evidence.get("parse_block_uid")
        ),
    }


def _learning_evidence(
    evidence: dict[str, Any], *, language: str = ""
) -> dict[str, Any]:
    item = {
        **_learning_citation(evidence),
        "snippet": str(
            evidence.get("snippet") or evidence.get("text") or ""
        )[:MAX_LEARNING_SNIPPET_CHARS],
    }
    if language:
        item["language"] = language
    return item


def _learning_evidence_map(values: Any) -> dict[tuple[str, str], dict[str, Any]]:
    output: dict[tuple[str, str], dict[str, Any]] = {}
    for raw in values if isinstance(values, list) else []:
        if not isinstance(raw, dict):
            continue
        item = _learning_evidence(raw)
        key = (item["source_uid"], item["chunk_uid"])
        if all(key) and item["snippet"] and key not in output:
            output[key] = item
        if len(output) >= MAX_LEARNING_EVIDENCE_ITEMS:
            break
    return output


def _learning_candidates(
    raw_candidates: Any,
    chinese_evidence: dict[tuple[str, str], dict[str, Any]],
    *,
    selected_uid: str,
) -> list[dict[str, Any]]:
    output = []
    seen = set()
    for raw in raw_candidates if isinstance(raw_candidates, list) else []:
        if not isinstance(raw, dict) or bool(raw.get("generated")):
            continue
        source_uid = _text(raw.get("source_uid"))
        chunk_uid = _text(raw.get("chunk_uid"))
        evidence = chinese_evidence.get((source_uid, chunk_uid))
        term = _text(raw.get("text") or raw.get("chinese_term"))[:160]
        candidate_uid = _text(raw.get("candidate_uid"))
        if (
            not bool(raw.get("evidence_backed"))
            or evidence is None
            or not term
            or not candidate_uid
            or candidate_uid in seen
        ):
            continue
        seen.add(candidate_uid)
        output.append(
            {
                "candidate_uid": candidate_uid,
                "term": term,
                "evidence_backed": True,
                "selected": candidate_uid == selected_uid,
                "evidence": dict(evidence),
            }
        )
        if len(output) >= MAX_LEARNING_EVIDENCE_ITEMS:
            break
    return output


def build_student_learning_support(
    result: dict[str, Any],
    *,
    alignment_status: str,
    recommended_chinese_concept: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build a no-network, evidence-only learning aid from the frozen result.

    The adapter explains the machine decision and places candidate evidence
    side by side. It deliberately does not infer a semantic distinction that
    is absent from the governed evidence.
    """
    english_map = _learning_evidence_map(result.get("english_evidence"))
    chinese_map = _learning_evidence_map(result.get("chinese_evidence"))
    english_evidence = list(english_map.values())
    selected = (
        result.get("selected_candidate")
        if isinstance(result.get("selected_candidate"), dict)
        else {}
    )
    selected_uid = _text(selected.get("candidate_uid"))
    candidates = _learning_candidates(
        result.get("chinese_candidates"),
        chinese_map,
        selected_uid=selected_uid,
    )
    selected_candidate = next(
        (item for item in candidates if item["selected"]), None
    )
    alternatives = [item for item in candidates if not item["selected"]]
    meaning = str(
        result.get("bounded_context")
        or (english_evidence[0]["snippet"] if english_evidence else "")
    )[:MAX_CONTEXT_CHARS]
    meaning_citations = (
        [_learning_citation(english_evidence[0])] if english_evidence else []
    )

    support_status = "NO_RELIABLE_ALIGNMENT"
    recommendation_claim = "NONE"
    why_status = "UNAVAILABLE"
    why_summary = "当前没有足够可靠的中文证据支持双语概念对应。"
    why_evidence: list[dict[str, Any]] = []
    limitations = ["未形成可靠双语对应，因此不生成候选差异结论。"]

    grounding_complete = bool(
        meaning
        and english_evidence
        and selected_candidate
        and recommended_chinese_concept
    )
    if alignment_status == "READY" and grounding_complete:
        support_status = "EVIDENCE_GROUNDED"
        recommendation_claim = "EVIDENCE_BACKED_RECOMMENDATION"
        why_status = "EVIDENCE_BACKED"
        why_summary = (
            f"当前推荐“{selected_candidate['term']}”绑定到独立中文证据，"
            "并通过既有双侧证据资格门。下面只呈现输入证据及流程结论，"
            "仍是个人非官方学习结果。"
        )[:MAX_LEARNING_SUMMARY_CHARS]
        why_evidence = [
            {**english_evidence[0], "language": "en"},
            {**selected_candidate["evidence"], "language": "zh"},
        ]
        limitations = [
            "该说明解释证据与机器推荐的关系，不替代课程正式定义。",
            "候选间的概念边界仅在证据中并列展示，不由系统补写。",
        ]
    elif alignment_status == "REVIEW_REQUIRED" and english_evidence and candidates:
        support_status = "ALTERNATIVES_UNRESOLVED"
        recommendation_claim = "TENTATIVE"
        why_status = "UNRESOLVED"
        why_summary = (
            "多个候选具有独立中文证据，但现有证据无法唯一确认对应关系。"
            "请比较每个候选的有界证据，不要把第一项当作唯一答案。"
        )[:MAX_LEARNING_SUMMARY_CHARS]
        why_evidence = [{**english_evidence[0], "language": "en"}] + [
            {**item["evidence"], "language": "zh"}
            for item in candidates
        ]
        limitations = [
            "候选关系尚未解决，所有候选均保持非官方和不确定状态。"
        ]
    elif alignment_status in {"READY", "REVIEW_REQUIRED"}:
        support_status = "GROUNDING_INCOMPLETE"
        why_summary = "当前结果缺少可绑定到候选的双侧证据，学习说明已关闭。"
        limitations = ["候选或证据 provenance 不完整。"]

    alternative_items = []
    comparisons = []
    if alignment_status in {"READY", "REVIEW_REQUIRED"}:
        for alternative in alternatives:
            alternative_items.append(
                {
                    **alternative,
                    "student_message": (
                        f"“{alternative['term']}”有独立中文证据，但当前流程"
                        "没有把它确认为唯一对应；保留为可比较候选，不代表已证明错误。"
                    )[:MAX_LEARNING_SUMMARY_CHARS],
                }
            )
            if selected_candidate is not None:
                comparisons.append(
                    {
                        "recommended_term": selected_candidate["term"],
                        "alternative_term": alternative["term"],
                        "comparison_mode": "EVIDENCE_SIDE_BY_SIDE",
                        "boundary_conclusion": "UNRESOLVED",
                        "recommended_evidence": dict(
                            selected_candidate["evidence"]
                        ),
                        "alternative_evidence": dict(alternative["evidence"]),
                        "student_message": (
                            f"当前证据不足以安全概括“{selected_candidate['term']}”"
                            f"与“{alternative['term']}”的概念边界；下面并列有界证据，"
                            "避免编造差异。"
                        )[:MAX_LEARNING_SUMMARY_CHARS],
                    }
                )

    return {
        "contract_id": LEARNING_SUPPORT_CONTRACT_VERSION,
        "status": support_status,
        "workspace_behavior": "SHARED_STUDENT_EXPERIENCE",
        "authority": "NON_OFFICIAL",
        "visibility": "PRIVATE",
        "grounding_mode": "DETERMINISTIC_EVIDENCE_TEMPLATE",
        "provider_used": False,
        "generated_claims": False,
        "recommendation_claim": recommendation_claim,
        "what_it_means_here": {
            "mode": "EXTRACTIVE_COURSE_CONTEXT",
            "text": meaning,
            "citations": meaning_citations,
        },
        "why_they_align": {
            "status": why_status,
            "summary": why_summary,
            "evidence": why_evidence[: MAX_LEARNING_EVIDENCE_ITEMS + 1],
        },
        "candidate_evidence": candidates if alignment_status != "NOT_READY" else [],
        "alternatives": alternative_items,
        "do_not_confuse_with": comparisons,
        "limitations": limitations,
    }


def serialize_alignment_result(result: dict[str, Any]) -> dict[str, Any]:
    status = alignment_status_from_qualification(
        result.get("qualification"),
        selected_candidate=result.get("selected_candidate"),
        chinese_evidence=result.get("chinese_evidence", []),
        chinese_candidates=result.get("chinese_candidates", []),
    )
    selected = result.get("selected_candidate") if isinstance(result.get("selected_candidate"), dict) else {}
    raw = {
        "alignment_result_uid": result.get("result_uid"),
        "workspace_scope": result.get("workspace_scope"),
        "alignment_status": status,
        "english_term": result.get("english_term"),
        "chinese_term": selected.get("text") or selected.get("chinese_term"),
        "english_evidence": result.get("english_evidence", []),
        "chinese_evidence": result.get("chinese_evidence", []),
        "chinese_candidates": result.get("chinese_candidates", []),
        "generated_hints": result.get("generated_hints", []),
        "evidence_scope": result.get("evidence_scope", {}),
    }
    base = student_first_boundaries.serialize_student_alignment_result(raw)
    recommended = None
    if status in {"READY", "REVIEW_REQUIRED"} and base["chinese_term"]:
        recommended = {
            "candidate_uid": _text(selected.get("candidate_uid")),
            "text": base["chinese_term"],
            "evidence_backed": True,
        }
    student_explanations = {
        "READY": "已在独立中文资料中找到有双侧证据支持的概念对应。",
        "REVIEW_REQUIRED": "找到了有证据的候选，但当前证据不足以唯一确认。",
        "NOT_READY": "当前没有在独立中文资料中找到足够可靠的概念对应。",
    }
    student_risk_summaries = {
        "READY": [],
        "REVIEW_REQUIRED": ["存在多个可能对应或概念范围不确定。"],
        "NOT_READY": ["请补充受治理的中文资料，或重新选择更明确的英文概念。"],
    }
    learning_support = build_student_learning_support(
        result,
        alignment_status=status,
        recommended_chinese_concept=recommended,
    )
    return {
        **base,
        "contract_id": ALIGNMENT_RESULT_CONTRACT_VERSION,
        "result_uid": _text(result.get("result_uid")),
        "query_uid": _text(result.get("query_uid")),
        "result_version": int(result.get("result_version") or 1),
        "workspace_uid": _text(result.get("workspace_uid")),
        "source_uid": _text(result.get("source_uid")),
        "source_version": _text(result.get("source_version")),
        "selected_text": _text(result.get("selected_text")),
        "bounded_context": str(result.get("bounded_context") or "")[:MAX_CONTEXT_CHARS],
        "recommended_chinese_concept": recommended,
        "student_explanation": student_explanations[status],
        "student_risk_summary": student_risk_summaries[status],
        "learning_support": learning_support,
        "evidence_complete": bool(base["english_evidence"] and base["chinese_evidence"]),
        "generated_hint_present": bool(base["generated_hints"]),
        "evidence_scope": dict(result.get("evidence_scope") or {}),
        "personal_state": dict(result.get("personal_state") or {}),
        "created_at": _text(result.get("created_at")),
        "updated_at": _text(result.get("updated_at")),
    }


def redact_unavailable_source_result(
    serialized: dict[str, Any],
) -> dict[str, Any]:
    """Retain the historical decision while closing access to deleted evidence.

    A PersonalLearningRecord may outlive its source material, but deletion must
    make the bounded source text and derived learning explanation inaccessible.
    The original machine status and selected term remain historical facts; they
    are no longer presented as currently verifiable evidence.
    """
    redacted = dict(serialized)
    redacted.update(
        {
            "bounded_context": "",
            "english_evidence": [],
            "chinese_evidence": [],
            "chinese_candidates": [],
            "evidence_complete": False,
            "student_explanation": (
                "历史对齐结果仍保留，但原资料已不可用，当前无法重新核验证据。"
            ),
            "student_risk_summary": ["原资料已删除或当前不可访问。"],
        }
    )
    support = dict(redacted.get("learning_support") or {})
    support.update(
        {
            "status": "SOURCE_UNAVAILABLE",
            "grounding_mode": "SOURCE_UNAVAILABLE",
            "recommendation_claim": "HISTORICAL_RESULT_ONLY",
            "what_it_means_here": {
                "mode": "SOURCE_UNAVAILABLE",
                "text": "",
                "citations": [],
            },
            "why_they_align": {
                "status": "UNAVAILABLE",
                "summary": (
                    "原资料已不可用，系统不再展示或重新解释其历史证据。"
                ),
                "evidence": [],
            },
            "candidate_evidence": [],
            "alternatives": [],
            "do_not_confuse_with": [],
            "limitations": ["历史结果不可作为当前可核验的证据型推荐。"],
        }
    )
    redacted["learning_support"] = support
    return redacted


def build_raw_alignment_result(
    workflow_result: Any,
    *,
    query_uid: str,
    result_uid: str,
    workspace_scope: str,
    workspace_uid: str,
    source_uid: str,
    source_version: str,
    selection: ValidatedSelection,
    created_at: str,
) -> dict[str, Any]:
    """Adapt the existing Task 12 workflow output to the student read model."""
    qualification = getattr(workflow_result, "evidence_qualification", None)
    selected = getattr(workflow_result, "selected_chinese_candidate", None) or {}
    candidates = []
    for item in getattr(workflow_result, "chinese_term_candidates", []) or []:
        candidate = dict(item)
        candidate["text"] = candidate.get("text") or candidate.get("chinese_term")
        candidate["evidence_backed"] = bool(
            candidate.get("source_uid") and candidate.get("chunk_uid")
        )
        candidate["generated"] = False
        candidates.append(candidate)
    if not selected:
        production_pairs = list(
            getattr(workflow_result, "bilingual_pair_candidates", []) or []
        )
        top1 = next(
            (
                item for item in production_pairs
                if int(item.get("rank") or 0) == 1
            ),
            None,
        )
        if top1 is not None:
            selected_uid = _text(top1.get("chinese_candidate_uid"))
            selected = next(
                (
                    candidate for candidate in candidates
                    if _text(candidate.get("candidate_uid")) == selected_uid
                ),
                {},
            )
    english_evidence = [
        dict(item) for item in getattr(workflow_result, "english_evidence_candidates", []) or []
    ]
    chinese_evidence = [
        dict(item) for item in getattr(workflow_result, "chinese_evidence_candidates", []) or []
    ]
    risk_labels = finalize_student_alignment_risks(
        getattr(workflow_result, "risk_labels", []) or [],
        qualification=qualification,
        selected_candidate=selected,
    )
    return {
        "query_uid": query_uid,
        "result_uid": result_uid,
        "result_version": 1,
        "workspace_scope": workspace_scope,
        "workspace_uid": workspace_uid,
        "source_uid": source_uid,
        "source_version": source_version,
        "english_term": getattr(workflow_result, "english_term", selection.selected_text),
        "selected_text": selection.selected_text,
        "bounded_context": selection.bounded_context,
        "english_evidence": english_evidence,
        "chinese_evidence": chinese_evidence,
        "chinese_candidates": candidates,
        "selected_candidate": selected,
        "qualification": qualification,
        "risk_labels": risk_labels,
        "generated_hints": [],
        "created_at": created_at,
        "updated_at": created_at,
    }
