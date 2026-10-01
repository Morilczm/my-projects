"""Legacy provider registry seed service.

This service preserves the historical admin AI registry seed behavior: it
creates missing provider/model/prompt rows and flushes them for the caller's
current transaction, but it never commits or rolls back.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class LegacyProviderRegistrySeedModels:
    AIProviderConfig: Any
    AIModelRegistry: Any
    PromptTemplate: Any


@dataclass(frozen=True)
class LegacyProviderRegistrySeedResult:
    provider_config: Any
    model: Any
    prompts: tuple[Any, ...]
    created_provider: bool
    created_model: bool
    created_prompt_count: int
    updated_provider: bool


def ensure_legacy_provider_registry_seed(
    *,
    db: Any,
    models: LegacyProviderRegistrySeedModels,
    selection: Any,
    default_prompts: Iterable[dict[str, Any]],
    current_time_text,
    model_version: str = "local-mvp-v1",
    owner_user_id: int = 0,
) -> LegacyProviderRegistrySeedResult:
    """Ensure legacy provider/model/prompt defaults in the caller's transaction."""

    now = current_time_text()
    existing_default = (
        models.AIProviderConfig.query.filter_by(is_default=True, is_enabled=True)
        .order_by(models.AIProviderConfig.id.desc())
        .first()
    )
    provider = models.AIProviderConfig.query.filter_by(
        provider_name=selection.provider_name
    ).first()
    created_provider = provider is None
    updated_provider = False

    if provider is None:
        provider = models.AIProviderConfig(
            provider_name=selection.provider_name,
            provider_mode=selection.provider_mode,
            base_url=selection.base_url,
            default_model=selection.model_name,
            is_enabled=True,
            is_default=existing_default is None,
            timeout_seconds=selection.timeout_seconds,
            max_retries=selection.max_retries,
            cost_per_1k_input_tokens=selection.cost_per_1k_input_tokens,
            cost_per_1k_output_tokens=selection.cost_per_1k_output_tokens,
            health_status="unknown",
            created_at=now,
            updated_at=now,
        )
        db.session.add(provider)
        db.session.flush()
    else:
        provider.provider_mode = provider.provider_mode or selection.provider_mode
        provider.base_url = provider.base_url or selection.base_url
        provider.default_model = provider.default_model or selection.model_name
        provider.timeout_seconds = provider.timeout_seconds or selection.timeout_seconds
        provider.max_retries = provider.max_retries or selection.max_retries
        provider.updated_at = now
        updated_provider = True

    defaults = (
        models.AIProviderConfig.query.filter_by(is_default=True)
        .order_by(models.AIProviderConfig.id.desc())
        .all()
    )
    if not defaults:
        provider.is_default = True
    elif provider.is_default:
        for other in defaults:
            if other.id != provider.id:
                other.is_default = False

    model_name = provider.default_model or selection.model_name or provider.provider_name
    model = models.AIModelRegistry.query.filter_by(
        provider_name=provider.provider_name,
        model_name=model_name,
    ).first()
    created_model = model is None
    if model is None:
        model = models.AIModelRegistry(
            provider_name=provider.provider_name,
            model_name=model_name,
            model_version=model_version,
            model_display_name=model_name,
            provider_mode=provider.provider_mode,
            is_enabled=True,
            is_default_for_provider=True,
            known_risks_json=json.dumps(
                ["mock/local providers cannot auto-approve"]
                if provider.provider_mode in {"mock", "local_heuristic", "none"}
                else [],
                ensure_ascii=False,
            ),
            created_at=now,
            updated_at=now,
        )
        db.session.add(model)
        db.session.flush()

    prompts = []
    created_prompt_count = 0
    for item in default_prompts:
        prompt = models.PromptTemplate.query.filter_by(
            prompt_key=item["prompt_key"],
            prompt_version=item["prompt_version"],
        ).first()
        if prompt is None:
            prompt = models.PromptTemplate(
                prompt_key=item["prompt_key"],
                prompt_version=item["prompt_version"],
                task_type=item["task_type"],
                language=item["language"],
                template_text=item["template_text"],
                json_schema=json.dumps(item["json_schema"], ensure_ascii=False),
                is_active=True,
                is_default=True,
                created_by=owner_user_id or 0,
                created_at=now,
                updated_at=now,
                notes=item.get("notes", ""),
            )
            db.session.add(prompt)
            db.session.flush()
            created_prompt_count += 1
        prompts.append(prompt)

    return LegacyProviderRegistrySeedResult(
        provider_config=provider,
        model=model,
        prompts=tuple(prompts),
        created_provider=created_provider,
        created_model=created_model,
        created_prompt_count=created_prompt_count,
        updated_provider=updated_provider,
    )
