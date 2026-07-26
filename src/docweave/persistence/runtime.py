"""Side-effect-free composition of the durable operation runtime."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID, uuid4

from sqlalchemy.engine import Engine

from docweave.operations.batch import (
    BatchExecutionHooks,
    OperationBatch,
    OperationExecutor,
)
from docweave.operations.execution import execute_file_operation
from docweave.persistence.mappers import ActorIdentityResolver, PersistenceIdentityMap
from docweave.persistence.operation_repository import CockroachOperationRepository
from docweave.persistence.orchestration import (
    DurableExecutionLedger,
    DurableOperationLifecycleRecorder,
)
from docweave.persistence.transactions import (
    CockroachTransactionRunner,
    TransactionRetryHooks,
    TransactionRetryPolicy,
)

LeaseTokenFactory = Callable[[], UUID]


@dataclass(frozen=True, slots=True)
class DurableOperationRuntime:
    """Coherent durable dependencies for one authorized operation batch."""

    transaction_runner: CockroachTransactionRunner
    repository: CockroachOperationRepository
    execution_ledger: DurableExecutionLedger
    lifecycle_recorder: DurableOperationLifecycleRecorder
    execution_hooks: BatchExecutionHooks


@dataclass(frozen=True, slots=True)
class DurableRuntimeOptions:
    """Optional retry, lease, and execution dependencies for composition."""

    retry_policy: TransactionRetryPolicy | None = None
    retry_hooks: TransactionRetryHooks | None = None
    lease_duration: timedelta = timedelta(minutes=2)
    lease_token_factory: LeaseTokenFactory = uuid4
    operation_executor: OperationExecutor = execute_file_operation


def build_durable_operation_runtime(
    engine: Engine,
    *,
    batch: OperationBatch,
    identities: PersistenceIdentityMap,
    resolve_actor_identity: ActorIdentityResolver,
    options: DurableRuntimeOptions | None = None,
) -> DurableOperationRuntime:
    """Compose runtime dependencies without connecting to the database.

    The caller owns engine creation, credential resolution, and authorization.
    Construction performs validation only. Database input/output starts when a
    repository-backed operation is explicitly invoked.
    """
    runtime_options = options or DurableRuntimeOptions()
    transaction_runner = CockroachTransactionRunner(
        engine,
        policy=runtime_options.retry_policy,
        hooks=runtime_options.retry_hooks,
    )
    repository = CockroachOperationRepository(transaction_runner)
    execution_ledger = DurableExecutionLedger(
        repository,
        batch=batch,
        identities=identities,
    )
    lifecycle_recorder = DurableOperationLifecycleRecorder(
        repository,
        identities=identities,
        resolve_actor_identity=resolve_actor_identity,
        lease_duration=runtime_options.lease_duration,
        lease_token_factory=runtime_options.lease_token_factory,
    )
    return DurableOperationRuntime(
        transaction_runner=transaction_runner,
        repository=repository,
        execution_ledger=execution_ledger,
        lifecycle_recorder=lifecycle_recorder,
        execution_hooks=BatchExecutionHooks(
            operation_executor=runtime_options.operation_executor,
            lifecycle_recorder=lifecycle_recorder,
        ),
    )
