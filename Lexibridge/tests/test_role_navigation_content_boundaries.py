from pathlib import Path
import uuid

from services import student_first_boundaries as boundaries
from services import course_review_policy
from test_teacher_alignment_review_vertical_slice import _case


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
REVIEW_ROUTE = (ROOT / "backend" / "routes" / "concept_card_review.py").read_text(encoding="utf-8")


def test_role_capability_matrix_separates_instructor_and_reviewer():
    instructor = boundaries.role_capabilities("teacher")
    reviewer = boundaries.role_capabilities("reviewer")
    assert "MANAGE_ENGLISH_COURSE_MATERIALS" in instructor
    assert "REVIEW_BILINGUAL_ALIGNMENT_EXCEPTIONS" not in instructor
    assert "REVIEW_BILINGUAL_ALIGNMENT_EXCEPTIONS" in reviewer
    assert "MANAGE_PROVIDER_CONFIGURATION" not in reviewer


def test_instructor_navigation_is_english_and_does_not_include_concept_review():
    instructor_block = FRONTEND.split("teacher: [", 1)[1].split("reviewer: [", 1)[0]
    assert "conceptReview" not in instructor_block
    assert "Teacher Dashboard" in instructor_block
    assert "Courseware Upload" in instructor_block


def test_reviewer_navigation_exposes_reviewer_console():
    reviewer_block = FRONTEND.split("reviewer: [", 1)[1].split("admin: [", 1)[0]
    assert "conceptReview" in reviewer_block
    assert "Reviewer Console" in reviewer_block


def test_review_routes_accept_reviewer_and_retain_teacher_compatibility():
    assert 'REVIEW_ROUTE_ROLES = {"reviewer", "teacher", "admin"}' in REVIEW_ROUTE
    assert "transitional compatibility" in REVIEW_ROUTE


def test_frontend_calls_task_12jb_review_workflow_reused_not_duplicated():
    assert "/api/concept-cards/review-queue" in FRONTEND
    assert "/review-case" in FRONTEND
    assert "/generate-draft" in FRONTEND
    assert "Reviewer Console" in FRONTEND


def test_role_aware_initial_load_does_not_prefetch_reviewer_data_for_instructor():
    load_block = FRONTEND.split("async function loadEverything()", 1)[1].split("const Lexi =", 1)[0]
    assert 'if (role === "reviewer")' in load_block
    assert 'if (role === "teacher")' in load_block
    assert "loadReviewQueue()" not in load_block.split('if (role === "teacher")', 1)[1].split(
        'if (role === "admin")', 1
    )[0]
    assert "loadQC()" not in load_block.split('if (role === "teacher")', 1)[1].split(
        'if (role === "admin")', 1
    )[0]


def test_role_contract_blocks_students_from_reviewer_capabilities():
    assert "REVIEW_BILINGUAL_ALIGNMENT_EXCEPTIONS" not in boundaries.role_capabilities("student")


def test_reviewer_account_reuses_task_12jb_routes_with_course_permission(client, app_module):
    password = "Reviewer1234"
    with app_module.app.app_context():
        reviewer = app_module.User(
            username=f"reviewer_{uuid.uuid4().hex[:10]}",
            email=f"reviewer-{uuid.uuid4().hex}@lexibridge.local",
            password_hash=app_module.generate_password_hash(password, method="pbkdf2:sha256"),
            role="reviewer",
            is_verified=True,
            created_at=app_module.current_time_text(),
        )
        app_module.db.session.add(reviewer)
        app_module.db.session.flush()
        card = _case(app_module)
        course_review_policy.grant_course_review_permission(
            app_module.db.session,
            app_module.CourseReviewPermission,
            card.course,
            reviewer.id,
            {
                "reviewer_id": reviewer.id,
                "reviewer_role": "reviewer",
                "permission_level": "review",
            },
            actor=reviewer,
            now_fn=app_module.current_time_text,
        )
        app_module.db.session.commit()
        email = reviewer.email
        card_uid = card.card_uid
    login = client.post("/api/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200
    token = login.get_json()["token"]
    response = client.get(
        f"/api/concept-cards/{card_uid}/review-case",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["case"]["identity"]["alignment_case_uid"] == card_uid
