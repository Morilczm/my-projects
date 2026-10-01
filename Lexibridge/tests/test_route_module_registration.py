import ast
import importlib.util
import sys
from pathlib import Path

from flask import Flask

from routes.shared import RouteCoreDependencies


ROOT = Path(__file__).resolve().parents[1]
TEACHER_MODULE_PATH = ROOT / "backend" / "routes" / "teacher_learning_analytics.py"
STUDENT_MODULE_PATH = ROOT / "backend" / "routes" / "student_concept_cards.py"
CONCEPT_REVIEW_MODULE_PATH = ROOT / "backend" / "routes" / "concept_card_review.py"
CONCEPT_FEEDBACK_MODULE_PATH = ROOT / "backend" / "routes" / "concept_card_feedback.py"
PROVIDER_GOVERNANCE_MODULE_PATH = ROOT / "backend" / "routes" / "provider_governance.py"
PROVIDER_POLICY_MODULE_PATH = ROOT / "backend" / "routes" / "provider_policy.py"
PROVIDER_PREFLIGHT_MODULE_PATH = ROOT / "backend" / "routes" / "provider_preflight.py"
ALIGNMENT_VERIFICATION_MODULE_PATH = ROOT / "backend" / "routes" / "alignment_verification.py"
ADMIN_ALIGNMENT_RUNS_MODULE_PATH = ROOT / "backend" / "routes" / "admin_alignment_runs.py"
LEGACY_PROVIDER_OBSERVABILITY_MODULE_PATH = ROOT / "backend" / "routes" / "legacy_provider_admin_observability.py"
LEGACY_PROVIDER_CONFIGURATION_MODULE_PATH = ROOT / "backend" / "routes" / "legacy_provider_admin_configuration.py"
LEGACY_PROVIDER_HEALTHCHECK_MODULE_PATH = ROOT / "backend" / "routes" / "legacy_provider_admin_healthcheck.py"
DOCUMENT_ALIGNMENT_WORKFLOW_MODULE_PATH = ROOT / "backend" / "routes" / "document_alignment_workflow_routes.py"


def load_route_module(module_path, module_name):
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    previous = sys.modules.get(module_name)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        if previous is None:
            sys.modules.pop(module_name, None)
        else:
            sys.modules[module_name] = previous
    return module


class DummyDb:
    session = object()


def dummy_core_dependencies():
    return RouteCoreDependencies(
        db=DummyDb(),
        audit_record_model=object,
        audit_record_service=object(),
        current_time_text=lambda: "",
        require_current_user=lambda roles: (None, None),
        get_route_audit_context=lambda user=None: {"request_id": "dummy"},
        attach_request_id_to_response=lambda response, audit_context: response,
        api_success_with_audit_context=lambda data=None, message="", audit_context=None: data,
        api_error_with_audit_context=lambda *args, **kwargs: ({"status": "error"}, 400),
    )


def teacher_dummy_dependencies(module):
    return {
        "core": dummy_core_dependencies(),
        "models": module.TeacherLearningAnalyticsModels(
            ConceptAlignmentCard=object,
            StudentConceptCardState=object,
            Feedback=object,
            StudentCourseMembership=object,
            CourseReviewPermission=object,
            CourseStudentVisibilityPolicy=object,
        ),
    }


def student_dummy_dependencies(module):
    return {
        "core": dummy_core_dependencies(),
        "models": module.StudentConceptCardModels(
            ConceptAlignmentCard=object,
            StudentConceptCardState=object,
            Feedback=object,
            StudentCourseMembership=object,
            CourseStudentVisibilityPolicy=object,
        ),
        "student_visible_course_names": lambda user: [],
        "student_course_access_service": object(),
        "record_student_course_access_audit": lambda *args, **kwargs: None,
    }


def concept_review_dummy_dependencies(module):
    return {
        "core": dummy_core_dependencies(),
        "models": module.ConceptCardReviewModels(
            ConceptAlignmentCard=object,
            ConceptCardReviewRecord=object,
            ConceptCardReviewAssignment=object,
            CourseReviewPolicy=object,
            CourseReviewPermission=object,
            AlignmentVerificationRun=object,
        ),
    }


def concept_feedback_dummy_dependencies(module):
    return {
        "core": dummy_core_dependencies(),
        "models": module.ConceptCardFeedbackModels(
            Feedback=object,
            ConceptAlignmentCard=object,
            ConceptCardReviewRecord=object,
            ConceptCardFeedbackTriageRecord=object,
            CourseReviewPermission=object,
            CourseReviewPolicy=object,
        ),
    }


