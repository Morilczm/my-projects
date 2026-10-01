"""Legacy admin AI configuration route registration.

This module owns the shared legacy provider configuration rule, including the
seed-backed GET views and the thin prompt mutation HTTP adapter.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable

from flask import request

from routes.shared import RouteCoreDependencies
from services.legacy_provider_prompt_mutation import LegacyPromptMutationRequest


ROUTE_MARKER = "legacy_provider_admin_configuration_routes"
TARGET_ROUTES = {
    "/api/admin/ai/providers": {
        "endpoint": "admin_ai_providers",
        "method": "GET",
    },
    "/api/admin/ai/models": {
        "endpoint": "admin_ai_models",
        "method": "GET",
    },
    "/api/admin/ai/prompts": {
        "endpoint": "admin_ai_prompts",
        "methods": {"GET", "POST"},
    },
}


@dataclass(frozen=True)
class LegacyProviderAdminConfigurationModels:
    """Domain model dependencies for legacy admin AI configuration views."""

    AIProviderConfig: Any
    AIModelRegistry: Any
    PromptTemplate: Any


@dataclass(frozen=True)
class LegacyProviderAdminConfigurationSerializers:
    """Legacy response helpers passed explicitly from the Flask app."""

    api_success: Callable[..., Any]
    api_error: Callable[[str, str, int], Any]
    serialize_ai_provider_config: Callable[[Any], dict[str, Any]]
    serialize_ai_model_registry: Callable[[Any], dict[str, Any]]
    serialize_prompt_template: Callable[[Any], dict[str, Any]]
    current_provider_metadata: Callable[[], dict[str, Any]]


def register_legacy_provider_admin_configuration_routes(
    app,
    *,
    core: RouteCoreDependencies,
    models: LegacyProviderAdminConfigurationModels,
    serializers: LegacyProviderAdminConfigurationSerializers,
    registry_seed_service: Callable[..., Any],
    seed_models: Any,
    provider_selection_factory: Callable[[], Any],
    default_prompts: Iterable[dict[str, Any]],
    model_version_factory: Callable[[], str],
    prompt_mutation_service: Callable[..., Any],
    prompt_mutation_dependencies: Any,
) -> None:
    """Register legacy admin AI provider/model/prompt configuration routes."""

    registered = app.extensions.setdefault("lexibridge_route_modules", set())
    if ROUTE_MARKER in registered:
        return

    _assert_no_duplicate_target_routes(app)

    def seed_registry(owner_user_id: int) -> None:
        registry_seed_service(
            db=core.db,
            models=seed_models,
            selection=provider_selection_factory(),
            default_prompts=default_prompts,
            current_time_text=core.current_time_text,
            model_version=model_version_factory(),
            owner_user_id=owner_user_id,
        )

    def admin_ai_providers():
        user, error_response = core.require_current_user({"admin"})
        if error_response:
            return error_response
        seed_registry(user.id)
        providers = models.AIProviderConfig.query.order_by(
            models.AIProviderConfig.is_default.desc(),
            models.AIProviderConfig.id.asc(),
        ).all()
        return serializers.api_success(
            {
                "items": [
                    serializers.serialize_ai_provider_config(provider)
                    for provider in providers
                ],
                "current": serializers.current_provider_metadata(),
            }
        )

    def admin_ai_models():
        user, error_response = core.require_current_user({"admin"})
        if error_response:
            return error_response
        seed_registry(user.id)
        ai_models = models.AIModelRegistry.query.order_by(
            models.AIModelRegistry.provider_name.asc(),
            models.AIModelRegistry.id.desc(),
        ).all()
        return serializers.api_success(
            {"items": [serializers.serialize_ai_model_registry(model) for model in ai_models]}
        )

    def admin_ai_prompts():
        user, error_response = core.require_current_user({"admin"})
        if error_response:
            return error_response
        if request.method == "POST":
            data = request.get_json() or {}
            mutation_request = LegacyPromptMutationRequest.from_payload(data, actor_user_id=user.id)
            result = prompt_mutation_service(
                request=mutation_request,
                dependencies=prompt_mutation_dependencies,
            )
            if result.outcome == "validation_error":
                return serializers.api_error(result.error_code, result.message, 400)
            if result.outcome == "persistence_error":
                return serializers.api_error(result.error_code, result.message, 500)
            return serializers.api_success(
                serializers.serialize_prompt_template(result.prompt),
                result.message,
            )
        seed_registry(user.id)
        prompts = models.PromptTemplate.query.order_by(
            models.PromptTemplate.prompt_key.asc(),
            models.PromptTemplate.id.desc(),
        ).all()
        return serializers.api_success(
            {"items": [serializers.serialize_prompt_template(prompt) for prompt in prompts]}
        )

    app.add_url_rule(
        "/api/admin/ai/providers",
        endpoint="admin_ai_providers",
        view_func=admin_ai_providers,
        methods=["GET"],
    )
    app.add_url_rule(
        "/api/admin/ai/models",
        endpoint="admin_ai_models",
        view_func=admin_ai_models,
        methods=["GET"],
    )
    app.add_url_rule(
        "/api/admin/ai/prompts",
        endpoint="admin_ai_prompts",
        view_func=admin_ai_prompts,
        methods=["GET", "POST"],
    )
    registered.add(ROUTE_MARKER)


def _assert_no_duplicate_target_routes(app) -> None:
    for path, route in TARGET_ROUTES.items():
        expected_methods = route["methods"] if "methods" in route else {route["method"]}
        endpoint = route["endpoint"]
        for rule in app.url_map.iter_rules():
            duplicated_methods = expected_methods.intersection(rule.methods)
            if rule.rule == path and duplicated_methods:
                methods = ", ".join(sorted(duplicated_methods))
                raise RuntimeError(
                    f"Cannot register {endpoint}: {methods} {path} is already registered as {rule.endpoint}."
                )
