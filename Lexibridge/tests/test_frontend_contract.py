import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "index.html"
OPENAPI = ROOT / "docs" / "openapi.yaml"


FRONTEND_API_PATHS = {
    "/api/auth/me",
    "/api/auth/login",
    "/api/auth/logout",
    "/api/auth/register",
    "/api/auth/verify-email",
    "/api/auth/password-reset/request",
    "/api/auth/password-reset/confirm",
    "/api/courses",
    "/api/courses/mine",
    "/api/courses/{course_id}/join",
    "/api/terminology/cards",
    "/api/terminology/cards/{card_id}/favorite",
    "/api/terminology/cards/{card_id}/mastered",
    "/api/terminology/cards/{card_id}/feedback",
    "/api/terminology/cards/export",
    "/api/student/concept-cards",
    "/api/student/concept-cards/{card_uid}",
    "/api/student/concept-cards/{card_uid}/state",
    "/api/student/concept-cards/{card_uid}/feedback",
    "/api/student/concept-cards/export",
    "/api/student/progress",
    "/api/concept-cards/review-queue",
    "/api/concept-cards/{card_uid}",
    "/api/concept-cards/{card_uid}/reviews",
    "/api/concept-cards/{card_uid}/review",
    "/api/concept-cards/{card_uid}/assign-reviewer",
    "/api/concept-cards/student-feedback-queue",
    "/api/concept-cards/student-feedback/{feedback_uid}/triage",
    "/api/teacher/learning-analytics",
    "/api/teacher/learning-analytics/cards",
    "/api/teacher/learning-analytics/export",
    "/api/documents",
    "/api/documents/upload",
    "/api/jobs",
    "/api/jobs/{job_id}/cancel",
    "/api/jobs/{job_id}/retry",
    "/api/alignment/runs",
    "/api/document-alignment-runs",
    "/api/document-alignment-runs/{run_uid}",
    "/api/document-alignment-runs/{run_uid}/items",
    "/api/evaluation/runs",
    "/api/feedback",
    "/api/feedback/{feedback_id}/resolve",
    "/api/subscription/plans",
    "/api/subscription/me",
    "/api/subscription/mock-payment",
    "/api/quality-control",
    "/api/quality-control/{card_id}/approve",
    "/api/quality-control/{card_id}/reject",
    "/api/quality-control/{card_id}/edit",
    "/api/quality-control/{card_id}/needs-more-evidence",
    "/api/knowledge/sources",
    "/api/knowledge/versions",
    "/api/admin/users",
    "/api/admin/users/{user_id}/role",
    "/api/admin/logs",
    "/api/admin/billing",
    "/api/admin/usage",
}


CORE_ERROR_CODES = {
    "AUTH_REQUIRED",
    "TOKEN_EXPIRED",
    "PERMISSION_DENIED",
    "VALIDATION_ERROR",
    "FILE_TOO_LARGE",
    "UNSUPPORTED_FILE_TYPE",
    "OCR_UNAVAILABLE",
    "FORMULA_OCR_UNAVAILABLE",
    "AI_PROVIDER_FAILED",
    "INTERNAL_ERROR",
}


def frontend_text():
    assert FRONTEND.exists()
    return FRONTEND.read_text(encoding="utf-8")


def openapi_paths():
    assert OPENAPI.exists()
    contract = yaml.safe_load(OPENAPI.read_text(encoding="utf-8"))
    return set(contract["paths"])


def extract_inline_script(text):
    matches = re.findall(r"<script>(.*?)</script>", text, flags=re.S)
    assert matches
    return "\n".join(matches)


def find_node_binary():
    bundled = Path.home() / ".cache" / "codex-runtimes" / "codex-primary-runtime" / "dependencies" / "node" / "bin" / "node"
    if bundled.exists():
        return str(bundled)
    return shutil.which("node")


def test_frontend_javascript_syntax(tmp_path):
    node = find_node_binary()
    if not node:
        pytest.skip("node is not available")
    script_path = tmp_path / "lexibridge-frontend.js"
    script_path.write_text(extract_inline_script(frontend_text()), encoding="utf-8")
    subprocess.run([node, "--check", str(script_path)], check=True, cwd=ROOT)


def test_frontend_api_paths_are_documented_in_openapi():
    missing = sorted(FRONTEND_API_PATHS - openapi_paths())
    assert missing == []


def test_frontend_has_error_code_mapping():
    text = frontend_text()
    for code in CORE_ERROR_CODES:
        assert code in text


