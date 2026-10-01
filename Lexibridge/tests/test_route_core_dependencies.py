import ast
import inspect
from dataclasses import FrozenInstanceError, fields, is_dataclass
from pathlib import Path

import pytest
from flask import Flask

from routes.shared import RouteCoreDependencies
from routes.student_concept_cards import (
    StudentConceptCardModels,
    register_student_concept_card_routes,
)
from routes.teacher_learning_analytics import (
    TeacherLearningAnalyticsModels,
    register_teacher_learning_analytics_routes,
)
from routes.concept_card_review import (
    ConceptCardReviewModels,
    register_concept_card_review_routes,
)
from routes.concept_card_feedback import (
    ConceptCardFeedbackModels,
    register_concept_card_feedback_routes,
)
from routes.provider_governance import (
    ProviderGovernanceModels,
    register_provider_governance_routes,
)
from routes.provider_policy import (
    ProviderPolicyModels,
    register_provider_policy_routes,
)
from routes.provider_preflight import (
    ProviderPreflightModels,
    register_provider_preflight_routes,
)
from routes.alignment_verification import register_alignment_verification_routes
from routes.admin_alignment_runs import (
    AdminAlignmentRunModels,
    register_admin_alignment_run_routes,
)
from routes.legacy_provider_admin_observability import (
    LegacyProviderAdminObservabilityModels,
    register_legacy_provider_admin_observability_routes,
)
from routes.legacy_provider_admin_configuration import (
    LegacyProviderAdminConfigurationModels,
    register_legacy_provider_admin_configuration_routes,
)
from routes.legacy_provider_admin_healthcheck import (
    LegacyProviderAdminHealthcheckModels,
    register_legacy_provider_admin_healthcheck_routes,
)
from routes.document_alignment_workflow_routes import register_document_alignment_workflow_routes


ROOT = Path(__file__).resolve().parents[1]
SHARED_MODULE = ROOT / "backend" / "routes" / "shared.py"
TEACHER_MODULE = ROOT / "backend" / "routes" / "teacher_learning_analytics.py"
STUDENT_MODULE = ROOT / "backend" / "routes" / "student_concept_cards.py"
CONCEPT_REVIEW_MODULE = ROOT / "backend" / "routes" / "concept_card_review.py"
CONCEPT_FEEDBACK_MODULE = ROOT / "backend" / "routes" / "concept_card_feedback.py"
PROVIDER_GOVERNANCE_MODULE = ROOT / "backend" / "routes" / "provider_governance.py"
PROVIDER_POLICY_MODULE = ROOT / "backend" / "routes" / "provider_policy.py"
PROVIDER_PREFLIGHT_MODULE = ROOT / "backend" / "routes" / "provider_preflight.py"
ALIGNMENT_VERIFICATION_MODULE = ROOT / "backend" / "routes" / "alignment_verification.py"
ADMIN_ALIGNMENT_RUNS_MODULE = ROOT / "backend" / "routes" / "admin_alignment_runs.py"
LEGACY_PROVIDER_OBSERVABILITY_MODULE = ROOT / "backend" / "routes" / "legacy_provider_admin_observability.py"
LEGACY_PROVIDER_CONFIGURATION_MODULE = ROOT / "backend" / "routes" / "legacy_provider_admin_configuration.py"
LEGACY_PROVIDER_HEALTHCHECK_MODULE = ROOT / "backend" / "routes" / "legacy_provider_admin_healthcheck.py"
DOCUMENT_ALIGNMENT_WORKFLOW_MODULE = ROOT / "backend" / "routes" / "document_alignment_workflow_routes.py"

EXPECTED_CORE_FIELDS = {
    "db",
    "audit_record_model",
    "audit_record_service",
    "current_time_text",
    "require_current_user",
    "get_route_audit_context",
    "attach_request_id_to_response",
    "api_success_with_audit_context",
    "api_error_with_audit_context",
}


class DummyDb:
    session = object()


def _imports_for(path):
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")
    return imports


def _dummy_core():
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