def provider_governance_dummy_dependencies(module):
    return {
        "core": dummy_core_dependencies(),
        "models": module.ProviderGovernanceModels(
            AlignmentProviderPolicy=object,
            AlignmentProviderUsageRecord=object,
            AlignmentProviderPreflightRun=object,
        ),
    }


def provider_policy_dummy_dependencies(module):
    return {
        "core": dummy_core_dependencies(),
        "models": module.ProviderPolicyModels(
            AlignmentProviderPolicy=object,
        ),
        "record_provider_governance_audit": lambda *args, **kwargs: None,
    }


def provider_preflight_dummy_dependencies(module):
    return {
        "core": dummy_core_dependencies(),
        "models": module.ProviderPreflightModels(
            AlignmentProviderPreflightRun=object,
            AlignmentProviderPolicy=object,
        ),
        "record_provider_preflight_audit": lambda *args, **kwargs: None,
    }


def alignment_verification_dummy_dependencies(module):
    return {
        "core": dummy_core_dependencies(),
        "execution_dependencies": lambda: object(),
        "execute_fn": lambda *args, **kwargs: type(
            "Result",
            (),
            {
                "succeeded": True,
                "payload": {"ok": True},
                "message": "ok",
                "error_code": "",
                "status_code": 200,
                "audit_error_code": "",
            },
        )(),
    }


def admin_alignment_runs_dummy_dependencies(module):
    class DummyQuery:
        def order_by(self, *args, **kwargs):
            return self

        def limit(self, *args, **kwargs):
            return self

        def all(self):
            return []

    class DummyAlignmentRun:
        id = object()
        query = DummyQuery()

    return {
        "core": dummy_core_dependencies(),
        "models": module.AdminAlignmentRunModels(
            AlignmentRun=DummyAlignmentRun,
        ),
        "serialize_alignment_run": lambda run: {},
    }


def legacy_provider_observability_dummy_dependencies(module):
    class DummyQuery:
        def order_by(self, *args, **kwargs):
            return self

        def limit(self, *args, **kwargs):
            return self

        def all(self):
            return []

    class DummyAICallLog:
        id = object()
        query = DummyQuery()

    class DummyAIProviderConfig:
        id = object()
        query = DummyQuery()

    return {
        "core": dummy_core_dependencies(),
        "models": module.LegacyProviderAdminObservabilityModels(
            AICallLog=DummyAICallLog,
            AIProviderConfig=DummyAIProviderConfig,
        ),
        "serializers": module.LegacyProviderAdminObservabilitySerializers(
            api_success=lambda data=None, message="Operation completed.": data,
            serialize_ai_call_log=lambda log: {},
            serialize_ai_provider_config=lambda config: {},
            summarize_ai_calls=lambda logs: {"total_calls": len(logs)},
        ),
        "registry_seed_service": lambda owner_user_id=0: None,
    }


def legacy_provider_configuration_dummy_dependencies(module):
    class DummyQuery:
        def order_by(self, *args, **kwargs):
            return self

        def all(self):
            return []

    class DummyAIProviderConfig:
        id = object()
        is_default = object()
        query = DummyQuery()

    class DummyAIModelRegistry:
        provider_name = object()
        id = object()
        query = DummyQuery()

    class DummyPromptTemplate:
        prompt_key = object()
        id = object()
        query = DummyQuery()

    return {
        "core": dummy_core_dependencies(),
        "models": module.LegacyProviderAdminConfigurationModels(
            AIProviderConfig=DummyAIProviderConfig,
            AIModelRegistry=DummyAIModelRegistry,
            PromptTemplate=DummyPromptTemplate,
        ),
        "serializers": module.LegacyProviderAdminConfigurationSerializers(
            api_success=lambda data=None, message="Operation completed.": data,
            api_error=lambda error_code, message, status_code: ({"status": "error"}, status_code),
            serialize_ai_provider_config=lambda provider: {},
            serialize_ai_model_registry=lambda model: {},
            serialize_prompt_template=lambda prompt: {},
            current_provider_metadata=lambda: {},
        ),
        "registry_seed_service": lambda **kwargs: None,
        "seed_models": object(),
        "provider_selection_factory": lambda: object(),
        "default_prompts": [],
        "model_version_factory": lambda: "local-mvp-v1",
        "prompt_mutation_service": lambda **kwargs: type(
            "Result",
            (),
            {
                "outcome": "created",
                "prompt": object(),
                "message": "Prompt saved.",
                "error_code": None,
            },
        )(),
        "prompt_mutation_dependencies": object(),
    }


