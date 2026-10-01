"""Legacy prompt mutation application service.

This service implements the small-pilot compatibility policy documented as
LEGACY_PROMPT_MUTABLE_REVISION_V1. It owns the prompt mutation transaction, but
it deliberately does not own HTTP parsing, Flask responses, route registration,
provider transport, credentials, or audit records.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable


LEGACY_PROMPT_MUTATION_POLICY = "LEGACY_PROMPT_MUTABLE_REVISION_V1"
_MISSING = object()


@dataclass(frozen=True)
class LegacyPromptMutationRequest:
    prompt_key: str
    prompt_version: str
    actor_user_id: int = 0
    task_type: Any = _MISSING
    language: Any = _MISSING
    template_text: Any = _MISSING
    json_schema: Any = _MISSING
    is_active: Any = _MISSING
    is_default: Any = _MISSING
    notes: Any = _MISSING

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any],
        *,
        actor_user_id: int = 0,
    ) -> "LegacyPromptMutationRequest":
        return cls(
            prompt_key=str(payload.get("prompt_key", "")).strip(),
            prompt_version=str(payload.get("prompt_version", "")).strip(),
            actor_user_id=int(actor_user_id or 0),
            task_type=_known_field(payload, "task_type"),
            language=_known_field(payload, "language"),
            template_text=_known_field(payload, "template_text"),
            json_schema=_known_field(payload, "json_schema"),
            is_active=_known_field(payload, "is_active"),
            is_default=_known_field(payload, "is_default"),
            notes=_known_field(payload, "notes"),
        )


@dataclass(frozen=True)
class LegacyPromptMutationDependencies:
    db: Any
    PromptTemplate: Any
    current_time_text: Callable[[], str]
    safe_json_loads: Callable[[Any, Any], Any]
    seed_registry: Callable[[int], Any]


@dataclass(frozen=True)
class LegacyPromptMutationResult:
    outcome: str
    prompt: Any = None
    created: bool = False
    message: str = "Prompt saved."
    error_code: str | None = None

    @classmethod
    def validation_error(cls, error_code: str, message: str) -> "LegacyPromptMutationResult":
        return cls(
            outcome="validation_error",
            error_code=error_code,
            message=message,
        )

    @classmethod
    def persistence_error(cls) -> "LegacyPromptMutationResult":
        return cls(
            outcome="persistence_error",
            error_code="INTERNAL_ERROR",
            message="Internal server error.",
        )


def execute_legacy_prompt_mutation(
    *,
    request: LegacyPromptMutationRequest,
    dependencies: LegacyPromptMutationDependencies,
) -> LegacyPromptMutationResult:
    """Create or update one mutable legacy prompt revision."""

    try:
        if not request.prompt_key or not request.prompt_version:
            dependencies.db.session.rollback()
            return LegacyPromptMutationResult.validation_error(
                "VALIDATION_ERROR",
                "prompt_key and prompt_version are required.",
            )

        dependencies.seed_registry(request.actor_user_id)
        prompt = dependencies.PromptTemplate.query.filter_by(
            prompt_key=request.prompt_key,
            prompt_version=request.prompt_version,
        ).first()
        created = prompt is None
        now = dependencies.current_time_text()
        if prompt is None:
            prompt = dependencies.PromptTemplate(
                prompt_key=request.prompt_key,
                prompt_version=request.prompt_version,
                created_at=now,
            )
            dependencies.db.session.add(prompt)

        _apply_mutation_fields(
            request=request,
            prompt=prompt,
            safe_json_loads=dependencies.safe_json_loads,
            now=now,
        )
        dependencies.db.session.commit()
        return LegacyPromptMutationResult(
            outcome="created" if created else "updated",
            prompt=prompt,
            created=created,
        )
    except Exception:
        dependencies.db.session.rollback()
        return LegacyPromptMutationResult.persistence_error()


def _known_field(payload: dict[str, Any], key: str) -> Any:
    return payload[key] if key in payload else _MISSING


def _field_or_default(value: Any, default: Any) -> Any:
    return default if value is _MISSING else value


def _apply_mutation_fields(
    *,
    request: LegacyPromptMutationRequest,
    prompt: Any,
    safe_json_loads: Callable[[Any, Any], Any],
    now: str,
) -> None:
    prompt.task_type = str(_field_or_default(request.task_type, prompt.task_type or request.prompt_key)).strip()
    prompt.language = str(_field_or_default(request.language, prompt.language or "bilingual")).strip()
    prompt.template_text = str(_field_or_default(request.template_text, prompt.template_text or "")).strip()
    schema = _field_or_default(request.json_schema, safe_json_loads(prompt.json_schema, {}))
    prompt.json_schema = json.dumps(schema, ensure_ascii=False) if isinstance(schema, (dict, list)) else str(schema)
    prompt.is_active = bool(_field_or_default(request.is_active, prompt.is_active))
    prompt.is_default = bool(_field_or_default(request.is_default, prompt.is_default))
    prompt.created_by = prompt.created_by or request.actor_user_id
    prompt.updated_at = now
    prompt.notes = str(_field_or_default(request.notes, prompt.notes or "")).strip()
