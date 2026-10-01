"""Single-iteration dispatcher for formal document alignment jobs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from services.document_alignment_worker_handler import (
    ERROR_INTERNAL_WORKER,
    OUTCOME_NO_JOB_AVAILABLE,
    OUTCOME_OWNERSHIP_LOST,
    OUTCOME_PERSISTENCE_ERROR,
    RunFormalDocumentAlignmentJobResult,
)
from services.formal_background_job_execution import (
    CLAIM_OUTCOME_CLAIMED,
    CLAIM_OUTCOME_CLAIM_CONFLICT,
    CLAIM_OUTCOME_NO_JOB_AVAILABLE,
    CLAIM_OUTCOME_PERSISTENCE_ERROR,
)


@dataclass(frozen=True)
class FormalBackgroundJobDispatchDependencies:
    claim: Callable[[str], Any]
    handle: Callable[[Any], RunFormalDocumentAlignmentJobResult]


def run_one_formal_document_alignment_job(
    worker_id: str,
    dependencies: FormalBackgroundJobDispatchDependencies,
) -> RunFormalDocumentAlignmentJobResult:
    claim = dependencies.claim(worker_id)
    if getattr(claim, "outcome", "") == CLAIM_OUTCOME_NO_JOB_AVAILABLE:
        return RunFormalDocumentAlignmentJobResult(outcome=OUTCOME_NO_JOB_AVAILABLE)
    if getattr(claim, "outcome", "") == CLAIM_OUTCOME_CLAIM_CONFLICT:
        return RunFormalDocumentAlignmentJobResult(
            outcome=OUTCOME_OWNERSHIP_LOST,
            ownership_lost=True,
            error_code=str(getattr(claim, "error_code", "") or "FORMAL_JOB_WORKER_CLAIM_CONFLICT"),
            error_message=str(getattr(claim, "error_message", "") or "Formal job claim was won by another worker."),
        )
    if getattr(claim, "outcome", "") == CLAIM_OUTCOME_PERSISTENCE_ERROR:
        return RunFormalDocumentAlignmentJobResult(
            outcome=OUTCOME_PERSISTENCE_ERROR,
            retryable=True,
            error_code=str(getattr(claim, "error_code", "") or ERROR_INTERNAL_WORKER),
            error_message=str(getattr(claim, "error_message", "") or "Formal job claim failed safely."),
        )
    if getattr(claim, "outcome", "") != CLAIM_OUTCOME_CLAIMED or getattr(claim, "lease", None) is None:
        return RunFormalDocumentAlignmentJobResult(
            outcome=OUTCOME_PERSISTENCE_ERROR,
            retryable=True,
            error_code=ERROR_INTERNAL_WORKER,
            error_message="Formal job claim returned an invalid result.",
        )
    return dependencies.handle(claim.lease)