def legacy_provider_healthcheck_dummy_dependencies(module):
    class DummyQuery:
        def filter_by(self, **kwargs):
            return self

        def all(self):
            return []

    class DummyAIProviderConfig:
        query = DummyQuery()

    return {
        "core": dummy_core_dependencies(),
        "models": module.LegacyProviderAdminHealthcheckModels(
            AIProviderConfig=DummyAIProviderConfig,
        ),
        "serializers": module.LegacyProviderAdminHealthcheckSerializers(
            api_success=lambda data=None, message="Operation completed.": data,
        ),
        "registry_seed_service": lambda **kwargs: None,
        "seed_models": object(),
        "provider_selection_factory": lambda: object(),
        "default_prompts": [],
        "model_version_factory": lambda: "local-mvp-v1",
        "local_readiness_service": lambda **kwargs: type(
            "Result",
            (),
            {
                "health_updates": {"health_status": "healthy"},
                "to_payload": lambda self: {"provider_name": "mock", "health_status": "healthy"},
            },
        )(),
        "credential_presence_resolver": lambda config: False,
    }


def target_route_summary(app, prefix):
    return {
        rule.rule: {
            "endpoint": rule.endpoint,
            "methods": {method for method in rule.methods if method not in {"HEAD", "OPTIONS"}},
        }
        for rule in app.url_map.iter_rules()
        if rule.rule.startswith(prefix)
    }


def assert_module_has_no_backend_app_import(module_path, register_name, module_name):
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported_modules.append(node.module or "")
    assert "backend.app" not in imported_modules
    assert "app" not in imported_modules
    module = load_route_module(module_path, module_name)
    assert hasattr(module, register_name)
    return module


def test_route_modules_import_without_backend_app_dependency():
    assert_module_has_no_backend_app_import(
        TEACHER_MODULE_PATH,
        "register_teacher_learning_analytics_routes",
        "teacher_learning_analytics_routes",
    )
    assert_module_has_no_backend_app_import(
        STUDENT_MODULE_PATH,
        "register_student_concept_card_routes",
        "student_concept_card_routes",
    )
    assert_module_has_no_backend_app_import(
        CONCEPT_REVIEW_MODULE_PATH,
        "register_concept_card_review_routes",
        "concept_card_review_routes",
    )
    assert_module_has_no_backend_app_import(
        CONCEPT_FEEDBACK_MODULE_PATH,
        "register_concept_card_feedback_routes",
        "concept_card_feedback_routes",
    )
    assert_module_has_no_backend_app_import(
        PROVIDER_GOVERNANCE_MODULE_PATH,
        "register_provider_governance_routes",
        "provider_governance_routes",
    )
    assert_module_has_no_backend_app_import(
        PROVIDER_POLICY_MODULE_PATH,
        "register_provider_policy_routes",
        "provider_policy_routes",
    )
    assert_module_has_no_backend_app_import(
        PROVIDER_PREFLIGHT_MODULE_PATH,
        "register_provider_preflight_routes",
        "provider_preflight_routes",
    )
    assert_module_has_no_backend_app_import(
        ALIGNMENT_VERIFICATION_MODULE_PATH,
        "register_alignment_verification_routes",
        "alignment_verification_routes",
    )
    assert_module_has_no_backend_app_import(
        ADMIN_ALIGNMENT_RUNS_MODULE_PATH,
        "register_admin_alignment_run_routes",
        "admin_alignment_run_routes",
    )
    assert_module_has_no_backend_app_import(
        LEGACY_PROVIDER_OBSERVABILITY_MODULE_PATH,
        "register_legacy_provider_admin_observability_routes",
        "legacy_provider_admin_observability_routes",
    )
    assert_module_has_no_backend_app_import(
        LEGACY_PROVIDER_CONFIGURATION_MODULE_PATH,
        "register_legacy_provider_admin_configuration_routes",
        "legacy_provider_admin_configuration_routes",
    )
    assert_module_has_no_backend_app_import(
        LEGACY_PROVIDER_HEALTHCHECK_MODULE_PATH,
        "register_legacy_provider_admin_healthcheck_routes",
        "legacy_provider_admin_healthcheck_routes",
    )
    assert_module_has_no_backend_app_import(
        DOCUMENT_ALIGNMENT_WORKFLOW_MODULE_PATH,
        "register_document_alignment_workflow_routes",
        "document_alignment_workflow_routes",
    )


