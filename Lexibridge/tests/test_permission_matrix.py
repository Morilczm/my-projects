import importlib.util
import uuid
from pathlib import Path

from test_concept_card_review import with_expected_version


ROOT = Path(__file__).resolve().parents[1]
SEED_SCRIPT = ROOT / "scripts" / "seed_review_demo.py"


def load_seed_module():
    spec = importlib.util.spec_from_file_location("seed_review_demo_module_permissions", SEED_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def login(client, email, password):
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()["token"]


def create_unprivileged_teacher(app_module, suffix: str):
    email = f"pilot-no-permission-{suffix}@lexibridge.local"
    with app_module.app.app_context():
        user = app_module.User.query.filter_by(email=email).first()
        if user is None:
            user = app_module.User(
                username=f"pilot_no_permission_{suffix}",
                email=email,
                password_hash=app_module.generate_password_hash("Teacher1234", method="pbkdf2:sha256"),
                role="teacher",
                is_verified=True,
                created_at=app_module.current_time_text(),
            )
            app_module.db.session.add(user)
            app_module.db.session.commit()
    return email


def assert_stable_error(response, expected_statuses):
    assert response.status_code in expected_statuses, response.get_data(as_text=True)
    payload = response.get_json()
    assert payload["status"] == "error"
    assert payload["request_id"]
    assert payload["error_code"]


def test_student_permission_boundaries(client, app_module):
    seed = load_seed_module()
    summary = seed.seed_review_demo(app_module, reset_demo=True)
    student = summary["users"]["student"]
    token = login(client, student["email"], student["password"])
    impulse_uid = summary["card_uids"]["impulse"]
    hidden_uid = summary["card_uids"]["hidden_approved"]
    feedback_uid = summary["student_feedback_uid"]

    visible = client.get(
        f"/api/student/concept-cards?course={seed.DEMO_COURSE.replace(' ', '%20')}",
        headers={**bearer(token), "X-Request-ID": "matrix-student-visible"},
    )
    assert visible.status_code == 200, visible.get_data(as_text=True)
    assert all(item["status"] == "approved" for item in visible.get_json()["data"]["items"])

    state = client.post(
        f"/api/student/concept-cards/{impulse_uid}/state",
        json={"favorited": True, "mastered": True, "personal_note": "matrix note"},
        headers={**bearer(token), "X-Request-ID": "matrix-student-state"},
    )
    feedback = client.post(
        f"/api/student/concept-cards/{impulse_uid}/feedback",
        json={"feedback_type": "other", "message": "Matrix feedback."},
        headers={**bearer(token), "X-Request-ID": "matrix-student-feedback"},
    )
    assert state.status_code == 200, state.get_data(as_text=True)
    assert feedback.status_code == 200, feedback.get_data(as_text=True)

    for response in [
        client.post(
            f"/api/concept-cards/{impulse_uid}/review",
            json={"action": "approve", "reason_code": "teacher_verified"},
            headers={**bearer(token), "X-Request-ID": "matrix-student-review"},
        ),
        client.post(
            f"/api/concept-cards/student-feedback/{feedback_uid}/triage",
            json={"action": "acknowledge", "teacher_note": "student should not triage"},
            headers={**bearer(token), "X-Request-ID": "matrix-student-triage"},
        ),
        client.get(
            "/api/teacher/learning-analytics",
            headers={**bearer(token), "X-Request-ID": "matrix-student-analytics"},
        ),
        client.get(
            "/api/alignment/providers",
            headers={**bearer(token), "X-Request-ID": "matrix-student-provider-policy"},
        ),
        client.get(
            "/api/review-policies",
            headers={**bearer(token), "X-Request-ID": "matrix-student-course-policy"},
        ),
    ]:
        assert_stable_error(response, {403})

    hidden_state = client.post(
        f"/api/student/concept-cards/{hidden_uid}/state",
        json={"favorited": True},
        headers={**bearer(token), "X-Request-ID": "matrix-hidden-state"},
    )
    assert_stable_error(hidden_state, {403, 404})


def test_teacher_permission_boundaries(client, app_module):
    seed = load_seed_module()
    summary = seed.seed_review_demo(app_module, reset_demo=True)
    teacher = summary["users"]["teacher"]
    token = login(client, teacher["email"], teacher["password"])
    suffix = uuid.uuid4().hex[:8]
    no_perm_email = create_unprivileged_teacher(app_module, suffix)
    no_perm_token = login(client, no_perm_email, "Teacher1234")

    authorized_queue = client.get(
        f"/api/concept-cards/review-queue?course={seed.DEMO_COURSE.replace(' ', '%20')}",
        headers={**bearer(token), "X-Request-ID": "matrix-teacher-queue"},
    )
    assert authorized_queue.status_code == 200, authorized_queue.get_data(as_text=True)
    assert authorized_queue.get_json()["data"]["items"]

    unauthorized_queue = client.get(
        f"/api/concept-cards/review-queue?course={seed.DEMO_COURSE.replace(' ', '%20')}",
        headers={**bearer(no_perm_token), "X-Request-ID": "matrix-teacher-no-perm-queue"},
    )
    assert unauthorized_queue.status_code == 200, unauthorized_queue.get_data(as_text=True)
    assert unauthorized_queue.get_json()["data"]["items"] == []

    hidden_analytics = client.get(
        f"/api/teacher/learning-analytics?course={seed.DEMO_HIDDEN_COURSE.replace(' ', '%20')}",
        headers={**bearer(token), "X-Request-ID": "matrix-teacher-hidden-analytics"},
    )
    assert hidden_analytics.status_code in {200, 403}, hidden_analytics.get_data(as_text=True)
    if hidden_analytics.status_code == 200:
        assert hidden_analytics.get_json()["data"]["course_summary"]["approved_card_count"] == 0

    provider_policy_write = client.post(
        f"/api/alignment/providers/matrix-provider-{suffix}/policy",
        json={"provider_type": "replay_llm", "enabled": True},
        headers={**bearer(token), "X-Request-ID": "matrix-teacher-provider-write"},
    )
    assert_stable_error(provider_policy_write, {403})

    transfer_uid = summary["card_uids"]["transfer"]
    blocked_override = client.post(
        f"/api/concept-cards/{transfer_uid}/review",
        json=with_expected_version(app_module, transfer_uid, {
            "action": "approve",
            "reason_code": "teacher_verified",
            "review_comment": "Teacher cannot override policy-blocked missing evidence.",
            "allow_risk_override": True,
            "override_reason": "Matrix override attempt.",
        }),
        headers={**bearer(token), "X-Request-ID": "matrix-teacher-override-block"},
    )
    assert blocked_override.status_code == 400
    assert blocked_override.get_json()["request_id"] == "matrix-teacher-override-block"


def test_admin_permission_boundaries_and_hard_safety_gates(client, app_module):
    seed = load_seed_module()
    summary = seed.seed_review_demo(app_module, reset_demo=True)
    admin = summary["users"]["admin"]
    token = login(client, admin["email"], admin["password"])
    suffix = uuid.uuid4().hex[:8]
    course = f"Pilot Matrix {suffix}"

    policy = client.post(
        "/api/review-policies",
        json={"course": course, "status": "active", "required_evidence_sides": "both"},
        headers={**bearer(token), "X-Request-ID": "matrix-admin-policy"},
    )
    assert policy.status_code == 200, policy.get_data(as_text=True)
    assert policy.get_json()["request_id"] == "matrix-admin-policy"

    with app_module.app.app_context():
        teacher = app_module.User.query.filter_by(email=summary["users"]["teacher"]["email"]).first()
        teacher_id = teacher.id
    permission = client.post(
        "/api/review-permissions",
        json={
            "course": course,
            "reviewer_id": teacher_id,
            "reviewer_role": "teacher",
            "permission_level": "approve",
            "can_review": True,
            "can_approve": True,
        },
        headers={**bearer(token), "X-Request-ID": "matrix-admin-permission"},
    )
    assert permission.status_code == 200, permission.get_data(as_text=True)

    hidden_analytics = client.get(
        f"/api/teacher/learning-analytics?course={seed.DEMO_HIDDEN_COURSE.replace(' ', '%20')}",
        headers={**bearer(token), "X-Request-ID": "matrix-admin-hidden-analytics"},
    )
    assert hidden_analytics.status_code == 200, hidden_analytics.get_data(as_text=True)
    assert hidden_analytics.get_json()["data"]["course_summary"]["approved_card_count"] >= 1

    provider = f"matrix-replay-{suffix}"
    unsafe_policy = client.post(
        f"/api/alignment/providers/{provider}/policy",
        json={
            "provider_type": "replay_llm",
            "enabled": True,
            "status": "active",
            "replay_only": True,
            "allow_auto_approve": True,
            "allow_attach_to_card": True,
            "allowed_roles": ["teacher", "admin"],
        },
        headers={**bearer(token), "X-Request-ID": "matrix-admin-provider"},
    )
    assert unsafe_policy.status_code == 200, unsafe_policy.get_data(as_text=True)
    assert unsafe_policy.get_json()["data"]["policy"]["allow_auto_approve"] is False
    assert unsafe_policy.get_json()["data"]["policy"]["require_human_review"] is True

    verify_disabled = client.post(
        "/api/alignment/verify",
        json={
            "provider": "deepseek-alignment-v1-disabled",
            "english_term": "Fourier transform",
            "chinese_term": "傅里叶变换",
            "course": seed.DEMO_COURSE,
            "english_evidence": [{"snippet": "Fourier transform maps time to frequency."}],
            "chinese_evidence": [{"snippet": "傅里叶变换将信号表示到频域。"}],
        },
        headers={**bearer(token), "X-Request-ID": "matrix-admin-provider-disabled"},
    )
    assert verify_disabled.status_code == 200, verify_disabled.get_data(as_text=True)
    data = verify_disabled.get_json()["data"]
    assert data["can_auto_approve"] is False
    assert data["verification_status"] == "failed"


def test_unauthenticated_write_operations_return_stable_json(client):
    response = client.post(
        "/api/concept-cards/missing-card/review",
        json={"action": "approve", "reason_code": "teacher_verified"},
        headers={"X-Request-ID": "matrix-anonymous-review"},
    )
    assert_stable_error(response, {401, 403})
