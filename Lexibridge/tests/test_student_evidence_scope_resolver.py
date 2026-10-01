from types import SimpleNamespace

from services import student_concept_queries as queries


def source(uid, *, scope, owner=None, course_id=None, visibility="private", allowed=True):
    return SimpleNamespace(
        source_uid=uid,
        scope_type=scope,
        owner_user_id=owner,
        course_id=course_id,
        visibility=visibility,
        language="zh",
        status="active",
        allow_student_search=allowed,
        authorization_status="authorized",
        license_status="licensed",
    )


def test_personal_scope_excludes_other_students_and_managed_courses():
    sources = [
        source("student-a", scope="personal", owner=1),
        source("student-b", scope="personal", owner=2),
        source("course-a", scope="course", course_id=10, visibility="course"),
        source("platform", scope="global", visibility="global"),
    ]
    result = queries.resolve_evidence_scope(
        sources,
        workspace_scope="PERSONAL",
        student_id=1,
        course_id=None,
        allow_platform_governed=True,
    )
    assert result.allowed_source_uids == ("platform", "student-a")


def test_managed_scope_excludes_other_courses_and_all_student_private_sources():
    sources = [
        source("student-a", scope="personal", owner=1),
        source("course-a", scope="course", course_id=10, visibility="course"),
        source("course-b", scope="course", course_id=11, visibility="course"),
        source("platform", scope="global", visibility="global"),
    ]
    result = queries.resolve_evidence_scope(
        sources,
        workspace_scope="MANAGED_COURSE",
        student_id=1,
        course_id=10,
        allow_platform_governed=False,
    )
    assert result.allowed_source_uids == ("course-a",)


def test_platform_source_requires_explicit_policy():
    result = queries.resolve_evidence_scope(
        [source("platform", scope="global", visibility="global")],
        workspace_scope="PERSONAL",
        student_id=1,
        course_id=None,
        allow_platform_governed=False,
    )
    assert result.allowed_source_uids == ()