def test_teacher_register_function_registers_expected_routes_and_is_idempotent():
    module = load_route_module(TEACHER_MODULE_PATH, "teacher_learning_analytics_routes")
    app = Flask("route-registration-test")
    module.register_teacher_learning_analytics_routes(app, **teacher_dummy_dependencies(module))
    first = target_route_summary(app, "/api/teacher/learning-analytics")
    assert first == {
        "/api/teacher/learning-analytics": {
            "endpoint": "teacher_learning_analytics_api",
            "methods": {"GET"},
        },
        "/api/teacher/learning-analytics/cards": {
            "endpoint": "teacher_learning_analytics_cards_api",
            "methods": {"GET"},
        },
        "/api/teacher/learning-analytics/export": {
            "endpoint": "teacher_learning_analytics_export_api",
            "methods": {"GET"},
        },
    }
    module.register_teacher_learning_analytics_routes(app, **teacher_dummy_dependencies(module))
    assert target_route_summary(app, "/api/teacher/learning-analytics") == first


def test_student_register_function_registers_expected_routes_and_is_idempotent():
    module = load_route_module(STUDENT_MODULE_PATH, "student_concept_card_routes")
    app = Flask("student-route-registration-test")
    module.register_student_concept_card_routes(app, **student_dummy_dependencies(module))
    first = target_route_summary(app, "/api/student/concept-cards")
    assert first == {
        "/api/student/concept-cards": {
            "endpoint": "list_student_concept_cards_api",
            "methods": {"GET"},
        },
        "/api/student/concept-cards/export": {
            "endpoint": "export_student_concept_cards_api",
            "methods": {"GET"},
        },
        "/api/student/concept-cards/<card_uid>": {
            "endpoint": "get_student_concept_card_api",
            "methods": {"GET"},
        },
        "/api/student/concept-cards/<card_uid>/state": {
            "endpoint": "update_student_concept_card_state_api",
            "methods": {"POST"},
        },
        "/api/student/concept-cards/<card_uid>/feedback": {
            "endpoint": "student_concept_card_feedback_api",
            "methods": {"POST"},
        },
    }
    module.register_student_concept_card_routes(app, **student_dummy_dependencies(module))
    assert target_route_summary(app, "/api/student/concept-cards") == first


def test_concept_card_review_register_function_registers_expected_routes_and_is_idempotent():
    module = load_route_module(CONCEPT_REVIEW_MODULE_PATH, "concept_card_review_routes")
    app = Flask("concept-card-review-route-registration-test")
    module.register_concept_card_review_routes(app, **concept_review_dummy_dependencies(module))
    first = target_route_summary(app, "/api/concept-cards")
    expected = {
        "/api/concept-cards/review-queue": {
            "endpoint": "concept_card_review_queue_api",
            "methods": {"GET"},
        },
        "/api/concept-cards/<card_uid>/reviews": {
            "endpoint": "concept_card_reviews_api",
            "methods": {"GET"},
        },
        "/api/concept-cards/<card_uid>/review": {
            "endpoint": "concept_card_review_action_api",
            "methods": {"POST"},
        },
        "/api/concept-cards/<card_uid>/assign-reviewer": {
            "endpoint": "concept_card_assign_reviewer_api",
            "methods": {"POST"},
        },
    }
    assert {path: data for path, data in first.items() if path in expected} == expected
    module.register_concept_card_review_routes(app, **concept_review_dummy_dependencies(module))
    second = target_route_summary(app, "/api/concept-cards")
    assert {path: data for path, data in second.items() if path in expected} == expected


def test_concept_card_feedback_register_function_registers_expected_routes_and_is_idempotent():
    module = load_route_module(CONCEPT_FEEDBACK_MODULE_PATH, "concept_card_feedback_routes")
    app = Flask("concept-card-feedback-route-registration-test")
    module.register_concept_card_feedback_routes(app, **concept_feedback_dummy_dependencies(module))
    first = target_route_summary(app, "/api/concept-cards")
    expected = {
        "/api/concept-cards/student-feedback-queue": {
            "endpoint": "concept_card_student_feedback_queue_api",
            "methods": {"GET"},
        },
        "/api/concept-cards/<card_uid>/student-feedback": {
            "endpoint": "concept_card_student_feedback_for_card_api",
            "methods": {"GET"},
        },
        "/api/concept-cards/student-feedback/<feedback_uid>/triage": {
            "endpoint": "triage_concept_card_student_feedback_api",
            "methods": {"POST"},
        },
    }
    assert {path: data for path, data in first.items() if path in expected} == expected
    module.register_concept_card_feedback_routes(app, **concept_feedback_dummy_dependencies(module))
    second = target_route_summary(app, "/api/concept-cards")
    assert {path: data for path, data in second.items() if path in expected} == expected


