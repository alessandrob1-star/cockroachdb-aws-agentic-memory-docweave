"""Durable persistence boundaries for DocWeave."""

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
from docweave.persistence.operation_repository import (
    CockroachOperationRepository,
    PersistenceConflictError,
    PersistenceNotFoundError,
)
from docweave.persistence.orchestration import (
    ActiveExecutionLeaseError,
    DurableExecutionLedger,
    DurableOperationLifecycleRecorder,
    PersistenceEvidenceError,
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
    "CockroachOperationRepository",
    "CockroachTransactionRunner",
    "CreateBatch",
    "DurableExecutionLedger",
    "DurableOperationLifecycleRecorder",
    "DurableOperationRuntime",
    "DurableRuntimeOptions",
    "ExecutionIntentMapping",
    "OperationExecutionIdentity",
    "OperationPersistenceRepository",
    "OperationResultMapping",
    "PersistedOperationExecution",
    "PersistenceConflictError",
    "PersistenceDisposition",
    "PersistenceEvidenceError",
    "PersistenceIdentityMap",
    "PersistenceNotFoundError",
    "RecordExecutionIntent",
    "RecordOperationResult",
    "TransactionExecutionError",
    "TransactionRetry",
    "TransactionRetryHooks",
    "TransactionRetryPolicy",
    "TransactionRun",
    "build_durable_operation_runtime",
    "map_audit_event",
    "map_create_batch",
    "map_execution_intent",
    "map_operation_result",
]
