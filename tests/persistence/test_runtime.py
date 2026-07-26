from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest
from sqlalchemy.engine import Engine

from docweave.operations import (
    AppendOnlyAuditTrail,
    BatchApprovalRequest,
    BatchCreationRequest,
    BatchItemRequest,
    ExecutionResult,
    FileOperation,
    FileOperationPlan,
    FileOperationRequest,
    OperationApproval,
    OperationBatch,
    approve_operation_batch,
    create_operation_batch,
    plan_file_operation,
)
from docweave.persistence import (
    CockroachOperationRepository,
    CockroachTransactionRunner,
    DurableExecutionLedger,
    DurableOperationLifecycleRecorder,
    DurableRuntimeOptions,
    PersistenceIdentityMap,
    build_durable_operation_runtime,
)

NOW = datetime(2026, 7, 26, 16, 0, tzinfo=UTC)
WORKSPACE_EXTERNAL_ID = "workspace-001"
BATCH_EXTERNAL_ID = "batch-001"
WORKSPACE_ID = UUID("00000000-0000-4000-8000-000000000031")
BATCH_ID = UUID("00000000-0000-4000-8000-000000000032")
OPERATION_ID = UUID("00000000-0000-4000-8000-000000000033")
ACTOR_ID = UUID("00000000-0000-4000-8000-000000000034")


class NoConnectEngine:
    def __init__(self) -> None:
        self.connect_count = 0

    def connect(self) -> None:
        self.connect_count += 1
        raise AssertionError("runtime construction must not connect")


def approved_batch(tmp_path: Path) -> OperationBatch:
    source = tmp_path / "source"
    destination = tmp_path / "organized"
    source.mkdir()
    destination.mkdir()
    (source / "invoice.pdf").write_bytes(b"%PDF-1.7\ninvoice")
    plan = plan_file_operation(
        FileOperationRequest(
            operation=FileOperation.COPY,
            source_root=source,
            source_relative_path="invoice.pdf",
            destination_root=destination,
            destination_relative_path="invoices/invoice.pdf",
        )
    )
    trail = AppendOnlyAuditTrail()
    batch = create_operation_batch(
        BatchCreationRequest(
            batch_id=BATCH_EXTERNAL_ID,
            workspace_id=WORKSPACE_EXTERNAL_ID,
            created_by_user_id="creator",
            created_at_utc=NOW,
            idempotency_key="batch-create-001",
            correlation_id="correlation-001",
            policy_version="operations.v1",
            item_requests=(BatchItemRequest("item-001", plan),),
        ),
        audit_trail=trail,
    )
    return approve_operation_batch(
        batch,
        BatchApprovalRequest(
            approval_id="approval-001",
            approved_by_user_id="reviewer",
            approved_at_utc=NOW + timedelta(seconds=1),
            expires_at_utc=NOW + timedelta(minutes=10),
        ),
        audit_trail=trail,
    )


def identities() -> PersistenceIdentityMap:
    return PersistenceIdentityMap(
        external_workspace_id=WORKSPACE_EXTERNAL_ID,
        external_batch_id=BATCH_EXTERNAL_ID,
        workspace_id=WORKSPACE_ID,
        operation_batch_id=BATCH_ID,
        file_operation_ids={"item-001": OPERATION_ID},
    )


def fail_if_executed(
    plan: FileOperationPlan,
    approval: OperationApproval,
    *,
    execution_id: str,
    now_utc: datetime,
) -> ExecutionResult:
    raise AssertionError("injected executor should not run during construction")


def test_composes_one_coherent_runtime_without_database_io(tmp_path: Path) -> None:
    engine = NoConnectEngine()

    runtime = build_durable_operation_runtime(
        cast(Engine, engine),
        batch=approved_batch(tmp_path),
        identities=identities(),
        resolve_actor_identity=lambda external_id: ACTOR_ID,
        options=DurableRuntimeOptions(operation_executor=fail_if_executed),
    )

    assert isinstance(runtime.transaction_runner, CockroachTransactionRunner)
    assert isinstance(runtime.repository, CockroachOperationRepository)
    assert isinstance(runtime.execution_ledger, DurableExecutionLedger)
    assert isinstance(
        runtime.lifecycle_recorder,
        DurableOperationLifecycleRecorder,
    )
    assert runtime.execution_hooks.lifecycle_recorder is runtime.lifecycle_recorder
    assert runtime.execution_hooks.operation_executor is fail_if_executed
    assert engine.connect_count == 0


def test_rejects_mismatched_batch_identity_without_database_io(
    tmp_path: Path,
) -> None:
    engine = NoConnectEngine()
    mismatched = PersistenceIdentityMap(
        external_workspace_id=WORKSPACE_EXTERNAL_ID,
        external_batch_id="different-batch",
        workspace_id=WORKSPACE_ID,
        operation_batch_id=BATCH_ID,
        file_operation_ids={"item-001": OPERATION_ID},
    )

    with pytest.raises(ValueError, match="does not match"):
        build_durable_operation_runtime(
            cast(Engine, engine),
            batch=approved_batch(tmp_path),
            identities=mismatched,
            resolve_actor_identity=lambda external_id: ACTOR_ID,
        )

    assert engine.connect_count == 0


def test_rejects_invalid_lease_duration_without_database_io(
    tmp_path: Path,
) -> None:
    engine = NoConnectEngine()

    with pytest.raises(ValueError, match="lease_duration"):
        build_durable_operation_runtime(
            cast(Engine, engine),
            batch=approved_batch(tmp_path),
            identities=identities(),
            resolve_actor_identity=lambda external_id: ACTOR_ID,
            options=DurableRuntimeOptions(lease_duration=timedelta(0)),
        )

    assert engine.connect_count == 0
