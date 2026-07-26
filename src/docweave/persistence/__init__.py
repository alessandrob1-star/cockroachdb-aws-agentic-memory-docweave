"""Durable persistence boundaries for DocWeave."""

from docweave.persistence.contracts import (
    AuditAppend,
    BatchItemSnapshot,
    CreateBatch,
    OperationPersistenceRepository,
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
from docweave.persistence.transactions import (
    CockroachTransactionRunner,
    TransactionExecutionError,
    TransactionRetry,
    TransactionRetryHooks,
    TransactionRetryPolicy,
    TransactionRun,
)

__all__ = [
    "AuditAppend",
    "BatchItemSnapshot",
    "CockroachOperationRepository",
    "CockroachTransactionRunner",
    "CreateBatch",
    "ExecutionIntentMapping",
    "OperationPersistenceRepository",
    "OperationResultMapping",
    "PersistenceConflictError",
    "PersistenceDisposition",
    "PersistenceIdentityMap",
    "PersistenceNotFoundError",
    "RecordExecutionIntent",
    "RecordOperationResult",
    "TransactionExecutionError",
    "TransactionRetry",
    "TransactionRetryHooks",
    "TransactionRetryPolicy",
    "TransactionRun",
    "map_audit_event",
    "map_create_batch",
    "map_execution_intent",
    "map_operation_result",
]