def test_frontend_does_not_embed_secrets_or_local_paths():
    text = frontend_text()
    assert "/Users/" not in text
    assert not re.search(r"sk-[A-Za-z0-9]{20,}", text)
    assert "DEEPSEEK_API_KEY" not in text


def test_role_navigation_boundaries_are_explicit():
    text = frontend_text()
    student_block = re.search(r"student:\s*\[(.*?)\],\s*teacher:", text, flags=re.S).group(1)
    teacher_block = re.search(r"teacher:\s*\[(.*?)\],\s*admin:", text, flags=re.S).group(1)
    assert "admin" not in student_block.lower()
    assert "teacher" not in student_block.lower()
    assert "users" not in teacher_block
    assert "logs" not in teacher_block
    assert "evaluationRuns" not in teacher_block


def test_concept_card_review_ui_contract_is_present():
    text = frontend_text()
    assert "conceptReview" in text
    assert "/api/concept-cards/review-queue" in text
    assert "/api/concept-cards/student-feedback-queue" in text
    assert "/api/concept-cards/student-feedback/${encodeURIComponent(feedbackUid)}/triage" in text
    assert "/api/teacher/learning-analytics" in text
    assert "/api/teacher/learning-analytics/cards" in text
    assert "/api/teacher/learning-analytics/export" in text
    assert "/api/concept-cards/${encodeURIComponent(cardUid)}/reviews" in text
    assert "/api/concept-cards/${encodeURIComponent(card.card_uid)}/review" in text
    assert "CourseReviewPolicy / CourseReviewPermission" in text
    assert "Alignment confidence is verification output, not final approval confidence" in text
    assert "mark_needs_more_evidence" in text
    for test_id in [
        "concept-review-nav",
        "review-queue",
        "review-filter-status",
        "review-filter-course",
        "review-card-row",
        "review-card-detail",
        "english-evidence-list",
        "chinese-evidence-list",
        "review-history",
        "review-action-approve",
        "review-action-reject",
        "review-action-request-revision",
        "review-action-more-evidence",
        "review-submit",
        "review-error",
        "review-success",
        "teacher-feedback-queue",
        "teacher-feedback-row",
        "teacher-feedback-filter-status",
        "teacher-feedback-filter-type",
        "teacher-feedback-detail",
        "teacher-feedback-action-acknowledge",
        "teacher-feedback-action-resolve",
        "teacher-feedback-action-request-revision",
        "teacher-feedback-action-reopen",
        "teacher-feedback-action-reject",
        "teacher-feedback-error",
        "teacher-feedback-success",
        "teacher-learning-analytics",
        "teacher-analytics-course-filter",
        "teacher-analytics-chapter-filter",
        "teacher-analytics-summary",
        "teacher-analytics-chapter-table",
        "teacher-analytics-low-mastery-list",
        "teacher-analytics-feedback-hotspots",
        "teacher-analytics-export",
        "teacher-analytics-error",
        "teacher-analytics-success",
    ]:
        assert f'data-testid="{test_id}"' in text


def test_student_concept_card_ui_contract_is_present():
    text = frontend_text()
    assert "studentConceptCards" in text
    assert "/api/student/concept-cards" in text
    assert "/api/student/concept-cards/${encodeURIComponent(cardUid)}" in text
    assert "/api/student/concept-cards/${encodeURIComponent(cardUid)}/state" in text
    assert "/api/student/concept-cards/${encodeURIComponent(card.card_uid)}/feedback" in text
    assert "/api/student/concept-cards/export" in text
    assert "/api/student/courses" in text
    assert "/api/student/progress" in text
    assert "Only teacher-approved ConceptAlignmentCards are shown" in text
    assert "Alignment confidence is not final correctness" in text
    assert "No accessible course concept cards." in text
    assert "conceptReview" in text
    for test_id in [
        "student-concept-card-nav",
        "student-concept-card-page",
        "student-course-list",
        "student-no-access-message",
        "student-course-membership-status",
        "student-visibility-error",
        "student-card-filter-course",
        "student-card-filter-chapter",
        "student-card-search",
        "student-card-row",
        "student-card-detail",
        "student-english-evidence-list",
        "student-chinese-evidence-list",
        "student-favorite-toggle",
        "student-mastered-toggle",
        "student-feedback-form",
        "student-feedback-submit",
        "student-export-button",
        "student-card-error",
        "student-card-success",
        "student-progress-panel",
        "student-progress-course-row",
        "student-progress-mastered-count",
        "student-progress-unmastered-count",
        "student-progress-mastery-rate",
        "student-unmastered-shortcut",
        "student-recent-activity-list",
        "concept-review-nav",
    ]:
        assert f'data-testid="{test_id}"' in text