def test_provider_governance_register_function_registers_expected_routes_and_is_idempotent():
    module = load_route_module(PROVIDER_GOVERNANCE_MODULE_PATH, "provider_governance_routes")
    app = Flask("provider-governance-route-registration-test")
    module.register_provider_governance_routes(app, **provider_governance_dummy_dependencies(module))
    first = target_route_summary(app, "/api/alignment/providers")
    expected = {
        "/api/alignment/providers": {
            "endpoint": "list_alignment_providers_api",
            "methods": {"GET"},
        },
        "/api/alignment/providers/<path:provider_name>/policy": {
            "endpoint": "get_alignment_provider_policy_api",
            "methods": {"GET"},
        },
        "/api/alignment/providers/<path:provider_name>/usage": {
            "endpoint": "list_alignment_provider_usage_api",
            "methods": {"GET"},
        },
        "/api/alignment/providers/preflight/<preflight_uid>": {
            "endpoint": "get_alignment_provider_preflight_api",
            "methods": {"GET"},
        },
        "/api/alignment/providers/<path:provider_name>/preflight": {
            "endpoint": "list_alignment_provider_preflights_api",
            "methods": {"GET"},
        },
    }
    assert {path: data for path, data in first.items() if path in expected} == expected
    module.register_provider_governance_routes(app, **provider_governance_dummy_dependencies(module))
    second = target_route_summary(app, "/api/alignment/providers")
    assert {path: data for path, data in second.items() if path in expected} == expected


def test_provider_policy_register_function_registers_expected_routes_and_is_idempotent():
    module = load_route_module(PROVIDER_POLICY_MODULE_PATH, "provider_policy_routes")
    app = Flask("provider-policy-route-registration-test")
    module.register_provider_policy_routes(app, **provider_policy_dummy_dependencies(module))
    first = target_route_summary(app, "/api/alignment/providers")
    expected = {
        "/api/alignment/providers/<path:provider_name>/policy": {
            "endpoint": "update_alignment_provider_policy_api",
            "methods": {"POST"},
        },
    }
    assert {path: data for path, data in first.items() if path in expected} == expected
    module.register_provider_policy_routes(app, **provider_policy_dummy_dependencies(module))
    second = target_route_summary(app, "/api/alignment/providers")
    assert {path: data for path, data in second.items() if path in expected} == expected


def test_provider_preflight_register_function_registers_expected_routes_and_is_idempotent():
    module = load_route_module(PROVIDER_PREFLIGHT_MODULE_PATH, "provider_preflight_routes")
    app = Flask("provider-preflight-route-registration-test")
    module.register_provider_preflight_routes(app, **provider_preflight_dummy_dependencies(module))
    first = target_route_summary(app, "/api/alignment/providers")
    expected = {
        "/api/alignment/providers/<path:provider_name>/preflight": {
            "endpoint": "run_alignment_provider_preflight_api",
            "methods": {"POST"},
        },
    }
    assert {path: data for path, data in first.items() if path in expected} == expected
    module.register_provider_preflight_routes(app, **provider_preflight_dummy_dependencies(module))
    second = target_route_summary(app, "/api/alignment/providers")
    assert {path: data for path, data in second.items() if path in expected} == expected


def test_alignment_verification_register_function_registers_expected_route_and_is_idempotent():
    module = load_route_module(ALIGNMENT_VERIFICATION_MODULE_PATH, "alignment_verification_routes")
    app = Flask("alignment-verification-route-registration-test")
    module.register_alignment_verification_routes(app, **alignment_verification_dummy_dependencies(module))
    first = target_route_summary(app, "/api/alignment/verify")
    assert first == {
        "/api/alignment/verify": {
            "endpoint": "verify_alignment_api",
            "methods": {"POST"},
        },
    }
    module.register_alignment_verification_routes(app, **alignment_verification_dummy_dependencies(module))
    assert target_route_summary(app, "/api/alignment/verify") == first