def test_route_core_dependencies_shape_and_immutability():
    assert is_dataclass(RouteCoreDependencies)
    assert getattr(RouteCoreDependencies, "__dataclass_params__").frozen is True
    assert {field.name for field in fields(RouteCoreDependencies)} == EXPECTED_CORE_FIELDS
    assert len(fields(RouteCoreDependencies)) == 9

    core = _dummy_core()
    assert not hasattr(core, "app")
    assert not hasattr(core, "request")
    assert not hasattr(core, "user")
    assert not hasattr(core, "actor")
    assert not hasattr(core, "student_concept_cards_service")
    assert not hasattr(core, "teacher_learning_analytics_service")
    assert not hasattr(core, "concept_card_review_service")
    assert not hasattr(core, "concept_card_feedback_service")
    assert not hasattr(core, "course_review_policy_service")
    assert not hasattr(core, "student_feedback_service")
    assert not hasattr(core, "provider_governance_service")
    assert not hasattr(core, "provider_policy_service")
    assert not hasattr(core, "provider_preflight_service")
    assert not hasattr(core, "provider_transport")
    assert not hasattr(core, "credential_resolver")
    assert not hasattr(core, "AlignmentProviderPolicy")
    assert not hasattr(core, "alignment_verification_service")
    assert not hasattr(core, "alignment_verification_execution_service")
    assert not hasattr(core, "alignment_verification_execution_dependencies")
    assert not hasattr(core, "provider_execution_service")
    assert not hasattr(core, "AlignmentVerificationRun")
    assert not hasattr(core, "AlignmentProviderUsageRecord")
    assert not hasattr(core, "AlignmentRun")
    assert not hasattr(core, "admin_alignment_run_service")
    assert not hasattr(core, "run_query_service")
    assert not hasattr(core, "legacy_provider_observability_service")
    assert not hasattr(core, "legacy_provider_configuration_service")
    assert not hasattr(core, "registry_seed_service")
    assert not hasattr(core, "legacy_provider_healthcheck_service")
    assert not hasattr(core, "local_readiness_service")
    assert not hasattr(core, "credential_presence_resolver")
    assert not hasattr(core, "seed_models")
    assert not hasattr(core, "AICallLog")
    assert not hasattr(core, "AIProviderConfig")
    assert not hasattr(core, "AIModelRegistry")
    assert not hasattr(core, "PromptTemplate")
    assert not hasattr(core, "healthcheck_executor")
    with pytest.raises(FrozenInstanceError):
        core.db = object()


def test_shared_route_module_import_boundary():
    imports = set(_imports_for(SHARED_MODULE))
    assert "backend.app" not in imports
    assert "app" not in imports
    assert not any(name.startswith("services") for name in imports)
    assert not any("student" in name or "teacher" in name or "provider" in name for name in imports)


