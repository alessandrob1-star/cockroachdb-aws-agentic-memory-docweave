from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from uuid import UUID

import pytest

from docweave import review_cli
from docweave.application_runtime import (
    ConfiguredReviewDecisionRuntime,
    RuntimeConfigurationError,
    RuntimeConfigurationErrorCode,
    RuntimeEnvironmentConfig,
)
from docweave.operations import ReviewDecisionAction
from docweave.persistence import PersistHumanDecision
from docweave.persistence.contracts import PersistenceDisposition
from docweave.review_cli import _persist_review_decision_with_runtime

WORKSPACE_ID = UUID("11111111-1111-4111-8111-111111111111")
TAXONOMY_VERSION_ID = UUID("22222222-2222-4222-8222-222222222222")
ACTOR_ID = UUID("33333333-3333-4333-8333-333333333333")
PROPOSAL_ID = UUID("44444444-4444-4444-8444-444444444444")
REVIEW_DECISION_ID = UUID("55555555-5555-4555-8555-555555555555")
NOW = datetime(2026, 7, 30, 16, 30, tzinfo=UTC)
PROPOSAL_FINGERPRINT = "ab" * 32
PLAN_FINGERPRINT = "cd" * 32


class FakeSimpleMemoryRepository:
    def __init__(self) -> None:
        self.commands: list[PersistHumanDecision] = []

    def persist_human_decision(
        self, command: PersistHumanDecision
    ) -> PersistenceDisposition:
        self.commands.append(command)
        return PersistenceDisposition.APPLIED


def _configured() -> ConfiguredReviewDecisionRuntime:
    return cast(
        ConfiguredReviewDecisionRuntime,
        SimpleNamespace(
            config=RuntimeEnvironmentConfig(
                database_url="cockroachdb://user:secret@example.test/docweave",
                workspace_id=WORKSPACE_ID,
                taxonomy_version_id=TAXONOMY_VERSION_ID,
                approved_by_actor_id=ACTOR_ID,
            ),
            transaction_runner=object(),
        ),
    )


def test_persist_review_decision_binds_cli_fields_to_simple_memory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = FakeSimpleMemoryRepository()

    def fake_repository_factory(
        transaction_runner: object,
    ) -> FakeSimpleMemoryRepository:
        assert transaction_runner is not None
        return repository

    monkeypatch.setattr(
        review_cli,
        "CockroachSimpleMemoryRepository",
        fake_repository_factory,
    )

    result = _persist_review_decision_with_runtime(
        _configured(),
        review_cli.ReviewDecisionCommandInput(
            proposal_id=PROPOSAL_ID,
            action=ReviewDecisionAction.REJECT,
            proposal_fingerprint=PROPOSAL_FINGERPRINT,
            operation_plan_fingerprint=PLAN_FINGERPRINT,
            reason="  wrong category  ",
            review_decision_id=REVIEW_DECISION_ID,
            decided_at_utc=NOW,
            document_id=UUID("66666666-6666-4666-8666-666666666666"),
            operation="reject_only",
            previous_directory="Inbox",
            previous_filename="old.pdf",
            next_directory="Reviewed",
            next_filename="new.pdf",
            file_status="rejected",
            note="operator note",
        ),
    )

    assert result.disposition is PersistenceDisposition.APPLIED
    assert result.proposal_id == PROPOSAL_ID
    assert result.review_decision_id == REVIEW_DECISION_ID
    assert len(repository.commands) == 1
    command = repository.commands[0]
    assert command.proposal_id == PROPOSAL_ID
    assert command.human_decision_id == REVIEW_DECISION_ID
    assert command.actor_label == "local-cockpit-reviewer"
    assert command.decision == ReviewDecisionAction.REJECT.value
    assert command.reason == "wrong category"
    assert command.decided_at_utc == NOW
    assert command.operation == "reject_only"
    assert command.previous_directory == "Inbox"
    assert command.previous_filename == "old.pdf"
    assert command.next_directory == "Reviewed"
    assert command.next_filename == "new.pdf"
    assert command.file_status == "rejected"
    assert command.note == "operator note"


def test_review_main_prints_sanitized_success(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fake_persist_review_decision(
        command_input: review_cli.ReviewDecisionCommandInput,
    ) -> review_cli.ReviewDecisionCommandResult:
        assert command_input.proposal_id == PROPOSAL_ID
        assert command_input.action is ReviewDecisionAction.APPROVE
        assert command_input.proposal_fingerprint == PROPOSAL_FINGERPRINT
        assert command_input.review_decision_id == REVIEW_DECISION_ID
        return review_cli.ReviewDecisionCommandResult(
            action="approve",
            proposal_id=PROPOSAL_ID,
            review_decision_id=REVIEW_DECISION_ID,
            disposition=PersistenceDisposition.IDEMPOTENT_REPLAY,
        )

    monkeypatch.setattr(
        review_cli,
        "persist_review_decision",
        fake_persist_review_decision,
    )

    result = review_cli.main(
        [
            "--proposal-id",
            str(PROPOSAL_ID),
            "--action",
            "approve",
            "--proposal-fingerprint",
            PROPOSAL_FINGERPRINT,
            "--review-decision-id",
            str(REVIEW_DECISION_ID),
        ]
    )

    captured = capsys.readouterr()
    assert result == 0
    assert "Review decision: approve" in captured.out
    assert f"Proposal id: {PROPOSAL_ID}" in captured.out
    assert "Review memory: idempotent_replay" in captured.out
    assert "secret" not in captured.out
    assert captured.err == ""


def test_review_main_reports_configuration_errors_without_secret_values(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail_persist_review_decision(
        _: review_cli.ReviewDecisionCommandInput,
    ) -> review_cli.ReviewDecisionCommandResult:
        raise RuntimeConfigurationError(
            RuntimeConfigurationErrorCode.DATABASE_URL_MISSING,
            variable_name="DOCWEAVE_DATABASE_URL",
        )

    monkeypatch.setattr(
        review_cli,
        "persist_review_decision",
        fail_persist_review_decision,
    )

    result = review_cli.main(
        [
            "--proposal-id",
            str(PROPOSAL_ID),
            "--action",
            "approve",
            "--proposal-fingerprint",
            PROPOSAL_FINGERPRINT,
        ]
    )

    captured = capsys.readouterr()
    assert result == 2
    assert "database_url_missing" in captured.err
    assert "DOCWEAVE_DATABASE_URL" in captured.err
    assert "secret" not in captured.err


def test_review_main_rejects_bad_decisions_without_detail_leakage(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail_persist_review_decision(
        _: review_cli.ReviewDecisionCommandInput,
    ) -> review_cli.ReviewDecisionCommandResult:
        raise ValueError("secret validation detail")

    monkeypatch.setattr(
        review_cli,
        "persist_review_decision",
        fail_persist_review_decision,
    )

    result = review_cli.main(
        [
            "--proposal-id",
            str(PROPOSAL_ID),
            "--action",
            "reject",
            "--proposal-fingerprint",
            PROPOSAL_FINGERPRINT,
        ]
    )

    captured = capsys.readouterr()
    assert result == 3
    assert "Review decision failed: ValueError" in captured.err
    assert "secret validation detail" not in captured.err
