"""Durable persistence boundaries for DocWeave."""

from docweave.persistence.classification_repository import (
    ClassificationEvidenceWrite,
    ClassificationPersistenceIdentity,
    ClassificationScores,
    CockroachClassificationRepository,
    PersistClassificationProposal,
    map_bedrock_classification_run,
)
from docweave.persistence.classification_runtime import (
    ClassificationPipelineError,
    ClassificationPipelineErrorCode,
    ClassificationRunIdentity,
    ClassificationRuntime,
    ClassificationRuntimeOptions,
    PersistedClassificationRun,
    build_classification_runtime,
)
from docweave.persistence.confidence_provider import (
    provide_uncalibrated_confidence_v0,
)
from docweave.persistence.contracts import (
    AuditAppend,
    BatchItemSnapshot,
    CreateBatch,
    OperationExecutionIdentity,
    OperationPersistenceRepository,
    PersistedOperationExecution,
    PersistenceDisposition,
    RecordExecutionIntent,
    RecordOperationResult,
    RestoreAuditEventSnapshot,
    RestoreAuditQuery,
)
from docweave.persistence.lineage_repository import (
    CockroachFileLineageRepository,
    FileLineageEventSnapshot,
    FileLineageHistoryQuery,
    PersistFileLineageEvent,
)
from docweave.persistence.mappers import (
    ExecutionIntentMapping,
    OperationResultMapping,
    PersistenceIdentityMap,
    map_audit_event,
    map_create_batch,
    map_execution_intent,
    map_operation_result,
)
from docweave.persistence.memory_foundation_repository import (
    CockroachMemoryFoundationRepository,
    EnsureApprovedTaxonomy,
    RegisterDocumentVersion,
)
from docweave.persistence.operation_repository import (
    CockroachOperationRepository,
    CockroachRestoreAuditRepository,
    PersistenceConflictError,
    PersistenceNotFoundError,
)
from docweave.persistence.orchestration import (
    ActiveExecutionLeaseError,
    DurableExecutionLedger,
    DurableOperationLifecycleRecorder,
    DurableRestoreAuditRecorder,
    PersistenceEvidenceError,
)
from docweave.persistence.review_repository import (
    CockroachReviewDecisionRepository,
    PersistReviewDecision,
)
from docweave.persistence.runtime import (
    DurableOperationRuntime,
    DurableRuntimeOptions,
    build_durable_operation_runtime,
)
from docweave.persistence.transactions import (
    CockroachTransactionRunner,
    TransactionExecutionError,
    TransactionRetry,
    TransactionRetryHooks,
    TransactionRetryPolicy,
    TransactionRun,
)

__all__ = [
    "ActiveExecutionLeaseError",
    "AuditAppend",
    "BatchItemSnapshot",
    "ClassificationEvidenceWrite",
    "ClassificationPersistenceIdentity",
    "ClassificationPipelineError",
    "ClassificationPipelineErrorCode",
    "ClassificationRunIdentity",
    "ClassificationRuntime",
    "ClassificationRuntimeOptions",
    "ClassificationScores",
    "CockroachClassificationRepository",
    "CockroachFileLineageRepository",
    "CockroachMemoryFoundationRepository",
    "CockroachOperationRepository",
    "CockroachRestoreAuditRepository",
    "CockroachReviewDecisionRepository",
    "CockroachTransactionRunner",
    "CreateBatch",
    "DurableExecutionLedger",
    "DurableOperationLifecycleRecorder",
    "DurableOperationRuntime",
    "DurableRestoreAuditRecorder",
    "DurableRuntimeOptions",
    "EnsureApprovedTaxonomy",
    "ExecutionIntentMapping",
    "FileLineageEventSnapshot",
    "FileLineageHistoryQuery",
    "OperationExecutionIdentity",
    "OperationPersistenceRepository",
    "OperationResultMapping",
    "PersistClassificationProposal",
    "PersistFileLineageEvent",
    "PersistReviewDecision",
    "PersistedClassificationRun",
    "PersistedOperationExecution",
    "PersistenceConflictError",
    "PersistenceDisposition",
    "PersistenceEvidenceError",
    "PersistenceIdentityMap",
    "PersistenceNotFoundError",
    "RecordExecutionIntent",
    "RecordOperationResult",
    "RegisterDocumentVersion",
    "RestoreAuditEventSnapshot",
    "RestoreAuditQuery",
    "TransactionExecutionError",
    "TransactionRetry",
    "TransactionRetryHooks",
    "TransactionRetryPolicy",
    "TransactionRun",
    "build_classification_runtime",
    "build_durable_operation_runtime",
    "map_audit_event",
    "map_bedrock_classification_run",
    "map_create_batch",
    "map_execution_intent",
    "map_operation_result",
    "provide_uncalibrated_confidence_v0",
]