def test_admin_alignment_runs_register_function_registers_expected_route_and_is_idempotent():
    module = load_route_module(ADMIN_ALIGNMENT_RUNS_MODULE_PATH, "admin_alignment_run_routes")
    app = Flask("admin-alignment-run-route-registration-test")
    module.register_admin_alignment_run_routes(app, **admin_alignment_runs_dummy_dependencies(module))
    first = target_route_summary(app, "/api/admin/alignment-runs")
    assert first == {
        "/api/admin/alignment-runs": {
            "endpoint": "admin_alignment_runs",
            "methods": {"GET"},
        },
    }
    module.register_admin_alignment_run_routes(app, **admin_alignment_runs_dummy_dependencies(module))
    assert target_route_summary(app, "/api/admin/alignment-runs") == first


def test_legacy_provider_observability_register_function_registers_expected_routes_and_is_idempotent():
    module = load_route_module(LEGACY_PROVIDER_OBSERVABILITY_MODULE_PATH, "legacy_provider_admin_observability_routes")
    app = Flask("legacy-provider-observability-route-registration-test")
    module.register_legacy_provider_admin_observability_routes(app, **legacy_provider_observability_dummy_dependencies(module))
    first = target_route_summary(app, "/api/admin/ai")
    expected = {
        "/api/admin/ai/calls": {
            "endpoint": "admin_ai_calls",
            "methods": {"GET"},
        },
        "/api/admin/ai/usage": {
            "endpoint": "admin_ai_usage",
            "methods": {"GET"},
        },
        "/api/admin/ai/health": {
            "endpoint": "admin_ai_health",
            "methods": {"GET"},
        },
    }
    assert {path: data for path, data in first.items() if path in expected} == expected
    module.register_legacy_provider_admin_observability_routes(app, **legacy_provider_observability_dummy_dependencies(module))
    second = target_route_summary(app, "/api/admin/ai")
    assert {path: data for path, data in second.items() if path in expected} == expected


def test_legacy_provider_configuration_register_function_registers_expected_routes_and_is_idempotent():
    module = load_route_module(LEGACY_PROVIDER_CONFIGURATION_MODULE_PATH, "legacy_provider_admin_configuration_routes")
    app = Flask("legacy-provider-configuration-route-registration-test")
    module.register_legacy_provider_admin_configuration_routes(app, **legacy_provider_configuration_dummy_dependencies(module))
    first = target_route_summary(app, "/api/admin/ai")
    expected = {
        "/api/admin/ai/providers": {
            "endpoint": "admin_ai_providers",
            "methods": {"GET"},
        },
        "/api/admin/ai/models": {
            "endpoint": "admin_ai_models",
            "methods": {"GET"},
        },
        "/api/admin/ai/prompts": {
            "endpoint": "admin_ai_prompts",
            "methods": {"GET", "POST"},
        },
    }
    assert {path: data for path, data in first.items() if path in expected} == expected
    module.register_legacy_provider_admin_configuration_routes(app, **legacy_provider_configuration_dummy_dependencies(module))
    second = target_route_summary(app, "/api/admin/ai")
    assert {path: data for path, data in second.items() if path in expected} == expected


def test_legacy_provider_healthcheck_register_function_registers_expected_route_and_is_idempotent():
    module = load_route_module(LEGACY_PROVIDER_HEALTHCHECK_MODULE_PATH, "legacy_provider_admin_healthcheck_routes")
    app = Flask("legacy-provider-healthcheck-route-registration-test")
    module.register_legacy_provider_admin_healthcheck_routes(app, **legacy_provider_healthcheck_dummy_dependencies(module))
    first = target_route_summary(app, "/api/admin/ai")
    expected = {
        "/api/admin/ai/healthcheck": {
            "endpoint": "admin_ai_healthcheck",
            "methods": {"POST"},
        },
    }
    assert {path: data for path, data in first.items() if path in expected} == expected
    module.register_legacy_provider_admin_healthcheck_routes(app, **legacy_provider_healthcheck_dummy_dependencies(module))
    second = target_route_summary(app, "/api/admin/ai")
    assert {path: data for path, data in second.items() if path in expected} == expected


def test_existing_app_has_no_duplicate_teacher_analytics_routes(app_module):
    summary = target_route_summary(app_module.app, "/api/teacher/learning-analytics")
    assert summary == {
        "/api/teacher/learning-analytics": {
            "endpoint": "teacher_learning_analytics_api",
            "methods": {"GET"},
        },
        "/api/teacher/learning-analytics/cards": {
            "endpoint": "teacher_learning_analytics_cards_api",
            "methods": {"GET"},
        },
        "/api/teacher/learning-analytics/export": {
            "endpoint": "teacher_learning_analytics_export_api",
            "methods": {"GET"},
        },
    }


