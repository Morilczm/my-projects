#!/usr/bin/env python3
"""Seed repeatable Concept Card review demo data.

The seed is intentionally local and deterministic. It creates only clearly
marked demo records and never calls external providers or reads API keys.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from services import concept_alignment_cards
from services import concept_card_review
from services import course_review_policy
from services import student_course_access


DEMO_COURSE = "DEMO Signals and Systems"
DEMO_HIDDEN_COURSE = "DEMO Hidden Course"
DEMO_CHAPTER = "Frequency Domain"
DEMO_CREATED_BY = "demo_seed"
DEMO_PASSWORDS = {
    "teacher": "Teacher1234",
    "reviewer": "Reviewer1234",
    "admin": "Admin1234",
    "student": "Student1234",
    "student2": "Student2234",
}
DEMO_USERS = {
    "teacher": {
        "username": "demo_review_teacher",
        "email": "review.teacher@lexibridge.local",
        "display_name": "Demo Review Teacher",
    },
    "reviewer": {
        "username": "demo_bilingual_reviewer",
        "email": "review.reviewer@lexibridge.local",
        "display_name": "Demo Bilingual Reviewer",
        "role": "reviewer",
    },
    "admin": {
        "username": "demo_review_admin",
        "email": "review.admin@lexibridge.local",
        "display_name": "Demo Review Admin",
    },
    "student": {
        "username": "demo_review_student",
        "email": "review.student@lexibridge.local",
        "display_name": "Demo Review Student",
        "role": "student",
    },
    "student2": {
        "username": "demo_review_student_two",
        "email": "review.student2@lexibridge.local",
        "display_name": "Demo Review Student Two",
        "role": "student",
    },
}


def _now(app_module: Any) -> str:
    return app_module.current_time_text()


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, sort_keys=True)


def _loads(value: Any, fallback: Any) -> Any:
    if value in ("", None):
        return fallback
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


def _delete_query(query) -> None:
    query.delete(synchronize_session=False)


def reset_review_demo_data(app_module: Any) -> None:
    """Delete only records in the review-demo namespace."""
    db = app_module.db
    demo_courses = [DEMO_COURSE, DEMO_HIDDEN_COURSE]
    card_uids = [
        row.card_uid
        for row in app_module.ConceptAlignmentCard.query.filter(app_module.ConceptAlignmentCard.course.in_(demo_courses)).all()
    ]
    source_uids = [
        row.source_uid
        for row in app_module.KnowledgeSource.query.filter(app_module.KnowledgeSource.course.in_(demo_courses)).all()
    ]
    user_ids = [
        row.id
        for row in app_module.User.query.filter(
            app_module.User.email.in_([data["email"] for data in DEMO_USERS.values()])
        ).all()
    ]
    courses = app_module.Course.query.filter(app_module.Course.name.in_(demo_courses)).all()
    policy_uids = [
        row.policy_uid
        for row in app_module.CourseStudentVisibilityPolicy.query.filter(app_module.CourseStudentVisibilityPolicy.course.in_(demo_courses)).all()
    ]
    membership_uids = [
        row.membership_uid
        for row in app_module.StudentCourseMembership.query.filter(app_module.StudentCourseMembership.course.in_(demo_courses)).all()
    ]

    if card_uids:
        _delete_query(app_module.StudentConceptCardState.query.filter(app_module.StudentConceptCardState.card_uid.in_(card_uids)))
        _delete_query(app_module.Feedback.query.filter(
            app_module.Feedback.feedback_source == "student_concept_card",
            app_module.Feedback.actual_result.in_(card_uids),
        ))
        _delete_query(app_module.ConceptCardReviewAssignment.query.filter(app_module.ConceptCardReviewAssignment.card_uid.in_(card_uids)))
        _delete_query(app_module.ConceptCardReviewRecord.query.filter(app_module.ConceptCardReviewRecord.card_uid.in_(card_uids)))
        _delete_query(app_module.AlignmentVerificationRun.query.filter(app_module.AlignmentVerificationRun.card_uid.in_(card_uids)))
        _delete_query(app_module.AuditRecord.query.filter(app_module.AuditRecord.target_uid.in_(card_uids)))
        _delete_query(app_module.ConceptAlignmentCard.query.filter(app_module.ConceptAlignmentCard.card_uid.in_(card_uids)))
    if policy_uids or membership_uids:
        _delete_query(app_module.AuditRecord.query.filter(app_module.AuditRecord.target_uid.in_(policy_uids + membership_uids)))

    _delete_query(app_module.StudentCourseMembership.query.filter(app_module.StudentCourseMembership.course.in_(demo_courses)))
    _delete_query(app_module.CourseStudentVisibilityPolicy.query.filter(app_module.CourseStudentVisibilityPolicy.course.in_(demo_courses)))
    _delete_query(app_module.CourseReviewPermission.query.filter(app_module.CourseReviewPermission.course.in_(demo_courses)))
    _delete_query(app_module.CourseReviewPolicy.query.filter(app_module.CourseReviewPolicy.course.in_(demo_courses)))
    _delete_query(app_module.KnowledgeChunk.query.filter(app_module.KnowledgeChunk.course.in_(demo_courses)))
    if source_uids:
        _delete_query(app_module.KnowledgePermission.query.filter(app_module.KnowledgePermission.source_uid.in_(source_uids)))
    _delete_query(app_module.KnowledgeSource.query.filter(app_module.KnowledgeSource.course.in_(demo_courses)))

    for course in courses:
        _delete_query(app_module.CourseMember.query.filter_by(course_id=course.id))
        db.session.delete(course)

    if user_ids:
        _delete_query(app_module.AuthToken.query.filter(app_module.AuthToken.user_id.in_(user_ids)))
        _delete_query(app_module.CourseMember.query.filter(app_module.CourseMember.user_id.in_(user_ids)))
        _delete_query(app_module.User.query.filter(app_module.User.id.in_(user_ids)))

    db.session.commit()


def upsert_demo_user(app_module: Any, role: str) -> Any:
    data = DEMO_USERS[role]
    user = app_module.User.query.filter_by(email=data["email"]).first()
    if user is None:
        user = app_module.User(email=data["email"], username=data["username"])
        app_module.db.session.add(user)
    user.username = data["username"]
    user.display_name = data["display_name"]
    user.role = data.get("role", role)
    user.is_verified = True
    user.password_hash = app_module.generate_password_hash(DEMO_PASSWORDS[role], method="pbkdf2:sha256")
    user.created_at = user.created_at or _now(app_module)
    return user


def upsert_demo_course(app_module: Any, teacher: Any, *, course_name: str = DEMO_COURSE, course_code: str = "DEMO-SIGNALS") -> Any:
    course = app_module.Course.query.filter_by(name=course_name).first()
    if course is None:
        course = app_module.Course(name=course_name)
        app_module.db.session.add(course)
    course.course_code = course_code
    course.semester = "Demo"
    course.description = "Demo course for Concept Card review and student visibility workflow."
    course.language_mode = "bilingual"
    course.teacher_id = teacher.id
    course.status = "active"
    course.created_at = course.created_at or _now(app_module)
    app_module.db.session.flush()
    return course


def upsert_course_member(app_module: Any, course: Any, user: Any, role: str) -> Any:
    member = app_module.CourseMember.query.filter_by(course_id=course.id, user_id=user.id).first()
    if member is None:
        member = app_module.CourseMember(course_id=course.id, user_id=user.id)
        app_module.db.session.add(member)
    member.role = role
    member.role_in_course = role
    member.status = "active"
    member.created_at = member.created_at or _now(app_module)
    member.joined_at = member.joined_at or _now(app_module)
    return member


def upsert_review_policy_and_permissions(app_module: Any, users: dict[str, Any]) -> tuple[Any, Any, Any, Any]:
    policy, _ = course_review_policy.create_or_update_course_review_policy(
        app_module.db.session,
        app_module.CourseReviewPolicy,
        DEMO_COURSE,
        {
            "chapter": "",
            "require_human_review": True,
            "required_evidence_sides": "both",
            "min_required_evidence_count": 2,
            "allow_approve_with_missing_chinese_evidence": False,
            "allow_approve_with_missing_english_evidence": False,
            "allow_approve_with_unverified_alignment": False,
            "allow_approve_with_partial_text": False,
            "require_admin_for_override": True,
            "allow_teacher_override": False,
            "blocking_risk_labels": [
                "no_chinese_evidence",
                "bilingual_alignment_not_verified",
                "input_partial_text",
                "candidate_not_alignment_verified",
            ],
            "override_allowed_risk_labels": ["bilingual_alignment_not_verified", "candidate_not_alignment_verified"],
            "override_forbidden_risk_labels": ["no_chinese_evidence", "input_partial_text", "parse_failed"],
            "status": "active",
        },
        actor=users["admin"],
        now_fn=app_module.current_time_text,
    )
    teacher_permission, _ = course_review_policy.grant_course_review_permission(
        app_module.db.session,
        app_module.CourseReviewPermission,
        DEMO_COURSE,
        users["teacher"].id,
        {
            "reviewer_id": users["teacher"].id,
            "reviewer_role": "teacher",
            "permission_level": "approve",
            "status": "active",
        },
        actor=users["admin"],
        now_fn=app_module.current_time_text,
    )
    reviewer_permission, _ = course_review_policy.grant_course_review_permission(
        app_module.db.session,
        app_module.CourseReviewPermission,
        DEMO_COURSE,
        users["reviewer"].id,
        {
            "reviewer_id": users["reviewer"].id,
            "reviewer_role": "reviewer",
            "permission_level": "approve",
            "status": "active",
        },
        actor=users["admin"],
        now_fn=app_module.current_time_text,
    )
    admin_permission, _ = course_review_policy.grant_course_review_permission(
        app_module.db.session,
        app_module.CourseReviewPermission,
        DEMO_COURSE,
        users["admin"].id,
        {
            "reviewer_id": users["admin"].id,
            "reviewer_role": "admin",
            "permission_level": "admin",
            "status": "active",
        },
        actor=users["admin"],
        now_fn=app_module.current_time_text,
    )
    return policy, teacher_permission, reviewer_permission, admin_permission


def upsert_student_visibility_demo(app_module: Any, users: dict[str, Any]) -> tuple[Any, Any, Any, Any]:
    visible_policy, _ = student_course_access.create_or_update_course_student_visibility_policy(
        app_module.db.session,
        app_module.CourseStudentVisibilityPolicy,
        DEMO_COURSE,
        {
            "visibility": "enrolled_only",
            "allow_auditor_view": False,
            "allow_teacher_preview": True,
            "allow_cross_course_search": False,
            "status": "active",
        },
        actor=users["admin"],
        now_fn=app_module.current_time_text,
    )
    hidden_policy, _ = student_course_access.create_or_update_course_student_visibility_policy(
        app_module.db.session,
        app_module.CourseStudentVisibilityPolicy,
        DEMO_HIDDEN_COURSE,
        {
            "visibility": "enrolled_only",
            "allow_auditor_view": False,
            "allow_teacher_preview": True,
            "allow_cross_course_search": False,
            "status": "active",
        },
        actor=users["admin"],
        now_fn=app_module.current_time_text,
    )
    membership = student_course_access.add_student_course_membership(
        app_module.db.session,
        app_module.StudentCourseMembership,
        users["student"].id,
        DEMO_COURSE,
        {
            "role_in_course": "student",
            "status": "active",
        },
        actor=users["admin"],
        now_fn=app_module.current_time_text,
    )
    membership_two = student_course_access.add_student_course_membership(
        app_module.db.session,
        app_module.StudentCourseMembership,
        users["student2"].id,
        DEMO_COURSE,
        {
            "role_in_course": "student",
            "status": "active",
        },
        actor=users["admin"],
        now_fn=app_module.current_time_text,
    )
    return visible_policy, hidden_policy, membership, membership_two


def _upsert_source(app_module: Any, source_uid: str, title: str, language: str, role: str, source_type: str, course: str = DEMO_COURSE) -> Any:
    source = app_module.KnowledgeSource.query.filter_by(source_uid=source_uid).first()
    if source is None:
        source = app_module.KnowledgeSource(source_uid=source_uid)
        app_module.db.session.add(source)
    source.title = title
    source.name = title
    source.source_title = title
    source.course = course
    source.chapter = DEMO_CHAPTER
    source.language = language
    source.source_type = source_type
    source.source_role = role
    source.owner_type = "teacher"
    source.owner_id = DEMO_CREATED_BY
    source.visibility = "course"
    source.trust_level = "teacher_verified"
    source.parse_uid = f"demo-parse-{language}"
    source.source_filename = f"{source_uid}.txt"
    source.file_type = "txt"
    source.content_hash = _hash_text(f"{source_uid}:{title}")
    source.quality_status = "native_text_ok"
    source.quality_flags = _dumps([])
    source.status = "active"
    source.allow_student_search = True
    source.allow_derivative_cards = True
    source.created_at = source.created_at or _now(app_module)
    source.updated_at = _now(app_module)
    return source


def _upsert_chunk(
    app_module: Any,
    source: Any,
    chunk_uid: str,
    text: str,
    language: str,
    index: int,
    locator: str,
    quality_status: str = "native_text_ok",
    quality_flags: list[str] | None = None,
    status: str = "active",
) -> Any:
    chunk = app_module.KnowledgeChunk.query.filter_by(chunk_uid=chunk_uid).first()
    if chunk is None:
        chunk = app_module.KnowledgeChunk(chunk_uid=chunk_uid, document_id=0)
        app_module.db.session.add(chunk)
    chunk.source_uid = source.source_uid
    chunk.knowledge_source_id = source.id
    chunk.parse_uid = source.parse_uid
    chunk.parse_block_uid = f"{chunk_uid}-block"
    chunk.course = source.course
    chunk.title = source.title
    chunk.chapter = DEMO_CHAPTER
    chunk.chunk_index = index
    chunk.content = text
    chunk.normalized_text = text.lower()
    chunk.content_hash = _hash_text(text)
    chunk.source_locator = locator
    chunk.page_number = index
    chunk.block_type = "text"
    chunk.char_count = len(text)
    chunk.language = language
    chunk.visibility = "course"
    chunk.quality_status = quality_status
    chunk.quality_flags = _dumps(quality_flags or [])
    chunk.trust_level = "teacher_verified"
    chunk.status = status
    chunk.embedding_status = "not_started"
    chunk.created_at = chunk.created_at or _now(app_module)
    chunk.updated_at = _now(app_module)
    return chunk


def upsert_demo_knowledge(app_module: Any) -> dict[str, Any]:
    en_source = _upsert_source(
        app_module,
        "demo-review-source-en",
        "DEMO English Signals Notes",
        "en",
        "english_course_material",
        "course_material",
    )
    zh_source = _upsert_source(
        app_module,
        "demo-review-source-zh",
        "DEMO 中文信号系统讲义",
        "zh",
        "chinese_reference_material",
        "teacher_upload",
    )
    hidden_source = _upsert_source(
        app_module,
        "demo-review-source-hidden",
        "DEMO Hidden Course Notes",
        "en",
        "english_course_material",
        "course_material",
        course=DEMO_HIDDEN_COURSE,
    )
    app_module.db.session.flush()
    chunks = {
        "fourier_en": _upsert_chunk(
            app_module,
            en_source,
            "demo-review-chunk-fourier-en",
            "The Fourier transform represents a signal in the frequency domain using complex exponentials.",
            "en",
            1,
            "page:12",
        ),
        "fourier_zh": _upsert_chunk(
            app_module,
            zh_source,
            "demo-review-chunk-fourier-zh",
            "傅里叶变换用于将信号从时域转换到频域，是频域分析的核心工具。",
            "zh",
            2,
            "page:8",
        ),
        "transfer_en": _upsert_chunk(
            app_module,
            en_source,
            "demo-review-chunk-transfer-en",
            "A transfer function describes the input-output relationship of a linear time-invariant system.",
            "en",
            3,
            "page:21",
        ),
        "convergence_en": _upsert_chunk(
            app_module,
            en_source,
            "demo-review-chunk-convergence-en",
            "Convergence describes whether an infinite sequence or series approaches a finite limit.",
            "en",
            4,
            "page:34",
            quality_status="partial_text",
            quality_flags=["input_partial_text"],
            status="needs_review",
        ),
        "convergence_zh": _upsert_chunk(
            app_module,
            zh_source,
            "demo-review-chunk-convergence-zh",
            "收敛描述序列、级数或系统响应逐渐接近某一有限极限的性质。",
            "zh",
            5,
            "page:19",
            quality_status="partial_text",
            quality_flags=["input_partial_text"],
            status="needs_review",
        ),
        "impulse_en": _upsert_chunk(
            app_module,
            en_source,
            "demo-review-chunk-impulse-en",
            "The impulse response characterizes the output of a system when the input is a unit impulse.",
            "en",
            6,
            "page:27",
        ),
        "impulse_zh": _upsert_chunk(
            app_module,
            zh_source,
            "demo-review-chunk-impulse-zh",
            "冲激响应表示系统在单位冲激输入下产生的输出。",
            "zh",
            7,
            "page:23",
        ),
        "hidden_en": _upsert_chunk(
            app_module,
            hidden_source,
            "demo-review-chunk-hidden-en",
            "Hidden-course evidence should not be visible to demo students without membership.",
            "en",
            1,
            "page:3",
        ),
        "hidden_zh": _upsert_chunk(
            app_module,
            hidden_source,
            "demo-review-chunk-hidden-zh",
            "隐藏课程证据不应展示给没有课程成员关系的学生。",
            "zh",
            2,
            "page:4",
        ),
    }
    app_module.db.session.flush()
    return {"sources": {"en": en_source, "zh": zh_source, "hidden": hidden_source}, "chunks": chunks}


def _evidence_from_chunk(chunk: Any, source: Any, snippet: str | None = None) -> dict[str, Any]:
    text = snippet or getattr(chunk, "content", "")
    return {
        "chunk_uid": chunk.chunk_uid,
        "source_uid": source.source_uid,
        "source_title": source.title,
        "course": chunk.course,
        "chapter": chunk.chapter,
        "language": chunk.language,
        "source_role": source.source_role,
        "source_type": source.source_type,
        "trust_level": chunk.trust_level,
        "quality_status": chunk.quality_status,
        "quality_flags": _loads(chunk.quality_flags, []),
        "source_locator": chunk.source_locator,
        "snippet": text[:300],
        "score": 0.86,
        "retrieval_reason": "demo_seed_governed_chunk",
        "risk_labels": _loads(chunk.quality_flags, []),
        "parse_uid": chunk.parse_uid,
        "parse_block_uid": chunk.parse_block_uid,
    }


def _upsert_card(app_module: Any, payload: dict[str, Any]) -> Any:
    json_fields = {
        "english_evidence",
        "chinese_evidence",
        "risk_labels",
        "parse_quality_flags",
        "input_risk_labels",
    }
    normalized_payload = {
        key: (_dumps(value) if key in json_fields and isinstance(value, (list, dict)) else value)
        for key, value in payload.items()
    }
    card = app_module.ConceptAlignmentCard.query.filter_by(
        english_term=normalized_payload["english_term"],
        course=normalized_payload["course"],
        chapter=normalized_payload.get("chapter", ""),
    ).first()
    if card is None:
        card = concept_alignment_cards.create_concept_card(
            app_module.db.session,
            app_module.ConceptAlignmentCard,
            normalized_payload,
            now_fn=app_module.current_time_text,
            commit=False,
        )
    else:
        for key, value in normalized_payload.items():
            setattr(card, key, value)
        card.updated_at = _now(app_module)
        app_module.db.session.flush()
    return card


def upsert_demo_cards(app_module: Any, knowledge: dict[str, Any], users: dict[str, Any]) -> dict[str, Any]:
    chunks = knowledge["chunks"]
    sources = knowledge["sources"]
    cards = {
        "fourier": _upsert_card(
            app_module,
            {
                "english_term": "Fourier transform",
                "chinese_term": "傅里叶变换",
                "course": DEMO_COURSE,
                "chapter": DEMO_CHAPTER,
                "concept_scope": "Signal representation in the frequency domain.",
                "english_evidence": [_evidence_from_chunk(chunks["fourier_en"], sources["en"])],
                "chinese_evidence": [{
                    **_evidence_from_chunk(chunks["fourier_zh"], sources["zh"]),
                    "candidate_uid": "demo-candidate-fourier-zh",
                    "candidate_text": "傅里叶变换",
                    "chinese_term": "傅里叶变换",
                    "extraction_rank": 1,
                    "retrieval_rank": 1,
                    "evidence_backed": True,
                    "generated": False,
                }],
                "risk_labels": ["bilingual_alignment_not_verified"],
                "status": "needs_review",
                "confidence_score": None,
                "alignment_reason": "Pending bilingual alignment verification.",
                "retrieval_version": "lexical-v1",
                "model_name": "",
                "prompt_version": "",
                "created_by": users["teacher"].id,
            },
        ),
        "transfer": _upsert_card(
            app_module,
            {
                "english_term": "Transfer function",
                "chinese_term": "传递函数",
                "course": DEMO_COURSE,
                "chapter": DEMO_CHAPTER,
                "concept_scope": "System input-output representation.",
                "english_evidence": [_evidence_from_chunk(chunks["transfer_en"], sources["en"])],
                "chinese_evidence": [],
                "risk_labels": ["no_chinese_evidence"],
                "status": "needs_review",
                "confidence_score": None,
                "alignment_reason": "Pending bilingual alignment verification.",
                "retrieval_version": "lexical-v1",
                "model_name": "",
                "prompt_version": "",
                "created_by": users["teacher"].id,
            },
        ),
        "convergence": _upsert_card(
            app_module,
            {
                "english_term": "Convergence",
                "chinese_term": "收敛",
                "course": DEMO_COURSE,
                "chapter": DEMO_CHAPTER,
                "concept_scope": "Limit behavior for sequences, series, or system response.",
                "english_evidence": [_evidence_from_chunk(chunks["convergence_en"], sources["en"])],
                "chinese_evidence": [_evidence_from_chunk(chunks["convergence_zh"], sources["zh"])],
                "risk_labels": ["input_partial_text", "candidate_not_alignment_verified"],
                "parse_quality_status": "partial_text",
                "parse_quality_flags": ["input_partial_text"],
                "input_risk_labels": ["input_partial_text"],
                "status": "needs_review",
                "confidence_score": None,
                "alignment_reason": "Pending bilingual alignment verification.",
                "retrieval_version": "lexical-v1",
                "model_name": "",
                "prompt_version": "",
                "created_by": users["teacher"].id,
            },
        ),
        "impulse": _upsert_card(
            app_module,
            {
                "english_term": "Impulse response",
                "chinese_term": "冲激响应",
                "course": DEMO_COURSE,
                "chapter": DEMO_CHAPTER,
                "concept_scope": "System response to a unit impulse.",
                "english_evidence": [_evidence_from_chunk(chunks["impulse_en"], sources["en"])],
                "chinese_evidence": [_evidence_from_chunk(chunks["impulse_zh"], sources["zh"])],
                "risk_labels": [],
                "status": "approved",
                "confidence_score": None,
                "alignment_reason": "Teacher reviewed demo card.",
                "retrieval_version": "lexical-v1",
                "model_name": "",
                "prompt_version": "",
                "created_by": users["teacher"].id,
                "reviewed_by": users["admin"].id,
                "reviewed_at": _now(app_module),
            },
        ),
        "frequency_response": _upsert_card(
            app_module,
            {
                "english_term": "Frequency response",
                "chinese_term": "频率响应",
                "course": DEMO_COURSE,
                "chapter": DEMO_CHAPTER,
                "concept_scope": "System behavior as a function of frequency.",
                "english_evidence": [_evidence_from_chunk(chunks["fourier_en"], sources["en"])],
                "chinese_evidence": [_evidence_from_chunk(chunks["fourier_zh"], sources["zh"])],
                "risk_labels": [],
                "status": "approved",
                "confidence_score": None,
                "alignment_reason": "Teacher reviewed demo card.",
                "retrieval_version": "lexical-v1",
                "model_name": "",
                "prompt_version": "",
                "created_by": users["teacher"].id,
                "reviewed_by": users["admin"].id,
                "reviewed_at": _now(app_module),
            },
        ),
        "step_response": _upsert_card(
            app_module,
            {
                "english_term": "Step response",
                "chinese_term": "阶跃响应",
                "course": DEMO_COURSE,
                "chapter": "Time Domain",
                "concept_scope": "System output produced by a unit step input.",
                "english_evidence": [_evidence_from_chunk(chunks["impulse_en"], sources["en"])],
                "chinese_evidence": [_evidence_from_chunk(chunks["impulse_zh"], sources["zh"])],
                "risk_labels": [],
                "status": "approved",
                "confidence_score": None,
                "alignment_reason": "Teacher reviewed demo card.",
                "retrieval_version": "lexical-v1",
                "model_name": "",
                "prompt_version": "",
                "created_by": users["teacher"].id,
                "reviewed_by": users["admin"].id,
                "reviewed_at": _now(app_module),
            },
        ),
        "rejected": _upsert_card(
            app_module,
            {
                "english_term": "Ambiguous response",
                "chinese_term": "响应",
                "course": DEMO_COURSE,
                "chapter": DEMO_CHAPTER,
                "concept_scope": "Rejected demo card for reopen workflow.",
                "english_evidence": [_evidence_from_chunk(chunks["impulse_en"], sources["en"])],
                "chinese_evidence": [_evidence_from_chunk(chunks["impulse_zh"], sources["zh"])],
                "risk_labels": ["course_context_mismatch"],
                "status": "rejected",
                "confidence_score": None,
                "alignment_reason": "Pending bilingual alignment verification.",
                "retrieval_version": "lexical-v1",
                "model_name": "",
                "prompt_version": "",
                "created_by": users["teacher"].id,
            },
        ),
        "hidden_approved": _upsert_card(
            app_module,
            {
                "english_term": "Hidden course concept",
                "chinese_term": "隐藏课程概念",
                "course": DEMO_HIDDEN_COURSE,
                "chapter": DEMO_CHAPTER,
                "concept_scope": "Approved card that demo student must not see.",
                "english_evidence": [_evidence_from_chunk(chunks["hidden_en"], sources["hidden"])],
                "chinese_evidence": [_evidence_from_chunk(chunks["hidden_zh"], sources["hidden"])],
                "risk_labels": [],
                "status": "approved",
                "confidence_score": None,
                "alignment_reason": "Teacher reviewed hidden demo card.",
                "retrieval_version": "lexical-v1",
                "model_name": "",
                "prompt_version": "",
                "created_by": users["teacher"].id,
                "reviewed_by": users["admin"].id,
                "reviewed_at": _now(app_module),
            },
        ),
    }
    app_module.db.session.flush()
    for card in cards.values():
        card.updated_at = _now(app_module)
    return cards


def _ensure_review_record(app_module: Any, card: Any, action: str, reviewer: Any, data: dict[str, Any], previous: str, new: str) -> Any:
    existing = app_module.ConceptCardReviewRecord.query.filter_by(
        card_uid=card.card_uid,
        action=action,
        reviewer_name=DEMO_CREATED_BY,
        reason_code=data.get("reason_code", ""),
    ).first()
    if existing is not None:
        return existing
    context = {
        "reviewer_id": getattr(reviewer, "id", None),
        "reviewer_role": getattr(reviewer, "role", ""),
        "reviewer_name": DEMO_CREATED_BY,
    }
    return concept_card_review.create_review_record(
        app_module.db.session,
        app_module.ConceptCardReviewRecord,
        card,
        action,
        context,
        data,
        previous_status=previous,
        new_status=new,
        now_fn=app_module.current_time_text,
        commit=False,
    )


def upsert_demo_history(app_module: Any, cards: dict[str, Any], users: dict[str, Any]) -> None:
    _ensure_review_record(
        app_module,
        cards["fourier"],
        "add_review_note",
        users["teacher"],
        {
            "reason_code": "alignment_not_verified",
            "review_comment": "Demo note: evidence is present, but teacher verification is still required.",
            "request_id": "demo-seed-review-note",
        },
        "needs_review",
        "needs_review",
    )
    _ensure_review_record(
        app_module,
        cards["rejected"],
        "reject",
        users["teacher"],
        {
            "reason_code": "course_context_mismatch",
            "review_comment": "Demo rejected card for reopen workflow.",
            "request_id": "demo-seed-rejected-history",
        },
        "needs_review",
        "rejected",
    )
    _ensure_review_record(
        app_module,
        cards["impulse"],
        "approve",
        users["admin"],
        {
            "reason_code": "teacher_verified",
            "review_comment": "Demo approved card for the student Concept Card learning view.",
            "request_id": "demo-seed-student-approved",
        },
        "needs_review",
        "approved",
    )
    for key, request_id in [
        ("frequency_response", "demo-seed-frequency-approved"),
        ("step_response", "demo-seed-step-approved"),
    ]:
        _ensure_review_record(
            app_module,
            cards[key],
            "approve",
            users["admin"],
            {
                "reason_code": "teacher_verified",
                "review_comment": "Demo approved card for teacher learning analytics.",
                "request_id": request_id,
            },
            "needs_review",
            "approved",
        )
    _ensure_review_record(
        app_module,
        cards["hidden_approved"],
        "approve",
        users["admin"],
        {
            "reason_code": "teacher_verified",
            "review_comment": "Demo hidden approved card used to verify course visibility filtering.",
            "request_id": "demo-seed-hidden-approved",
        },
        "needs_review",
        "approved",
    )
    assignment = app_module.ConceptCardReviewAssignment.query.filter_by(
        card_uid=cards["fourier"].card_uid,
        assigned_to=DEMO_USERS["teacher"]["username"],
        assignment_status="active",
    ).first()
    if assignment is None:
        assignment = app_module.ConceptCardReviewAssignment(
            card_uid=cards["fourier"].card_uid,
            assigned_to=DEMO_USERS["teacher"]["username"],
            assigned_by=users["admin"].id,
            assignment_status="active",
            created_at=_now(app_module),
            updated_at=_now(app_module),
        )
        app_module.db.session.add(assignment)


def upsert_demo_alignment_run(app_module: Any, card: Any) -> Any:
    run = app_module.AlignmentVerificationRun.query.filter_by(
        card_uid=card.card_uid,
        provider_name="mock-rule-v1",
        provider_response_status="demo_seed",
    ).first()
    output = {
        "provider_name": "mock-rule-v1",
        "provider_type": "mock",
        "alignment_decision": "uncertain",
        "alignment_confidence": 0.62,
        "recommendation": "needs_review",
        "risk_labels": ["bilingual_alignment_not_verified"],
        "is_production_result": False,
        "can_auto_approve": False,
        "explanation": "Demo mock verification only; not a production alignment decision.",
    }
    if run is None:
        run = app_module.AlignmentVerificationRun(
            card_uid=card.card_uid,
            english_term=card.english_term,
            chinese_term=card.chinese_term,
            course=card.course,
            chapter=card.chapter,
            provider_name="mock-rule-v1",
            provider_type="mock",
            provider_version="v1",
            verification_status="mock_only",
            recommendation="needs_review",
            alignment_confidence=0.62,
            provider_response_status="demo_seed",
            created_at=_now(app_module),
        )
        app_module.db.session.add(run)
    run.input_payload = _dumps({
        "card_uid": card.card_uid,
        "english_term": card.english_term,
        "chinese_term": card.chinese_term,
        "course": card.course,
        "chapter": card.chapter,
        "english_evidence_count": 1,
        "chinese_evidence_count": 1,
    })
    run.output_payload = _dumps(output)
    run.english_evidence_count = 1
    run.chinese_evidence_count = 1
    run.top_english_chunk_uids = _dumps(["demo-review-chunk-fourier-en"])
    run.top_chinese_chunk_uids = _dumps(["demo-review-chunk-fourier-zh"])
    run.risk_labels = _dumps(["bilingual_alignment_not_verified"])
    run.retrieval_score_summary = _dumps({"top_score": 0.86})
    run.candidate_score_summary = _dumps({})
    run.prompt_version = ""
    run.parser_version = ""
    run.output_schema_version = ""
    return run


def upsert_demo_student_learning(app_module: Any, cards: dict[str, Any], users: dict[str, Any]) -> dict[str, Any]:
    """Create stable student state and feedback for the demo learning loop."""
    now = _now(app_module)
    student = users["student"]
    student_two = users["student2"]

    def upsert_state(uid: str, user: Any, card_key: str, *, favorited: bool, mastered: bool, view_count: int, note: str = "") -> Any:
        card = cards[card_key]
        state = app_module.StudentConceptCardState.query.filter_by(
            user_id=user.id,
            card_uid=card.card_uid,
        ).first()
        if state is None:
            state = app_module.StudentConceptCardState(
                state_uid=uid,
                user_id=user.id,
                card_uid=card.card_uid,
                course=card.course,
                created_at=now,
            )
            app_module.db.session.add(state)
        state.course = card.course
        state.favorited = favorited
        state.mastered = mastered
        state.mastered_at = now if mastered else ""
        state.last_viewed_at = now if view_count > 0 else ""
        state.view_count = max(int(state.view_count or 0), view_count)
        state.personal_note = note
        state.updated_at = now
        return state

    def upsert_feedback(
        uid: str,
        user: Any,
        card_key: str,
        *,
        feedback_type: str,
        message: str,
        status: str = "submitted",
        teacher_note: str = "",
    ) -> Any:
        card = cards[card_key]
        feedback = app_module.Feedback.query.filter_by(feedback_uid=uid).first()
        if feedback is None:
            feedback = app_module.Feedback(
                feedback_uid=uid,
                term_id=0,
                user_id=user.id,
                created_at=now,
            )
            app_module.db.session.add(feedback)
        feedback.user_id = user.id
        feedback.user_role = "student"
        feedback.course = card.course
        feedback.chapter = card.chapter
        feedback.card_uid = card.card_uid
        feedback.english_term = card.english_term
        feedback.chinese_term = card.chinese_term
        feedback.feedback_type = feedback_type
        feedback.feedback_source = "student_concept_card"
        feedback.severity = "normal"
        feedback.priority = "P2"
        feedback.message = message
        feedback.feedback_content = message
        feedback.reported_issue = message
        feedback.expected_result = ""
        feedback.actual_result = card.card_uid
        feedback.evidence_comment = _dumps({
            "card_uid": card.card_uid,
            "original_feedback_type": feedback_type,
        })
        feedback.classification = "teacher_review_needed"
        feedback.root_cause = "unknown"
        feedback.status = status
        feedback.linked_card_uid = card.card_uid
        feedback.teacher_note = teacher_note
        if status in {"resolved", "closed"}:
            feedback.handled_by = users["admin"].id
            feedback.handler_role = "admin"
            feedback.handled_at = feedback.handled_at or now
            feedback.resolved_by = users["admin"].id
            feedback.resolved_at = feedback.resolved_at or now
            feedback.resolution_action = "demo_resolved"
            feedback.resolution_note = teacher_note or "Demo resolved feedback for analytics."
        feedback.updated_at = now
        return feedback

    states = [
        upsert_state(
            "demo-student-state-impulse",
            student,
            "impulse",
            favorited=True,
            mastered=True,
            view_count=2,
            note="Demo note: review impulse response examples before quiz.",
        ),
        upsert_state(
            "demo-student2-state-impulse",
            student_two,
            "impulse",
            favorited=False,
            mastered=True,
            view_count=1,
            note="",
        ),
        upsert_state(
            "demo-student-state-frequency",
            student,
            "frequency_response",
            favorited=True,
            mastered=False,
            view_count=1,
            note="Need a clearer example for frequency response.",
        ),
        upsert_state(
            "demo-student2-state-frequency",
            student_two,
            "frequency_response",
            favorited=True,
            mastered=False,
            view_count=1,
            note="",
        ),
    ]
    feedbacks = [
        upsert_feedback(
            "demo-student-feedback-impulse",
            student,
            "impulse",
            feedback_type="concept_explanation_error",
            message="The Chinese explanation is too brief for revision.",
            status="submitted",
        ),
        upsert_feedback(
            "demo-student-feedback-frequency-1",
            student,
            "frequency_response",
            feedback_type="explanation_unclear",
            message="The frequency response card needs a clearer relationship to Fourier transform.",
            status="submitted",
        ),
        upsert_feedback(
            "demo-student-feedback-frequency-2",
            student_two,
            "frequency_response",
            feedback_type="evidence_issue",
            message="Please add a source that shows frequency response magnitude and phase.",
            status="submitted",
        ),
        upsert_feedback(
            "demo-student-feedback-step-resolved",
            student,
            "step_response",
            feedback_type="duplicate",
            message="This looked similar to impulse response at first.",
            status="resolved",
            teacher_note="Teacher clarified that step response is distinct from impulse response.",
        ),
    ]
    return {"state": states[0], "states": states, "feedback": feedbacks[0], "feedbacks": feedbacks}


def seed_review_demo(app_module: Any, *, reset_demo: bool = False) -> dict[str, Any]:
    with app_module.app.app_context():
        app_module.db.create_all()
        if hasattr(app_module, "ensure_schema_columns"):
            app_module.ensure_schema_columns()
        if reset_demo:
            reset_review_demo_data(app_module)

        users = {role: upsert_demo_user(app_module, role) for role in DEMO_USERS}
        app_module.db.session.flush()
        course = upsert_demo_course(app_module, users["teacher"])
        hidden_course = upsert_demo_course(app_module, users["teacher"], course_name=DEMO_HIDDEN_COURSE, course_code="DEMO-HIDDEN")
        upsert_course_member(app_module, course, users["teacher"], "teacher")
        upsert_course_member(app_module, course, users["reviewer"], "reviewer")
        upsert_course_member(app_module, course, users["admin"], "teacher")
        upsert_course_member(app_module, course, users["student"], "student")
        upsert_course_member(app_module, course, users["student2"], "student")
        upsert_course_member(app_module, hidden_course, users["teacher"], "teacher")
        upsert_course_member(app_module, hidden_course, users["admin"], "teacher")
        policy, teacher_permission, reviewer_permission, admin_permission = upsert_review_policy_and_permissions(app_module, users)
        visible_policy, hidden_policy, student_membership, student2_membership = upsert_student_visibility_demo(app_module, users)
        knowledge = upsert_demo_knowledge(app_module)
        cards = upsert_demo_cards(app_module, knowledge, users)
        upsert_demo_history(app_module, cards, users)
        run = upsert_demo_alignment_run(app_module, cards["fourier"])
        learning = upsert_demo_student_learning(app_module, cards, users)
        app_module.db.session.commit()

        return {
            "course": DEMO_COURSE,
            "chapter": DEMO_CHAPTER,
            "users": {
                role: {
                    "email": data["email"],
                    "password": DEMO_PASSWORDS[role],
                    "role": data.get("role", role),
                }
                for role, data in DEMO_USERS.items()
            },
            "policy_uid": policy.policy_uid,
            "student_visibility_policy_uid": visible_policy.policy_uid,
            "hidden_visibility_policy_uid": hidden_policy.policy_uid,
            "student_membership_uid": student_membership.membership_uid,
            "student2_membership_uid": student2_membership.membership_uid,
            "teacher_permission_uid": teacher_permission.permission_uid,
            "reviewer_permission_uid": reviewer_permission.permission_uid,
            "admin_permission_uid": admin_permission.permission_uid,
            "card_uids": {key: card.card_uid for key, card in cards.items()},
            "source_uids": {key: source.source_uid for key, source in knowledge["sources"].items()},
            "alignment_run_uid": run.run_uid,
            "student_state_uid": learning["state"].state_uid,
            "student_state_uids": [state.state_uid for state in learning["states"]],
            "student_feedback_uid": learning["feedback"].feedback_uid,
            "student_feedback_uids": [feedback.feedback_uid for feedback in learning["feedbacks"]],
        }


def load_default_app_module() -> Any:
    import app as app_module

    return app_module


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed LexiBridge Concept Card review demo data.")
    parser.add_argument("--reset-demo", action="store_true", help="Delete existing demo namespace data before seeding.")
    args = parser.parse_args()

    app_module = load_default_app_module()
    summary = seed_review_demo(app_module, reset_demo=args.reset_demo)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