def test_extracted_route_modules_accept_core_and_do_not_import_backend_app():
    for path in [
        TEACHER_MODULE,
        STUDENT_MODULE,
        CONCEPT_REVIEW_MODULE,
        CONCEPT_FEEDBACK_MODULE,
        PROVIDER_GOVERNANCE_MODULE,
        PROVIDER_POLICY_MODULE,
        PROVIDER_PREFLIGHT_MODULE,
        ALIGNMENT_VERIFICATION_MODULE,
        ADMIN_ALIGNMENT_RUNS_MODULE,
        LEGACY_PROVIDER_OBSERVABILITY_MODULE,
        LEGACY_PROVIDER_CONFIGURATION_MODULE,
        LEGACY_PROVIDER_HEALTHCHECK_MODULE,
        DOCUMENT_ALIGNMENT_WORKFLOW_MODULE,
    ]:
        imports = set(_imports_for(path))
        assert "backend.app" not in imports
        assert "app" not in imports

    teacher_sig = inspect.signature(register_teacher_learning_analytics_routes)
    student_sig = inspect.signature(register_student_concept_card_routes)
    review_sig = inspect.signature(register_concept_card_review_routes)
    feedback_sig = inspect.signature(register_concept_card_feedback_routes)
    provider_sig = inspect.signature(register_provider_governance_routes)
    provider_policy_sig = inspect.signature(register_provider_policy_routes)
    provider_preflight_sig = inspect.signature(register_provider_preflight_routes)
    alignment_verification_sig = inspect.signature(register_alignment_verification_routes)
    admin_alignment_runs_sig = inspect.signature(register_admin_alignment_run_routes)
    legacy_provider_observability_sig = inspect.signature(register_legacy_provider_admin_observability_routes)
    legacy_provider_configuration_sig = inspect.signature(register_legacy_provider_admin_configuration_routes)
    legacy_provider_healthcheck_sig = inspect.signature(register_legacy_provider_admin_healthcheck_routes)
    document_alignment_workflow_sig = inspect.signature(register_document_alignment_workflow_routes)
    assert "core" in teacher_sig.parameters
    assert "core" in student_sig.parameters
    assert "core" in review_sig.parameters
    assert "core" in feedback_sig.parameters
    assert "core" in provider_sig.parameters
    assert "core" in provider_policy_sig.parameters
    assert "core" in provider_preflight_sig.parameters
    assert "core" in alignment_verification_sig.parameters
    assert "core" in admin_alignment_runs_sig.parameters
    assert "core" in legacy_provider_observability_sig.parameters
    assert "core" in legacy_provider_configuration_sig.parameters
    assert "core" in legacy_provider_healthcheck_sig.parameters
    assert "core" in document_alignment_workflow_sig.parameters
    assert "dependencies" in document_alignment_workflow_sig.parameters
    assert "execution_dependencies" in alignment_verification_sig.parameters
    assert "models" in admin_alignment_runs_sig.parameters
    assert "serialize_alignment_run" in admin_alignment_runs_sig.parameters
    assert "models" in legacy_provider_observability_sig.parameters
    assert "serializers" in legacy_provider_observability_sig.parameters
    assert "registry_seed_service" in legacy_provider_observability_sig.parameters
    assert "api_success" not in legacy_provider_observability_sig.parameters
    assert "models" in legacy_provider_configuration_sig.parameters
    assert "serializers" in legacy_provider_configuration_sig.parameters
    assert "registry_seed_service" in legacy_provider_configuration_sig.parameters
    assert "seed_models" in legacy_provider_configuration_sig.parameters
    assert "provider_selection_factory" in legacy_provider_configuration_sig.parameters
    assert "default_prompts" in legacy_provider_configuration_sig.parameters
    assert "model_version_factory" in legacy_provider_configuration_sig.parameters
    assert "prompt_mutation_service" in legacy_provider_configuration_sig.parameters
    assert "prompt_mutation_dependencies" in legacy_provider_configuration_sig.parameters
    assert "prompt_post_handler" not in legacy_provider_configuration_sig.parameters
    assert "models" in legacy_provider_healthcheck_sig.parameters
    assert "serializers" in legacy_provider_healthcheck_sig.parameters
    assert "registry_seed_service" in legacy_provider_healthcheck_sig.parameters
    assert "seed_models" in legacy_provider_healthcheck_sig.parameters
    assert "local_readiness_service" in legacy_provider_healthcheck_sig.parameters
    assert "credential_presence_resolver" in legacy_provider_healthcheck_sig.parameters
    assert "provider_transport" not in legacy_provider_healthcheck_sig.parameters
    assert "healthcheck_executor" not in legacy_provider_healthcheck_sig.parameters
    assert "api_success" not in legacy_provider_configuration_sig.parameters
    assert "api_success" not in legacy_provider_healthcheck_sig.parameters
    for name in {
        "db",
        "audit_model",
        "audit_record_service",
        "current_time_text",
        "require_current_user",
        "get_route_audit_context",
        "attach_request_id_to_response",
        "api_success_with_audit_context",
        "api_error_with_audit_context",
    }:
        assert name not in teacher_sig.parameters
        assert name not in student_sig.parameters
        assert name not in review_sig.parameters
        assert name not in feedback_sig.parameters
        assert name not in provider_sig.parameters
        assert name not in provider_policy_sig.parameters
        assert name not in provider_preflight_sig.parameters
        assert name not in alignment_verification_sig.parameters
        assert name not in admin_alignment_runs_sig.parameters
        assert name not in legacy_provider_observability_sig.parameters
        assert name not in legacy_provider_configuration_sig.parameters
        assert name not in legacy_provider_healthcheck_sig.parameters
        assert name not in document_alignment_workflow_sig.parameters

    assert "AICallLog" in LegacyProviderAdminObservabilityModels.__dataclass_fields__
    assert "AIProviderConfig" in LegacyProviderAdminObservabilityModels.__dataclass_fields__
    assert "AIProviderConfig" in LegacyProviderAdminConfigurationModels.__dataclass_fields__
    assert "AIModelRegistry" in LegacyProviderAdminConfigurationModels.__dataclass_fields__
    assert "PromptTemplate" in LegacyProviderAdminConfigurationModels.__dataclass_fields__
    assert "AIProviderConfig" in LegacyProviderAdminHealthcheckModels.__dataclass_fields__
    for service_name in {
        "concept_card_review_service",
        "concept_card_feedback_service",
        "course_review_policy_service",
        "student_feedback_service",
        "provider_governance_service",
        "provider_policy_service",
        "provider_preflight_service",
        "provider_transport",
        "credential_resolver",
        "alignment_verification_execution_service",
        "provider_execution_service",
        "admin_alignment_run_service",
        "run_query_service",
        "legacy_provider_configuration_service",
        "healthcheck_executor",
        "provider_transport",
        "credential_resolver",
    }:
        assert service_name not in review_sig.parameters
        assert service_name not in feedback_sig.parameters
        assert service_name not in provider_sig.parameters
        assert service_name not in provider_policy_sig.parameters
        assert service_name not in provider_preflight_sig.parameters
        assert service_name not in alignment_verification_sig.parameters
        assert service_name not in admin_alignment_runs_sig.parameters
        assert service_name not in legacy_provider_configuration_sig.parameters
        assert service_name not in legacy_provider_healthcheck_sig.parameters