def test_existing_app_has_no_duplicate_student_concept_card_routes(app_module):
    summary = target_route_summary(app_module.app, "/api/student/concept-cards")
    assert summary == {
        "/api/student/concept-cards": {
            "endpoint": "list_student_concept_cards_api",
            "methods": {"GET"},
        },
        "/api/student/concept-cards/export": {
            "endpoint": "export_student_concept_cards_api",
            "methods": {"GET"},
        },
        "/api/student/concept-cards/<card_uid>": {
            "endpoint": "get_student_concept_card_api",
            "methods": {"GET"},
        },
        "/api/student/concept-cards/<card_uid>/state": {
            "endpoint": "update_student_concept_card_state_api",
            "methods": {"POST"},
        },
        "/api/student/concept-cards/<card_uid>/feedback": {
            "endpoint": "student_concept_card_feedback_api",
            "methods": {"POST"},
        },
    }


def test_existing_app_has_no_duplicate_concept_card_review_routes(app_module):
    summary = target_route_summary(app_module.app, "/api/concept-cards")
    expected = {
        "/api/concept-cards/review-queue": {
            "endpoint": "concept_card_review_queue_api",
            "methods": {"GET"},
        },
        "/api/concept-cards/<card_uid>/reviews": {
            "endpoint": "concept_card_reviews_api",
            "methods": {"GET"},
        },
        "/api/concept-cards/<card_uid>/review": {
            "endpoint": "concept_card_review_action_api",
            "methods": {"POST"},
        },
        "/api/concept-cards/<card_uid>/assign-reviewer": {
            "endpoint": "concept_card_assign_reviewer_api",
            "methods": {"POST"},
        },
    }
    assert {path: data for path, data in summary.items() if path in expected} == expected


def test_existing_app_has_no_duplicate_concept_card_feedback_routes(app_module):
    summary = target_route_summary(app_module.app, "/api/concept-cards")
    expected = {
        "/api/concept-cards/student-feedback-queue": {
            "endpoint": "concept_card_student_feedback_queue_api",
            "methods": {"GET"},
        },
        "/api/concept-cards/<card_uid>/student-feedback": {
            "endpoint": "concept_card_student_feedback_for_card_api",
            "methods": {"GET"},
        },
        "/api/concept-cards/student-feedback/<feedback_uid>/triage": {
            "endpoint": "triage_concept_card_student_feedback_api",
            "methods": {"POST"},
        },
    }
    assert {path: data for path, data in summary.items() if path in expected} == expected


def test_existing_app_has_no_duplicate_provider_governance_routes(app_module):
    expected = {
        ("/api/alignment/providers", "GET"): "list_alignment_providers_api",
        ("/api/alignment/providers/<path:provider_name>/policy", "GET"): "get_alignment_provider_policy_api",
        ("/api/alignment/providers/<path:provider_name>/policy", "POST"): "update_alignment_provider_policy_api",
        ("/api/alignment/providers/<path:provider_name>/usage", "GET"): "list_alignment_provider_usage_api",
        ("/api/alignment/providers/preflight/<preflight_uid>", "GET"): "get_alignment_provider_preflight_api",
        ("/api/alignment/providers/<path:provider_name>/preflight", "GET"): "list_alignment_provider_preflights_api",
        ("/api/alignment/providers/<path:provider_name>/preflight", "POST"): "run_alignment_provider_preflight_api",
    }
    actual = {}
    for rule in app_module.app.url_map.iter_rules():
        for method in rule.methods - {"HEAD", "OPTIONS"}:
            if rule.rule.startswith("/api/alignment/providers"):
                actual[(rule.rule, method)] = rule.endpoint
    for key, endpoint in expected.items():
        assert actual.get(key) == endpoint
        assert sum(1 for rule in app_module.app.url_map.iter_rules() if rule.rule == key[0] and key[1] in rule.methods) == 1


def test_existing_app_has_single_alignment_verification_route(app_module):
    actual = {}
    for rule in app_module.app.url_map.iter_rules():
        for method in rule.methods - {"HEAD", "OPTIONS"}:
            if rule.rule == "/api/alignment/verify":
                actual[(rule.rule, method)] = rule.endpoint
    assert actual == {("/api/alignment/verify", "POST"): "verify_alignment_api"}
    assert sum(
        1
        for rule in app_module.app.url_map.iter_rules()
        if rule.rule == "/api/alignment/verify" and "POST" in rule.methods
    ) == 1


