import os
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import or_


SENTINEL_PREFIX = "LEXIBRIDGE_SENTINEL_SECRET_"

PROVIDER_ADMIN_ENV_KEYS = (
    "AI_PROVIDER",
    "AI_PROVIDER_MODE",
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_BASE_URL",
    "OPENAI_PROVIDER_MODE",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
)

PROVIDER_ADMIN_GLOBALS = (
    "AI_PROVIDER",
    "AI_PROVIDER_MODE",
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_BASE_URL",
    "OPENAI_PROVIDER_MODE",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
)


@dataclass(frozen=True)
class ProviderAdminStateSnapshot:
    environ: dict[str, Optional[str]]
    module_globals: dict[str, object]


def capture_provider_admin_state(app_module):
    return ProviderAdminStateSnapshot(
        environ={key: os.environ.get(key) for key in PROVIDER_ADMIN_ENV_KEYS},
        module_globals={
            key: getattr(app_module, key)
            for key in PROVIDER_ADMIN_GLOBALS
            if hasattr(app_module, key)
        },
    )


def restore_provider_admin_state(app_module, snapshot):
    _restore_environment(snapshot)
    _restore_module_globals(app_module, snapshot)
    with app_module.app.app_context():
        app_module.db.session.rollback()
        _delete_sentinel_rows(app_module)
        app_module.db.session.commit()
        assert not app_module.db.session.new
        assert not app_module.db.session.dirty
        assert not app_module.db.session.deleted
        app_module.db.session.remove()


def assert_provider_admin_state_clean(app_module):
    with app_module.app.app_context():
        for model in _sentinel_models(app_module):
            conditions = _sentinel_conditions(model)
            if not conditions:
                continue
            assert model.query.filter(or_(*conditions)).count() == 0
        assert not app_module.db.session.new
        assert not app_module.db.session.dirty
        assert not app_module.db.session.deleted


def _restore_environment(snapshot):
    for key, value in snapshot.environ.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def _restore_module_globals(app_module, snapshot):
    for key, value in snapshot.module_globals.items():
        setattr(app_module, key, value)


def _delete_sentinel_rows(app_module):
    for model in _sentinel_models(app_module):
        conditions = _sentinel_conditions(model)
        if conditions:
            model.query.filter(or_(*conditions)).delete(synchronize_session=False)


def _sentinel_models(app_module):
    names = (
        "AIProviderConfig",
        "AIModelRegistry",
        "PromptTemplate",
        "AICallLog",
        "AlignmentRun",
        "BackgroundJob",
        "BackgroundJobEvent",
        "TerminologyCard",
        "UsageRecord",
        "SystemLog",
        "AlignmentProviderUsageRecord",
        "AlignmentVerificationRun",
        "AlignmentProviderPreflightRun",
        "AlignmentProviderPolicy",
        "AuditRecord",
        "ConceptAlignmentCard",
        "DocumentAlignmentItemVerificationExecution",
    )
    return [getattr(app_module, name) for name in names if hasattr(app_module, name)]


def _sentinel_conditions(model):
    conditions = []
    for column in model.__table__.columns:
        try:
            python_type = column.type.python_type
        except NotImplementedError:
            continue
        if python_type is str:
            conditions.append(getattr(model, column.name).contains(SENTINEL_PREFIX))
    return conditions
