"""Student-owned ConceptQuery and PersonalLearningRecord routes."""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from flask import current_app, request

from routes.shared import RouteCoreDependencies
from services import bilingual_evidence_workflow
from services import student_concept_queries


@dataclass(frozen=True)
class StudentConceptQueryModels:
    StudentConceptQuery: Any
    PersonalLearningRecord: Any
    KnowledgeSource: Any
    KnowledgeChunk: Any
    Course: Any
    CourseMember: Any
    Document: Any
    DocumentParseRecord: Any


def register_student_concept_query_routes(
    app,
    *,
    core: RouteCoreDependencies,
    models: StudentConceptQueryModels,
    material_file_exists: Callable[[Any], bool],
    material_file_response: Callable[[Any], Any],
) -> None:
    marker = "student_concept_query_routes"
    registered = app.extensions.setdefault("lexibridge_route_modules", set())
    if marker in registered:
        return
    db = core.db

    def error(reason, message, status, context):
        return core.api_error_with_audit_context(
            reason, message, status, context, {"audit_error_code": reason}
        )

    def student(context=None):
        user, response = core.require_current_user({"student"})
        return user, response

    def membership_active(user_id, course_id):
        return models.CourseMember.query.filter_by(
            user_id=user_id, course_id=course_id, status="active"
        ).first() is not None

    def source_access(user, source, scope):
        if (
            str(source.status or "").lower() != "active"
            or not bool(source.allow_student_search)
        ):
            return False
        if scope == "PERSONAL":
            return (
                str(source.scope_type or "").lower() == "personal"
                and str(source.owner_user_id) == str(user.id)
            )
        return (
            scope == "MANAGED_COURSE"
            and str(source.scope_type or "").lower() in {"course", "managed_course"}
            and source.course_id is not None
            and membership_active(user.id, source.course_id)
        )

    def source_owned_or_member(user, source, scope):
        if scope == "PERSONAL":
            return (
                str(source.scope_type or "").lower() == "personal"
                and str(source.owner_user_id) == str(user.id)
            )
        return (
            scope == "MANAGED_COURSE"
            and str(source.scope_type or "").lower() in {"course", "managed_course"}
            and source.course_id is not None
            and membership_active(user.id, source.course_id)
        )

    def lifecycle_not_ready(reason, context, *, source=None):
        scope = (
            "PERSONAL"
            if source is not None and str(source.scope_type or "").lower() == "personal"
            else "MANAGED_COURSE"
        )
        return core.api_success_with_audit_context(
            {
                "query": {
                    "contract_id": student_concept_queries.ALIGNMENT_RESULT_CONTRACT_VERSION,
                    "workspace_scope": scope,
                    "workspace_uid": (
                        f"personal:{source.owner_user_id}"
                        if scope == "PERSONAL"
                        else f"course:{getattr(source, 'course_id', '')}"
                    ),
                    "visibility": "PRIVATE",
                    "authority": "NON_OFFICIAL",
                    "publication_status": "NOT_APPLICABLE",
                    "alignment_status": "NOT_READY",
                    "display_mode": "NO_RELIABLE_ALIGNMENT",
                    "uncertain": False,
                    "recommended_chinese_concept": None,
                    "english_evidence": [],
                    "chinese_evidence": [],
                    "chinese_candidates": [],
                    "generated_hints": [],
                    "source_availability": "SOURCE_UNAVAILABLE",
                    "evidence_availability": "UNAVAILABLE",
                    "student_explanation": "资料尚未完成处理、已被删除，或缺少可审计来源信息。",
                    "student_risk_summary": [reason],
                    "reason_code": reason,
                    "learning_support": student_concept_queries.build_student_learning_support(
                        {},
                        alignment_status="NOT_READY",
                        recommended_chinese_concept=None,
                    ),
                },
                "idempotent_replay": False,
            },
            audit_context=context,
        )

    def get_owned_query(user, query_uid):
        query = models.StudentConceptQuery.query.filter_by(
            query_uid=query_uid, student_id=user.id
        ).first()
        if query is None:
            return None
        if query.workspace_scope == "MANAGED_COURSE" and not membership_active(
            user.id, query.course_id
        ):
            return None
        return query

    def source_availability(query):
        source = models.KnowledgeSource.query.filter_by(
            source_uid=query.source_uid
        ).first()
        if source is None:
            return "SOURCE_UNAVAILABLE"
        if (
            str(source.status or "").lower() != "active"
            or not bool(source.allow_student_search)
        ):
            return "SOURCE_UNAVAILABLE"
        if query.workspace_scope == "PERSONAL" and (
            str(source.scope_type or "").lower() != "personal"
            or str(source.owner_user_id) != str(query.student_id)
        ):
            return "SOURCE_UNAVAILABLE"
        if query.workspace_scope == "MANAGED_COURSE" and not membership_active(
            query.student_id, query.course_id
        ):
            return "SOURCE_UNAVAILABLE"
        return "AVAILABLE"

    def personal_state(query):
        record = models.PersonalLearningRecord.query.filter_by(
            student_id=query.student_id, result_uid=query.result_uid
        ).first()
        if record is None:
            return {
                "saved": False, "note": "", "understanding_state": "",
                "last_viewed_at": "", "version": 0,
                "visibility": "PRIVATE", "authority": "NON_OFFICIAL",
                "publication_status": "NOT_APPLICABLE",
            }
        return {
            "record_uid": record.record_uid,
            "saved": bool(record.saved),
            "note": record.personal_note,
            "understanding_state": record.understanding_state,
            "last_viewed_at": record.last_viewed_at,
            "version": record.version,
            "visibility": "PRIVATE",
            "authority": "NON_OFFICIAL",
            "publication_status": "NOT_APPLICABLE",
        }

    def serialize_query(query):
        raw = json.loads(query.result_json or "{}")
        raw["personal_state"] = personal_state(query)
        serialized = student_concept_queries.serialize_alignment_result(raw)
        serialized["processing_status"] = str(query.processing_status or "")
        serialized["error_code"] = str(query.error_code or "")
        serialized["source_availability"] = source_availability(query)
        if serialized["source_availability"] == "SOURCE_UNAVAILABLE":
            serialized = student_concept_queries.redact_unavailable_source_result(
                serialized
            )
            serialized["source_availability"] = "SOURCE_UNAVAILABLE"
            serialized["evidence_availability"] = "UNAVAILABLE"
            serialized["source_unavailable_reason"] = "PERSONAL_MATERIAL_DELETED_OR_INACCESSIBLE"
        else:
            serialized["evidence_availability"] = "AVAILABLE"
            serialized["source_unavailable_reason"] = ""
        return serialized

    def audit(
        event_type,
        *,
        user,
        query,
        request_id,
        action="",
        result="success",
        mutation_fingerprint="",
    ):
        core.audit_record_service.create_audit_record(
            db.session,
            core.audit_record_model,
            {
                "event_type": event_type,
                "target_type": "student_concept_query",
                "target_uid": query.query_uid,
                "result": result,
                "input_payload": {
                    "query_uid": query.query_uid,
                    "student_id": user.id,
                    "workspace_uid": query.workspace_uid,
                    "source_uid": query.source_uid,
                    "action": action,
                    "mutation_fingerprint": mutation_fingerprint,
                },
                "output_payload": {"status": query.processing_status},
                "changed_fields": [action] if action else [],
            },
            audit_context={"actor_id": user.id, "actor_role": "student", "request_id": request_id},
            now_fn=core.current_time_text,
            commit=False,
        )

    def mutation_audit(*, event_type, user, query, request_id):
        if not request_id:
            return None, ""
        existing = core.audit_record_model.query.filter_by(
            event_type=event_type,
            target_uid=query.query_uid,
            actor_id=user.id,
            request_id=request_id,
        ).order_by(core.audit_record_model.id.desc()).first()
        if existing is None:
            return None, ""
        try:
            payload = json.loads(existing.input_payload or "{}")
        except (TypeError, ValueError):
            payload = {}
        return existing, str(payload.get("mutation_fingerprint") or "")

    def idempotency_key(*, required=False):
        value = str(request.headers.get("Idempotency-Key") or "").strip()
        if (required and not value) or len(value) > 120 or any(ord(char) < 32 for char in value):
            raise student_concept_queries.StudentConceptQueryError(
                "STUDENT_PERSONAL_RECORD_IDEMPOTENCY_KEY_INVALID",
                "A bounded Idempotency-Key is required.",
            )
        return value

    def notebook_item(query, serialized=None):
        result = dict(serialized or serialize_query(query))
        state = dict(result.get("personal_state") or {})
        source = models.KnowledgeSource.query.filter_by(
            source_uid=query.source_uid
        ).first()
        course = (
            db.session.get(models.Course, query.course_id)
            if query.course_id is not None
            else None
        )
        recommended = result.get("recommended_chinese_concept")
        note = str(state.get("note") or "")
        return {
            "contract_id": student_concept_queries.PERSONAL_NOTEBOOK_CONTRACT_VERSION,
            "query_uid": query.query_uid,
            "result_uid": query.result_uid,
            "workspace_scope": query.workspace_scope,
            "workspace_uid": query.workspace_uid,
            "visibility": "PRIVATE",
            "authority": "NON_OFFICIAL",
            "publication_status": "NOT_APPLICABLE",
            "alignment_status": result.get("alignment_status"),
            "display_mode": result.get("display_mode"),
            "uncertain": bool(result.get("uncertain")),
            "english_concept": str(result.get("english_term") or query.selected_text or "")[:220],
            "recommended_chinese_concept": recommended,
            "candidate_count": len(result.get("chinese_candidates") or []),
            "source_uid": query.source_uid,
            "source_title": str(
                getattr(source, "title", "") or getattr(source, "name", "") or ""
            )[:220],
            "course_name": str(getattr(course, "name", "") or "")[:220],
            "source_availability": result.get("source_availability"),
            "evidence_availability": result.get("evidence_availability"),
            "evidence_complete": bool(result.get("evidence_complete")),
            "saved": bool(state.get("saved")),
            "understanding_state": str(state.get("understanding_state") or ""),
            "last_viewed_at": str(state.get("last_viewed_at") or ""),
            "note_preview": note[:student_concept_queries.MAX_NOTEBOOK_NOTE_PREVIEW_CHARS],
            "personal_state": {
                "record_uid": str(state.get("record_uid") or ""),
                "saved": bool(state.get("saved")),
                "understanding_state": str(state.get("understanding_state") or ""),
                "last_viewed_at": str(state.get("last_viewed_at") or ""),
                "version": int(state.get("version") or 0),
                "visibility": "PRIVATE",
                "authority": "NON_OFFICIAL",
                "publication_status": "NOT_APPLICABLE",
            },
            "created_at": str(query.created_at or ""),
            "updated_at": str(state.get("last_viewed_at") or query.updated_at or query.created_at or ""),
        }

    def create_query():
        context = core.get_route_audit_context()
        user, response = student(context)
        if response:
            return core.attach_request_id_to_response(response, context)
        context = core.get_route_audit_context(user)
        data = request.get_json(silent=True) or {}
        scope = str(data.get("workspace_scope") or "").strip().upper()
        source = models.KnowledgeSource.query.filter_by(
            source_uid=str(data.get("source_uid") or "").strip()
        ).first()
        if source is None or not source_owned_or_member(user, source, scope):
            return error("STUDENT_CONCEPT_SOURCE_NOT_ACCESSIBLE", "Source is not available.", 404, context)
        if not source_access(user, source, scope):
            return lifecycle_not_ready(
                "STUDENT_CONCEPT_SOURCE_NOT_READY", context, source=source
            )
        chunk = models.KnowledgeChunk.query.filter_by(
            chunk_uid=str(data.get("chunk_uid") or "").strip(),
            source_uid=source.source_uid,
        ).first()
        if chunk is None or str(chunk.language or "").lower() != "en":
            return error("STUDENT_CONCEPT_SOURCE_CHUNK_INVALID", "English source chunk is not available.", 404, context)
        if (
            str(source.scope_type or "").lower() == "personal"
            and source.document_id is not None
            and not (
                str(chunk.parse_block_uid or "").strip()
                and chunk.page_number is not None
            )
        ):
            return lifecycle_not_ready(
                "STUDENT_CONCEPT_PROVENANCE_INCOMPLETE", context, source=source
            )
        try:
            selection = student_concept_queries.validate_selection(
                chunk,
                selected_text=data.get("selected_text"),
                selection_start=data.get("selection_start"),
                selection_end=data.get("selection_end"),
            )
        except student_concept_queries.StudentConceptQueryError as exc:
            return error(exc.reason_code, str(exc), 400, context)
        workspace_uid = (
            f"personal:{user.id}" if scope == "PERSONAL" else f"course:{source.course_id}"
        )
        source_version = str(source.version or 1)
        sources = models.KnowledgeSource.query.filter_by(language="zh", status="active").all()
        evidence_scope = student_concept_queries.resolve_evidence_scope(
            sources,
            workspace_scope=scope,
            student_id=user.id,
            course_id=source.course_id if scope == "MANAGED_COURSE" else None,
            allow_platform_governed=False,
        )
        # Personal/course evidence is the first tier. Platform-governed Chinese
        # evidence is an explicit fallback only when the workspace has no
        # eligible independent Chinese source.
        if (
            not evidence_scope.allowed_source_uids
            and bool(current_app.config.get("STUDENT_ALLOW_PLATFORM_EVIDENCE", False))
        ):
            evidence_scope = student_concept_queries.resolve_evidence_scope(
                sources,
                workspace_scope=scope,
                student_id=user.id,
                course_id=source.course_id if scope == "MANAGED_COURSE" else None,
                allow_platform_governed=True,
            )
        fingerprint = student_concept_queries.build_query_fingerprint(
            student_uid=user.id,
            workspace_scope=scope,
            workspace_uid=workspace_uid,
            source_uid=source.source_uid,
            source_version=source_version,
            chunk_uid=chunk.chunk_uid,
            selection_start=selection.selection_start,
            selection_end=selection.selection_end,
            selected_text=selection.selected_text,
            evidence_scope_id=evidence_scope.scope_id,
        )
        existing = models.StudentConceptQuery.query.filter_by(
            student_id=user.id, query_fingerprint=fingerprint
        ).first()
        if existing is not None:
            return core.api_success_with_audit_context(
                {"query": serialize_query(existing), "idempotent_replay": True},
                audit_context=context,
            )
        now = core.current_time_text()
        query_uid, result_uid = str(uuid.uuid4()), str(uuid.uuid4())
        runner = current_app.config.get("STUDENT_ALIGNMENT_RUNNER")
        try:
            if not evidence_scope.allowed_source_uids:
                raise student_concept_queries.StudentConceptQueryError(
                    "STUDENT_CONCEPT_CHINESE_EVIDENCE_UNAVAILABLE",
                    "No governed Chinese evidence is available in this workspace.",
                )
            if runner is not None:
                workflow = runner(
                    session=db.session,
                    english_term=selection.selected_text,
                    english_context=selection.bounded_context,
                    allowed_source_uids=evidence_scope.allowed_source_uids,
                    english_source_uid=source.source_uid,
                )
            else:
                embedding_backend = current_app.config.get(
                    "STUDENT_CROSS_LANGUAGE_EMBEDDING_BACKEND"
                )
                reranker_backend = current_app.config.get(
                    "STUDENT_BILINGUAL_RERANKER_BACKEND"
                )
                workflow = bilingual_evidence_workflow.retrieve_bilingual_evidence(
                    db.session,
                    models.KnowledgeChunk,
                    models.KnowledgeSource,
                    selection.selected_text,
                    course=source.course if scope == "MANAGED_COURSE" else "",
                    chapter=chunk.chapter,
                    filters={
                        "source_uids": evidence_scope.allowed_source_uids,
                        "english_source_uid": source.source_uid,
                        # Active, governed sources may carry review-grade parse
                        # labels. Keep that evidence visible and let the frozen
                        # qualification policy propagate uncertainty.
                        "include_needs_review": True,
                        # The student selected this exact governed English
                        # chunk. Review-grade parser risks must propagate into
                        # qualification instead of silently erasing the
                        # English evidence side.
                        "english_include_needs_review": True,
                    },
                    auto_generate_chinese_candidates=True,
                    english_candidate_uid=f"student:{query_uid}",
                    normalized_english_term=selection.selected_text.casefold(),
                    english_context=selection.bounded_context,
                    discipline=source.discipline,
                    cross_language_embedding_backend=embedding_backend,
                    bilingual_reranker_backend=reranker_backend,
                )
            raw = student_concept_queries.build_raw_alignment_result(
                workflow,
                query_uid=query_uid,
                result_uid=result_uid,
                workspace_scope=scope,
                workspace_uid=workspace_uid,
                source_uid=source.source_uid,
                source_version=source_version,
                selection=selection,
                created_at=now,
            )
            raw["evidence_scope"] = {
                "scope_id": evidence_scope.scope_id,
                "tier": evidence_scope.evidence_tier,
                "platform_governed_included": (
                    evidence_scope.platform_governed_included
                ),
                "source_count": len(evidence_scope.allowed_source_uids),
            }
            status = "completed"
            error_code = ""
        except Exception as exc:
            # Query ownership and validated source context remain useful; fail closed.
            failure_code = (
                exc.reason_code
                if isinstance(exc, student_concept_queries.StudentConceptQueryError)
                else "STUDENT_CONCEPT_ALIGNMENT_FAILED"
            )
            raw = {
                "query_uid": query_uid, "result_uid": result_uid,
                "workspace_scope": scope, "workspace_uid": workspace_uid,
                "source_uid": source.source_uid, "source_version": source_version,
                "english_term": selection.selected_text, "selected_text": selection.selected_text,
                "bounded_context": selection.bounded_context,
                "english_evidence": [{
                    "source_uid": source.source_uid, "chunk_uid": chunk.chunk_uid,
                    "page_number": chunk.page_number, "block_uid": chunk.parse_block_uid,
                    "span_start": selection.selection_start, "span_end": selection.selection_end,
                    "snippet": selection.bounded_context,
                }],
                "chinese_evidence": [], "chinese_candidates": [],
                "selected_candidate": None, "qualification": None,
                "risk_labels": [failure_code.lower()], "generated_hints": [],
                "evidence_scope": {
                    "scope_id": evidence_scope.scope_id,
                    "tier": evidence_scope.evidence_tier,
                    "platform_governed_included": (
                        evidence_scope.platform_governed_included
                    ),
                    "source_count": len(evidence_scope.allowed_source_uids),
                },
                "created_at": now, "updated_at": now,
            }
            status = "failed_closed"
            error_code = failure_code
        query = models.StudentConceptQuery(
            query_uid=query_uid, result_uid=result_uid, student_id=user.id,
            workspace_scope=scope, workspace_uid=workspace_uid,
            course_id=source.course_id if scope == "MANAGED_COURSE" else None,
            source_uid=source.source_uid, source_version=source_version,
            chunk_uid=chunk.chunk_uid, selected_text=selection.selected_text,
            selection_start=selection.selection_start, selection_end=selection.selection_end,
            query_fingerprint=fingerprint,
            request_id=str(request.headers.get("Idempotency-Key") or data.get("request_id") or "")[:120],
            evidence_scope_id=evidence_scope.scope_id,
            allowed_source_uids_json=json.dumps(evidence_scope.allowed_source_uids),
            result_json=json.dumps(raw, ensure_ascii=False, sort_keys=True),
            processing_status=status, error_code=error_code,
            created_at=now, updated_at=now,
        )
        db.session.add(query)
        audit("student_concept_query_created", user=user, query=query, request_id=query.request_id)
        db.session.commit()
        return core.api_success_with_audit_context(
            {"query": serialize_query(query), "idempotent_replay": False},
            audit_context=context,
        )

    def list_materials():
        context = core.get_route_audit_context()
        user, response = student(context)
        if response:
            return core.attach_request_id_to_response(response, context)
        context = core.get_route_audit_context(user)
        items = []
        for source in models.KnowledgeSource.query.filter_by(language="en", status="active").all():
            scope = (
                "PERSONAL"
                if str(source.scope_type or "").lower() == "personal"
                else "MANAGED_COURSE"
            )
            if not source_access(user, source, scope):
                continue
            course = db.session.get(models.Course, source.course_id) if source.course_id else None
            items.append({
                "source_uid": source.source_uid,
                "source_version": str(source.version or 1),
                "title": str(source.title or source.name or "")[:220],
                "workspace_scope": scope,
                "workspace_uid": f"personal:{user.id}" if scope == "PERSONAL" else f"course:{source.course_id}",
                "course_name": getattr(course, "name", "") if course else "",
            })
        items.sort(key=lambda item: (item["workspace_scope"], item["title"], item["source_uid"]))
        return core.api_success_with_audit_context({"items": items}, audit_context=context)

    def list_material_chunks(source_uid):
        context = core.get_route_audit_context()
        user, response = student(context)
        if response:
            return core.attach_request_id_to_response(response, context)
        context = core.get_route_audit_context(user)
        source = models.KnowledgeSource.query.filter_by(source_uid=source_uid, language="en", status="active").first()
        scope = (
            "PERSONAL"
            if source is not None and str(source.scope_type or "").lower() == "personal"
            else "MANAGED_COURSE"
        )
        if source is None or not source_access(user, source, scope):
            return error("STUDENT_CONCEPT_SOURCE_NOT_ACCESSIBLE", "Source is not available.", 404, context)
        chunks = models.KnowledgeChunk.query.filter_by(source_uid=source.source_uid, language="en", status="active").order_by(
            models.KnowledgeChunk.chunk_index.asc(), models.KnowledgeChunk.id.asc()
        ).limit(100).all()
        return core.api_success_with_audit_context(
            {
                "source": {
                    "source_uid": source.source_uid,
                    "title": str(source.title or source.name or "")[:220],
                    "source_version": str(source.version or 1),
                    "workspace_scope": scope,
                    "course_id": source.course_id,
                },
                "items": [{
                    "chunk_uid": chunk.chunk_uid,
                    "text": str(chunk.content or "")[:4000],
                    "page_number": chunk.page_number,
                    "block_uid": chunk.parse_block_uid,
                    "heading_path": chunk.source_section or chunk.chapter,
                } for chunk in chunks],
            },
            audit_context=context,
        )

    def reader_source(user, source_uid, context):
        source = models.KnowledgeSource.query.filter_by(
            source_uid=source_uid, language="en", status="active"
        ).first()
        scope = (
            "PERSONAL"
            if source is not None and str(source.scope_type or "").lower() == "personal"
            else "MANAGED_COURSE"
        )
        if source is None or not source_access(user, source, scope):
            return None, None, error(
                "STUDENT_CONCEPT_SOURCE_NOT_ACCESSIBLE",
                "Source is not available.",
                404,
                context,
            )
        return source, scope, None

    def material_reader(source_uid):
        context = core.get_route_audit_context()
        user, response = student(context)
        if response:
            return core.attach_request_id_to_response(response, context)
        context = core.get_route_audit_context(user)
        source, scope, failure = reader_source(user, source_uid, context)
        if failure:
            return failure
        raw_page = str(request.args.get("page") or "1").strip()
        try:
            page_number = int(raw_page)
        except (TypeError, ValueError):
            page_number = 0
        if page_number < 1:
            return error(
                "STUDENT_MATERIAL_READER_PAGE_INVALID",
                "Reader page is invalid.",
                400,
                context,
            )
        chunk_query = models.KnowledgeChunk.query.filter_by(
            source_uid=source.source_uid, language="en", status="active"
        )
        provenance_rows = db.session.query(
            models.KnowledgeChunk.page_number,
            models.KnowledgeChunk.parse_block_uid,
        ).filter_by(
            source_uid=source.source_uid, language="en", status="active"
        ).all()
        if any(page is None or not str(block or "").strip() for page, block in provenance_rows):
            return error(
                "STUDENT_MATERIAL_READER_PROVENANCE_INCOMPLETE",
                "A parsed material block is missing page or block provenance.",
                409,
                context,
            )
        available_pages = sorted({int(page) for page, _ in provenance_rows})
        if page_number not in available_pages:
            return error(
                "STUDENT_MATERIAL_READER_PAGE_INVALID",
                "Reader page is not available.",
                400,
                context,
            )
        chunks = chunk_query.filter_by(page_number=page_number).order_by(
            models.KnowledgeChunk.page_number.asc(),
            models.KnowledgeChunk.chunk_index.asc(),
            models.KnowledgeChunk.id.asc(),
        ).all()
        try:
            serialized_items = [
                student_concept_queries.serialize_material_reader_item(chunk)
                for chunk in chunks
            ]
        except student_concept_queries.StudentConceptQueryError as exc:
            return error(exc.reason_code, str(exc), 409, context)
        page_items = serialized_items
        document = (
            db.session.get(models.Document, source.document_id)
            if source.document_id is not None
            else None
        )
        parse_record = (
            models.DocumentParseRecord.query.filter_by(parse_uid=source.parse_uid).first()
            if str(source.parse_uid or "").strip()
            else None
        )
        course = db.session.get(models.Course, source.course_id) if source.course_id else None
        parsed_page_count = int(getattr(parse_record, "page_count", 0) or 0)
        page_count = max(parsed_page_count, max(available_pages, default=0))
        try:
            file_available = bool(
                document is not None
                and not str(document.deleted_at or "").strip()
                and str(document.file_type or source.file_type or "").lower() == "pdf"
                and material_file_exists(document)
            )
        except (FileNotFoundError, NotImplementedError, OSError, ValueError):
            file_available = False
        return core.api_success_with_audit_context(
            {
                "reader": {
                    "contract_id": student_concept_queries.MATERIAL_READER_CONTRACT_VERSION,
                    "source": {
                        "source_uid": source.source_uid,
                        "source_version": str(source.version or 1),
                        "title": str(source.title or source.name or "")[:220],
                        "workspace_scope": scope,
                        "workspace_uid": (
                            f"personal:{user.id}"
                            if scope == "PERSONAL"
                            else f"course:{source.course_id}"
                        ),
                        "course_name": getattr(course, "name", "") if course else "",
                        "file_type": str(
                            getattr(document, "file_type", "") or source.file_type or ""
                        ).lower(),
                        "file_available": file_available,
                        "parser_id": str(getattr(parse_record, "parser_name", "") or ""),
                        "parser_version": str(
                            getattr(parse_record, "parser_version", "") or ""
                        ),
                    },
                    "page": {
                        "number": page_number,
                        "page_count": page_count,
                        "available_pages": available_pages,
                        "previous_page": next(
                            (value for value in reversed(available_pages) if value < page_number),
                            None,
                        ),
                        "next_page": next(
                            (value for value in available_pages if value > page_number),
                            None,
                        ),
                        "block_count": len(page_items),
                    },
                    "items": page_items,
                }
            },
            audit_context=context,
        )

    def material_file(source_uid):
        context = core.get_route_audit_context()
        user, response = student(context)
        if response:
            return core.attach_request_id_to_response(response, context)
        context = core.get_route_audit_context(user)
        source, _, failure = reader_source(user, source_uid, context)
        if failure:
            return failure
        document = (
            db.session.get(models.Document, source.document_id)
            if source.document_id is not None
            else None
        )
        if (
            document is None
            or str(document.deleted_at or "").strip()
            or str(document.file_type or source.file_type or "").lower() != "pdf"
        ):
            return error(
                "STUDENT_MATERIAL_FILE_NOT_AVAILABLE",
                "The original PDF is not available.",
                404,
                context,
            )
        try:
            if not material_file_exists(document):
                raise FileNotFoundError(source_uid)
            file_response = material_file_response(document)
        except (FileNotFoundError, NotImplementedError, OSError, ValueError):
            return error(
                "STUDENT_MATERIAL_FILE_NOT_AVAILABLE",
                "The original PDF is not available.",
                404,
                context,
            )
        file_response.headers["Cache-Control"] = "private, no-store"
        file_response.headers["X-Content-Type-Options"] = "nosniff"
        file_response.headers["Content-Security-Policy"] = "frame-ancestors 'self'"
        return file_response

    def get_query(query_uid):
        context = core.get_route_audit_context()
        user, response = student(context)
        if response:
            return core.attach_request_id_to_response(response, context)
        context = core.get_route_audit_context(user)
        query = get_owned_query(user, query_uid)
        if query is None:
            return error("STUDENT_CONCEPT_QUERY_NOT_FOUND", "Query is not available.", 404, context)
        return core.api_success_with_audit_context({"query": serialize_query(query)}, audit_context=context)

    def list_notebook():
        context = core.get_route_audit_context()
        user, response = student(context)
        if response:
            return core.attach_request_id_to_response(response, context)
        context = core.get_route_audit_context(user)
        try:
            filters = student_concept_queries.validate_notebook_filters(request.args)
        except student_concept_queries.StudentConceptQueryError as exc:
            return error(exc.reason_code, str(exc), 400, context)

        accessible = []
        for query in models.StudentConceptQuery.query.filter_by(
            student_id=user.id
        ).order_by(
            models.StudentConceptQuery.updated_at.desc(),
            models.StudentConceptQuery.id.desc(),
        ).all():
            if query.workspace_scope == "MANAGED_COURSE" and not membership_active(
                user.id, query.course_id
            ):
                continue
            serialized = serialize_query(query)
            accessible.append((query, serialized, notebook_item(query, serialized)))

        summary = {
            "history_total": len(accessible),
            "saved_total": sum(bool(item[2]["saved"]) for item in accessible),
            "understood_total": sum(
                item[2]["understanding_state"] == "UNDERSTOOD" for item in accessible
            ),
            "still_confused_total": sum(
                item[2]["understanding_state"] == "STILL_CONFUSED" for item in accessible
            ),
            "personal_total": sum(
                item[0].workspace_scope == "PERSONAL" for item in accessible
            ),
            "managed_course_total": sum(
                item[0].workspace_scope == "MANAGED_COURSE" for item in accessible
            ),
        }
        selected = []
        query_text = filters["q"].casefold()
        for query, serialized, item in accessible:
            state = serialized.get("personal_state") or {}
            if filters["view"] == "SAVED" and not bool(state.get("saved")):
                continue
            if (
                filters["view"] == "UNDERSTOOD"
                and str(state.get("understanding_state") or "") != "UNDERSTOOD"
            ):
                continue
            if (
                filters["view"] == "STILL_CONFUSED"
                and str(state.get("understanding_state") or "") != "STILL_CONFUSED"
            ):
                continue
            if filters["workspace_scope"] and query.workspace_scope != filters["workspace_scope"]:
                continue
            if (
                filters["alignment_status"]
                and serialized.get("alignment_status") != filters["alignment_status"]
            ):
                continue
            if query_text:
                searchable = "\n".join((
                    item["english_concept"],
                    str((item.get("recommended_chinese_concept") or {}).get("text") or ""),
                    str(state.get("note") or ""),
                    item["source_title"],
                    item["course_name"],
                )).casefold()
                if query_text not in searchable:
                    continue
            selected.append(item)
        selected.sort(
            key=lambda item: (item["updated_at"], item["query_uid"]), reverse=True
        )
        total = len(selected)
        offset = (filters["page"] - 1) * filters["per_page"]
        page_items = selected[offset:offset + filters["per_page"]]
        return core.api_success_with_audit_context(
            {
                "contract_id": student_concept_queries.PERSONAL_NOTEBOOK_CONTRACT_VERSION,
                "items": page_items,
                "summary": summary,
                "filters": filters,
                "pagination": {
                    "page": filters["page"],
                    "per_page": filters["per_page"],
                    "total": total,
                    "has_next": offset + filters["per_page"] < total,
                },
            },
            audit_context=context,
        )

    def notebook_detail(query_uid):
        context = core.get_route_audit_context()
        user, response = student(context)
        if response:
            return core.attach_request_id_to_response(response, context)
        context = core.get_route_audit_context(user)
        query = get_owned_query(user, query_uid)
        if query is None:
            return error("STUDENT_CONCEPT_QUERY_NOT_FOUND", "Query is not available.", 404, context)
        serialized = serialize_query(query)
        return core.api_success_with_audit_context(
            {
                "contract_id": student_concept_queries.PERSONAL_NOTEBOOK_CONTRACT_VERSION,
                "notebook_item": notebook_item(query, serialized),
                "query": serialized,
            },
            audit_context=context,
        )

    def revisit_notebook_item(query_uid):
        context = core.get_route_audit_context()
        user, response = student(context)
        if response:
            return core.attach_request_id_to_response(response, context)
        context = core.get_route_audit_context(user)
        query = get_owned_query(user, query_uid)
        if query is None:
            return error("STUDENT_CONCEPT_QUERY_NOT_FOUND", "Query is not available.", 404, context)
        data = request.get_json(silent=True) or {}
        if set(data) - {"expected_version"}:
            return error(
                "STUDENT_PERSONAL_RECORD_FIELDS_INVALID",
                "Personal state fields are invalid.",
                400,
                context,
            )
        try:
            key = idempotency_key(required=True)
        except student_concept_queries.StudentConceptQueryError as exc:
            return error(exc.reason_code, str(exc), 400, context)
        try:
            fingerprint = student_concept_queries.personal_record_mutation_fingerprint(
                query_uid=query.query_uid,
                action="REVISIT",
                changes={},
                secret=current_app.secret_key,
            )
        except student_concept_queries.StudentConceptQueryError as exc:
            return error(exc.reason_code, str(exc), 503, context)
        previous, previous_fingerprint = mutation_audit(
            event_type="personal_learning_record_revisited",
            user=user,
            query=query,
            request_id=key,
        )
        if previous is not None:
            if previous_fingerprint != fingerprint:
                return error(
                    "STUDENT_PERSONAL_RECORD_IDEMPOTENCY_CONFLICT",
                    "Idempotency key was already used for another personal-state mutation.",
                    409,
                    context,
                )
            return core.api_success_with_audit_context(
                {"query": serialize_query(query), "idempotent_replay": True},
                audit_context=context,
            )
        record = models.PersonalLearningRecord.query.filter_by(
            student_id=user.id, result_uid=query.result_uid
        ).first()
        current_version = int(record.version or 0) if record else 0
        try:
            expected_version = int(data.get("expected_version"))
        except (TypeError, ValueError):
            expected_version = -1
        if expected_version != current_version:
            return error(
                "STUDENT_PERSONAL_RECORD_VERSION_CONFLICT",
                "Personal record version is stale.",
                409,
                context,
            )
        now = core.current_time_text()
        if record is None:
            record = models.PersonalLearningRecord(
                student_id=user.id,
                query_uid=query.query_uid,
                result_uid=query.result_uid,
                workspace_scope=query.workspace_scope,
                workspace_uid=query.workspace_uid,
                created_at=now,
            )
            db.session.add(record)
        record.last_viewed_at = now
        record.version = current_version + 1
        record.updated_at = now
        audit(
            "personal_learning_record_revisited",
            user=user,
            query=query,
            request_id=key,
            action="revisit",
            mutation_fingerprint=fingerprint,
        )
        db.session.commit()
        return core.api_success_with_audit_context(
            {"query": serialize_query(query), "idempotent_replay": False},
            audit_context=context,
        )

    def personal_record(query_uid):
        context = core.get_route_audit_context()
        user, response = student(context)
        if response:
            return core.attach_request_id_to_response(response, context)
        context = core.get_route_audit_context(user)
        query = get_owned_query(user, query_uid)
        if query is None:
            return error("STUDENT_CONCEPT_QUERY_NOT_FOUND", "Query is not available.", 404, context)
        if request.method == "GET":
            return core.api_success_with_audit_context(
                {"personal_state": personal_state(query)},
                audit_context=context,
            )
        data = request.get_json(silent=True) or {}
        allowed = {"saved", "note", "understanding_state", "expected_version"}
        if set(data) - allowed:
            return error("STUDENT_PERSONAL_RECORD_FIELDS_INVALID", "Personal state fields are invalid.", 400, context)
        state = str(data.get("understanding_state") or "").strip().upper()
        if state not in {"", "UNDERSTOOD", "STILL_CONFUSED"}:
            return error("STUDENT_PERSONAL_RECORD_STATE_INVALID", "Understanding state is invalid.", 400, context)
        record = models.PersonalLearningRecord.query.filter_by(
            student_id=user.id, result_uid=query.result_uid
        ).first()
        try:
            key = idempotency_key(required=False)
        except student_concept_queries.StudentConceptQueryError as exc:
            return error(exc.reason_code, str(exc), 400, context)
        changes = {name: data[name] for name in ("saved", "note", "understanding_state") if name in data}
        try:
            fingerprint = student_concept_queries.personal_record_mutation_fingerprint(
                query_uid=query.query_uid,
                action="UPDATE",
                changes=changes,
                secret=current_app.secret_key,
            )
        except student_concept_queries.StudentConceptQueryError as exc:
            return error(exc.reason_code, str(exc), 503, context)
        previous, previous_fingerprint = mutation_audit(
            event_type="personal_learning_record_updated",
            user=user,
            query=query,
            request_id=key,
        )
        if previous is not None:
            if previous_fingerprint != fingerprint:
                return error(
                    "STUDENT_PERSONAL_RECORD_IDEMPOTENCY_CONFLICT",
                    "Idempotency key was already used for another personal-state mutation.",
                    409,
                    context,
                )
            return core.api_success_with_audit_context(
                {
                    "query": serialize_query(query),
                    "personal_state": personal_state(query),
                    "idempotent_replay": True,
                },
                audit_context=context,
            )
        expected = data.get("expected_version")
        current_version = record.version if record else 0
        try:
            expected_version = int(expected)
        except (TypeError, ValueError):
            expected_version = -1
        if expected_version != current_version:
            return error("STUDENT_PERSONAL_RECORD_VERSION_CONFLICT", "Personal record version is stale.", 409, context)
        now = core.current_time_text()
        if record is None:
            record = models.PersonalLearningRecord(
                student_id=user.id, query_uid=query.query_uid, result_uid=query.result_uid,
                workspace_scope=query.workspace_scope, workspace_uid=query.workspace_uid,
                created_at=now,
            )
            db.session.add(record)
        if "saved" in data:
            record.saved = bool(data["saved"])
        if "note" in data:
            record.personal_note = str(data["note"] or "")[:4000]
        if "understanding_state" in data:
            record.understanding_state = state
        record.last_viewed_at = now
        record.version = current_version + 1
        record.updated_at = now
        audit(
            "personal_learning_record_updated", user=user, query=query,
            request_id=key,
            action="personal_state",
            mutation_fingerprint=fingerprint,
        )
        db.session.commit()
        return core.api_success_with_audit_context(
            {
                "query": serialize_query(query),
                "personal_state": personal_state(query),
                "idempotent_replay": False,
            },
            audit_context=context,
        )

    app.add_url_rule("/api/student/concept-queries", view_func=create_query, methods=["POST"])
    app.add_url_rule("/api/student/concept-materials", view_func=list_materials, methods=["GET"])
    app.add_url_rule(
        "/api/student/concept-materials/<source_uid>/chunks",
        view_func=list_material_chunks,
        methods=["GET"],
    )
    app.add_url_rule(
        "/api/student/concept-materials/<source_uid>/reader",
        view_func=material_reader,
        methods=["GET"],
    )
    app.add_url_rule(
        "/api/student/concept-materials/<source_uid>/file",
        view_func=material_file,
        methods=["GET"],
    )
    app.add_url_rule("/api/student/concept-queries/<query_uid>", view_func=get_query, methods=["GET"])
    app.add_url_rule(
        "/api/student/personal-concept-notebook",
        view_func=list_notebook,
        methods=["GET"],
    )
    app.add_url_rule(
        "/api/student/personal-concept-notebook/<query_uid>",
        view_func=notebook_detail,
        methods=["GET"],
    )
    app.add_url_rule(
        "/api/student/personal-concept-notebook/<query_uid>/revisit",
        view_func=revisit_notebook_item,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/student/concept-queries/<query_uid>/personal-record",
        view_func=personal_record,
        methods=["GET", "PUT"],
    )
    registered.add(marker)