def test_existing_app_has_single_admin_alignment_runs_route(app_module):
    actual = {}
    for rule in app_module.app.url_map.iter_rules():
        for method in rule.methods - {"HEAD", "OPTIONS"}:
            if rule.rule == "/api/admin/alignment-runs":
                actual[(rule.rule, method)] = rule.endpoint
    assert actual == {("/api/admin/alignment-runs", "GET"): "admin_alignment_runs"}
    assert sum(
        1
        for rule in app_module.app.url_map.iter_rules()
        if rule.rule == "/api/admin/alignment-runs" and "GET" in rule.methods
    ) == 1


def test_existing_app_has_single_legacy_provider_observability_routes(app_module):
    expected = {
        ("/api/admin/ai/calls", "GET"): "admin_ai_calls",
        ("/api/admin/ai/usage", "GET"): "admin_ai_usage",
        ("/api/admin/ai/health", "GET"): "admin_ai_health",
    }
    actual = {}
    for rule in app_module.app.url_map.iter_rules():
        for method in rule.methods - {"HEAD", "OPTIONS"}:
            if rule.rule in {path for path, _method in expected}:
                actual[(rule.rule, method)] = rule.endpoint
    assert actual == expected
    for path, method in expected:
        assert sum(
            1
            for rule in app_module.app.url_map.iter_rules()
            if rule.rule == path and method in rule.methods
        ) == 1


def test_existing_app_has_single_legacy_provider_configuration_routes(app_module):
    expected = {
        ("/api/admin/ai/providers", "GET"): "admin_ai_providers",
        ("/api/admin/ai/models", "GET"): "admin_ai_models",
        ("/api/admin/ai/prompts", "GET"): "admin_ai_prompts",
        ("/api/admin/ai/prompts", "POST"): "admin_ai_prompts",
    }
    actual = {}
    for rule in app_module.app.url_map.iter_rules():
        for method in rule.methods - {"HEAD", "OPTIONS"}:
            if rule.rule in {path for path, _method in expected}:
                actual[(rule.rule, method)] = rule.endpoint
    assert actual == expected
    for path, method in expected:
        assert sum(
            1
            for rule in app_module.app.url_map.iter_rules()
            if rule.rule == path and method in rule.methods
        ) == 1


def test_existing_app_has_single_legacy_provider_healthcheck_route(app_module):
    actual = {}
    for rule in app_module.app.url_map.iter_rules():
        for method in rule.methods - {"HEAD", "OPTIONS"}:
            if rule.rule == "/api/admin/ai/healthcheck":
                actual[(rule.rule, method)] = rule.endpoint
    assert actual == {("/api/admin/ai/healthcheck", "POST"): "admin_ai_healthcheck"}
    assert sum(
        1
        for rule in app_module.app.url_map.iter_rules()
        if rule.rule == "/api/admin/ai/healthcheck" and "POST" in rule.methods
    ) == 1


def test_app_startup_keeps_representative_legacy_routes(app_module, client, teacher_token):
    rules = {rule.rule for rule in app_module.app.url_map.iter_rules()}
    for path in {
        "/api/concept-cards/review-queue",
        "/api/student/concept-cards",
        "/api/concept-cards/student-feedback-queue",
        "/api/alignment/verify",
        "/api/admin/alignment-runs",
        "/api/admin/ai/calls",
        "/api/admin/ai/usage",
        "/api/admin/ai/health",
        "/api/admin/ai/providers",
        "/api/admin/ai/models",
        "/api/admin/ai/prompts",
        "/api/admin/ai/healthcheck",
        "/api/alignment/providers",
        "/api/teacher/learning-analytics",
    }:
        assert path in rules

    response = client.get(
        "/api/teacher/learning-analytics",
        headers={"Authorization": f"Bearer {teacher_token}", "X-Request-ID": "route-registration-smoke"},
    )
    assert response.status_code == 200
    assert response.get_json()["request_id"] == "route-registration-smoke"

    student_view_response = client.get(
        "/api/student/concept-cards",
        headers={"Authorization": f"Bearer {teacher_token}", "X-Request-ID": "student-route-registration-smoke"},
    )
    assert student_view_response.status_code == 200
    assert student_view_response.get_json()["request_id"] == "student-route-registration-smoke"