def test_route_core_can_be_reused_by_extracted_modules_without_duplicate_endpoints():
    app = Flask("route-core-reuse-test")
    core = _dummy_core()
    register_teacher_learning_analytics_routes(
        app,
        core=core,
        models=TeacherLearningAnalyticsModels(
            ConceptAlignmentCard=object,
            StudentConceptCardState=object,
            Feedback=object,
            StudentCourseMembership=object,
            CourseReviewPermission=object,
            CourseStudentVisibilityPolicy=object,
        ),
    )
    register_student_concept_card_routes(
        app,
        core=core,
        models=StudentConceptCardModels(
            ConceptAlignmentCard=object,
            StudentConceptCardState=object,
            Feedback=object,
            StudentCourseMembership=object,
            CourseStudentVisibilityPolicy=object,
        ),
        student_visible_course_names=lambda user: [],
        student_course_access_service=object(),
        record_student_course_access_audit=lambda *args, **kwargs: None,
    )
    register_concept_card_review_routes(
        app,
        core=core,
        models=ConceptCardReviewModels(
            ConceptAlignmentCard=object,
            ConceptCardReviewRecord=object,
            ConceptCardReviewAssignment=object,
            CourseReviewPolicy=object,
            CourseReviewPermission=object,
            AlignmentVerificationRun=object,
        ),
    )
    register_concept_card_feedback_routes(
        app,
        core=core,
        models=ConceptCardFeedbackModels(
            Feedback=object,
            ConceptAlignmentCard=object,
            ConceptCardReviewRecord=object,
            ConceptCardFeedbackTriageRecord=object,
            CourseReviewPermission=object,
            CourseReviewPolicy=object,
        ),
    )
    register_provider_governance_routes(
        app,
        core=core,
        models=ProviderGovernanceModels(
            AlignmentProviderPolicy=object,
            AlignmentProviderUsageRecord=object,
            AlignmentProviderPreflightRun=object,
        ),
    )
    register_provider_policy_routes(
        app,
        core=core,
        models=ProviderPolicyModels(
            AlignmentProviderPolicy=object,
        ),
        record_provider_governance_audit=lambda *args, **kwargs: None,
    )
    register_provider_preflight_routes(
        app,
        core=core,
        models=ProviderPreflightModels(
            AlignmentProviderPreflightRun=object,
            AlignmentProviderPolicy=object,
        ),
        record_provider_preflight_audit=lambda *args, **kwargs: None,
    )
    register_alignment_verification_routes(
        app,
        core=core,
        execution_dependencies=lambda: object(),
        execute_fn=lambda *args, **kwargs: type(
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
    )
    register_admin_alignment_run_routes(
        app,
        core=core,
        models=AdminAlignmentRunModels(
            AlignmentRun=object,
        ),
        serialize_alignment_run=lambda run: {},
    )

    class DummyQuery:
        def filter_by(self, *args, **kwargs):
            return self

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

    register_legacy_provider_admin_configuration_routes(
        app,
        core=core,
        models=LegacyProviderAdminConfigurationModels(
            AIProviderConfig=DummyAIProviderConfig,
            AIModelRegistry=DummyAIModelRegistry,
            PromptTemplate=DummyPromptTemplate,
        ),
        serializers=type(
            "Serializers",
            (),
            {
                "api_success": staticmethod(lambda data=None, message="Operation completed.": data),
                "api_error": staticmethod(lambda error_code, message, status_code: ({"status": "error"}, status_code)),
                "serialize_ai_provider_config": staticmethod(lambda provider: {}),
                "serialize_ai_model_registry": staticmethod(lambda model: {}),
                "serialize_prompt_template": staticmethod(lambda prompt: {}),
                "current_provider_metadata": staticmethod(lambda: {}),
            },
        )(),
        registry_seed_service=lambda **kwargs: None,
        seed_models=object(),
        provider_selection_factory=lambda: object(),
        default_prompts=[],
        model_version_factory=lambda: "local-mvp-v1",
        prompt_mutation_service=lambda **kwargs: type(
            "Result",
            (),
            {
                "outcome": "created",
                "prompt": object(),
                "message": "Prompt saved.",
                "error_code": None,
            },
        )(),
        prompt_mutation_dependencies=object(),
    )
    register_legacy_provider_admin_healthcheck_routes(
        app,
        core=core,
        models=LegacyProviderAdminHealthcheckModels(
            AIProviderConfig=DummyAIProviderConfig,
        ),
        serializers=type(
            "HealthcheckSerializers",
            (),
            {
                "api_success": staticmethod(lambda data=None, message="Operation completed.": data),
            },
        )(),
        registry_seed_service=lambda **kwargs: None,
        seed_models=object(),
        provider_selection_factory=lambda: object(),
        default_prompts=[],
        model_version_factory=lambda: "local-mvp-v1",
        local_readiness_service=lambda **kwargs: type(
            "Result",
            (),
            {
                "health_updates": {"health_status": "healthy"},
                "to_payload": lambda self: {"provider_name": "mock", "health_status": "healthy"},
            },
        )(),
        credential_presence_resolver=lambda config: False,
    )
    paths = [
        rule.rule
        for rule in app.url_map.iter_rules()
        if rule.rule.startswith("/api/teacher/learning-analytics")
        or rule.rule.startswith("/api/student/concept-cards")
        or rule.rule.startswith("/api/concept-cards")
        or rule.rule.startswith("/api/alignment/providers")
        or rule.rule == "/api/alignment/verify"
        or rule.rule == "/api/admin/alignment-runs"
        or rule.rule.startswith("/api/admin/ai/")
    ]
    method_paths = [
        (rule.rule, method)
        for rule in app.url_map.iter_rules()
        for method in rule.methods - {"HEAD", "OPTIONS"}
        if rule.rule in paths
    ]
    assert len(method_paths) == len(set(method_paths))
    assert "/api/teacher/learning-analytics" in paths
    assert "/api/student/concept-cards" in paths
    assert "/api/concept-cards/review-queue" in paths
    assert "/api/concept-cards/student-feedback-queue" in paths
    assert "/api/alignment/providers" in paths
    assert "/api/alignment/providers/<path:provider_name>/policy" in paths
    assert "/api/alignment/providers/<path:provider_name>/preflight" in paths
    assert "/api/alignment/verify" in paths
    assert "/api/admin/alignment-runs" in paths
    assert "/api/admin/ai/providers" in paths
    assert "/api/admin/ai/models" in paths
    assert "/api/admin/ai/prompts" in paths
    assert "/api/admin/ai/healthcheck" in paths
