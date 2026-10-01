import hashlib
import json
import uuid


PREFIX = "query-9c5e"


def uid(label):
    return f"{PREFIX}-{label}-{uuid.uuid4().hex[:10]}"


def cleanup(app_module):
    app_module.db.session.rollback()
    run_ids = [
        row.id
        for row in app_module.DocumentAlignmentWorkflowRun.query.filter(
            app_module.DocumentAlignmentWorkflowRun.run_uid.like(f"{PREFIX}%")
        ).all()
    ]
    if run_ids:
        app_module.DocumentAlignmentWorkflowItem.query.filter(
            app_module.DocumentAlignmentWorkflowItem.workflow_run_id.in_(run_ids)
        ).delete(synchronize_session=False)
    app_module.DocumentAlignmentWorkflowRun.query.filter(
        app_module.DocumentAlignmentWorkflowRun.run_uid.like(f"{PREFIX}%")
    ).delete(synchronize_session=False)
    app_module.KnowledgeSource.query.filter(
        app_module.KnowledgeSource.source_uid.like(f"{PREFIX}%")
    ).delete(synchronize_session=False)

    users = app_module.User.query.filter(app_module.User.username.like(f"{PREFIX}%")).all()
    user_ids = [user.id for user in users]
    courses = app_module.Course.query.filter(app_module.Course.course_code.like("Q9C5E-%")).all()
    course_ids = [course.id for course in courses]
    if user_ids:
        app_module.CourseMember.query.filter(
            app_module.CourseMember.user_id.in_(user_ids)
        ).delete(synchronize_session=False)
    if course_ids:
        app_module.CourseMember.query.filter(
            app_module.CourseMember.course_id.in_(course_ids)
        ).delete(synchronize_session=False)
    for course in courses:
        app_module.db.session.delete(course)
    for user in users:
        app_module.db.session.delete(user)
    app_module.db.session.commit()
    app_module.db.session.expire_all()


def create_scenario(
    app_module,
    *,
    item_count=3,
    run_status="processing",
    run_stage="verification",
    ready=1,
    blocked=0,
    failed=0,
    visibility="course",
    source_filename="teacher-notes.pdf",
):
    suffix = uuid.uuid4().hex[:8]
    requester = app_module.User(
        username=f"{PREFIX}-requester-{suffix}",
        email=f"{PREFIX}-requester-{suffix}@lexibridge.local",
        password_hash="test-only",
        role="teacher",
        is_verified=True,
        created_at=app_module.current_time_text(),
    )
    course_teacher = app_module.User(
        username=f"{PREFIX}-course-teacher-{suffix}",
        email=f"{PREFIX}-course-teacher-{suffix}@lexibridge.local",
        password_hash="test-only",
        role="teacher",
        is_verified=True,
        created_at=app_module.current_time_text(),
    )
    unrelated_teacher = app_module.User(
        username=f"{PREFIX}-unrelated-{suffix}",
        email=f"{PREFIX}-unrelated-{suffix}@lexibridge.local",
        password_hash="test-only",
        role="teacher",
        is_verified=True,
        created_at=app_module.current_time_text(),
    )
    app_module.db.session.add_all([requester, course_teacher, unrelated_teacher])
    app_module.db.session.flush()

    course = app_module.Course(
        name=f"Query Course {suffix}",
        course_code=f"Q9C5E-{suffix}",
        teacher_id=course_teacher.id,
        created_at=app_module.current_time_text(),
    )
    app_module.db.session.add(course)
    app_module.db.session.flush()
    app_module.db.session.add(
        app_module.CourseMember(
            course_id=course.id,
            user_id=course_teacher.id,
            role="teacher",
            role_in_course="teacher",
            status="active",
            created_at=app_module.current_time_text(),
            joined_at=app_module.current_time_text(),
        )
    )

    source_uid = uid("source")
    source = app_module.KnowledgeSource(
        source_uid=source_uid,
        title="Governed query source",
        name="Governed query source",
        source_title="Governed query source",
        source_filename=source_filename,
        course=course.name,
        course_id=course.id,
        owner_user_id=requester.id,
        visibility=visibility,
        trust_level="teacher_verified",
        status="active",
        parse_uid=uid("parse"),
        version=1,
    )
    app_module.db.session.add(source)
    app_module.db.session.flush()

    run_uid = uid("run")
    run = app_module.DocumentAlignmentWorkflowRun(
        run_uid=run_uid,
        source_uid=source_uid,
        parse_uid=source.parse_uid,
        source_version="1",
        course=course.name,
        chapter="Frequency Domain",
        requested_by=str(requester.id),
        request_id=uid("request"),
        idempotency_key=uid("idem"),
        idempotency_fingerprint=hashlib.sha256(run_uid.encode()).hexdigest(),
        workflow_version="formal-document-alignment-v1",
        status=run_status,
        stage=run_stage,
        total_items=item_count,
        ready_for_review_items=ready,
        blocked_items=blocked,
        failed_items=failed,
        warning_count=blocked + failed,
        created_at=app_module.current_time_text(),
    )
    app_module.db.session.add(run)
    app_module.db.session.flush()

    statuses = ["needs_review", "blocked", "failed", "evidence_ready"]
    for index in range(item_count):
        status = statuses[index % len(statuses)]
        stage = "terminal" if status in {"needs_review", "blocked", "failed"} else "evidence_retrieval"
        app_module.db.session.add(
            app_module.DocumentAlignmentWorkflowItem(
                item_uid=uid(f"item-{index:03d}"),
                workflow_run_id=run.id,
                item_key=f"item-key-v1:{index:064x}",
                candidate_term=f"Term {index:03d}",
                normalized_term=f"term {index:03d}",
                source_chunk_refs=json.dumps([uid(f"chunk-{index}-a"), uid(f"chunk-{index}-b")]),
                risk_labels=json.dumps(["evidence_gap", "translation_risk", "evidence_gap"]),
                confidence_score=0.8 if status == "needs_review" else None,
                confidence_summary=json.dumps({"score": 0.8}) if status == "needs_review" else "{}",
                recommendation="review" if status == "needs_review" else "",
                draft_card_uid=uid("card") if status in {"needs_review", "failed"} else "",
                verification_run_uid=uid("verification") if status == "needs_review" else "",
                status=status,
                stage=stage,
                error_code="DOCUMENT_ALIGNMENT_TEST_ERROR" if status in {"blocked", "failed"} else "",
                error_message="Safe processing summary." if status in {"blocked", "failed"} else "",
                retry_count=1 if status == "failed" else 0,
                created_at=app_module.current_time_text(),
            )
        )
    app_module.db.session.commit()
    app_module.db.session.expire_all()
    return {
        "run_uid": run_uid,
        "source_uid": source_uid,
        "requester_id": requester.id,
        "course_teacher_id": course_teacher.id,
        "unrelated_teacher_id": unrelated_teacher.id,
        "course_id": course.id,
        "course": course.name,
    }
