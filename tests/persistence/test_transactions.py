from collections.abc import Callable, Iterator

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Connection
from sqlalchemy.exc import OperationalError

from docweave.persistence import (
    CockroachTransactionRunner,
    TransactionExecutionError,
    TransactionRetry,
    TransactionRetryHooks,
    TransactionRetryPolicy,
)


class DriverError(Exception):
    def __init__(self, sqlstate: str | None) -> None:
        super().__init__("private driver detail must not escape")
        self.sqlstate = sqlstate


def database_error(sqlstate: str | None) -> OperationalError:
    return OperationalError(
        statement="statement containing private values",
        params={"private": "value"},
        orig=DriverError(sqlstate),
    )


@pytest.fixture
def engine() -> Iterator[sa.Engine]:
    database_engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    try:
        yield database_engine
    finally:
        database_engine.dispose()


def runner(
    engine: sa.Engine,
    *,
    maximum_attempts: int = 4,
    retries: list[TransactionRetry] | None = None,
    delays: list[float] | None = None,
    jitter_fn: Callable[[float], float] = lambda cap: cap,
) -> CockroachTransactionRunner:
    return CockroachTransactionRunner(
        engine,
        policy=TransactionRetryPolicy(maximum_attempts=maximum_attempts),
        hooks=TransactionRetryHooks(
            retry_observer=None if retries is None else retries.append,
            sleep_fn=lambda delay: None if delays is None else delays.append(delay),
            jitter_fn=jitter_fn,
        ),
    )


def test_runs_work_once_in_a_serializable_transaction(engine: sa.Engine) -> None:
    observed_isolation_levels: list[str] = []

    def work(connection: Connection) -> str:
        observed_isolation_levels.append(connection.get_isolation_level())
        assert connection.in_transaction()
        return "persisted"

    outcome = runner(engine).run(work)

    assert outcome.value == "persisted"
    assert outcome.attempts == 1
    assert observed_isolation_levels == ["SERIALIZABLE"]


def test_retries_only_serialization_failures_with_bounded_backoff(
    engine: sa.Engine,
) -> None:
    retries: list[TransactionRetry] = []
    delays: list[float] = []
    attempts = 0

    def work(connection: Connection) -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise database_error("40001")
        return "committed"

    outcome = runner(engine, retries=retries, delays=delays).run(work)

    assert outcome.value == "committed"
    assert outcome.attempts == 3
    assert attempts == 3
    assert delays == [0.05, 0.1]
    assert retries == [
        TransactionRetry(1, 4, "40001", 0.05),
        TransactionRetry(2, 4, "40001", 0.1),
    ]


def test_rolls_back_failed_attempt_before_retry(engine: sa.Engine) -> None:
    with engine.begin() as connection:
        connection.execute(sa.text("CREATE TABLE evidence (value INTEGER NOT NULL)"))

    attempts = 0

    def work(connection: Connection) -> None:
        nonlocal attempts
        attempts += 1
        connection.execute(
            sa.text("INSERT INTO evidence (value) VALUES (:value)"),
            {"value": attempts},
        )
        if attempts == 1:
            raise database_error("40001")

    outcome = runner(engine).run(work)

    with engine.connect() as connection:
        values = connection.execute(
            sa.text("SELECT value FROM evidence ORDER BY value")
        ).scalars()
        assert list(values) == [2]
    assert outcome.attempts == 2


def test_exhaustion_is_sanitized_and_reports_retry_metadata(
    engine: sa.Engine,
) -> None:
    with pytest.raises(TransactionExecutionError) as raised:
        runner(engine, maximum_attempts=3).run(
            lambda connection: (_ for _ in ()).throw(database_error("40001"))
        )

    assert str(raised.value) == "database transaction failed"
    assert "private" not in str(raised.value)
    assert raised.value.sqlstate == "40001"
    assert raised.value.attempts == 3
    assert raised.value.retryable is True
    assert raised.value.__cause__ is None


def test_non_retryable_database_failure_fails_immediately(
    engine: sa.Engine,
) -> None:
    retries: list[TransactionRetry] = []

    with pytest.raises(TransactionExecutionError) as raised:
        runner(engine, retries=retries).run(
            lambda connection: (_ for _ in ()).throw(database_error("23505"))
        )

    assert raised.value.sqlstate == "23505"
    assert raised.value.attempts == 1
    assert raised.value.retryable is False
    assert retries == []


def test_unknown_or_malformed_sqlstate_is_not_exposed(engine: sa.Engine) -> None:
    with pytest.raises(TransactionExecutionError) as raised:
        runner(engine).run(
            lambda connection: (_ for _ in ()).throw(
                database_error("private connection detail")
            )
        )

    assert raised.value.sqlstate is None
    assert raised.value.retryable is False


@pytest.mark.parametrize("maximum_attempts", [0, 11])
def test_rejects_unsafe_attempt_limits(
    engine: sa.Engine,
    maximum_attempts: int,
) -> None:
    with pytest.raises(ValueError, match="maximum_attempts"):
        runner(engine, maximum_attempts=maximum_attempts)


@pytest.mark.parametrize(
    ("initial_backoff_seconds", "maximum_backoff_seconds"),
    [(-0.01, 1.0), (1.0, 0.5)],
)
def test_rejects_invalid_backoff_configuration(
    engine: sa.Engine,
    initial_backoff_seconds: float,
    maximum_backoff_seconds: float,
) -> None:
    with pytest.raises(ValueError, match="backoff_seconds"):
        TransactionRetryPolicy(
            initial_backoff_seconds=initial_backoff_seconds,
            maximum_backoff_seconds=maximum_backoff_seconds,
        )


def test_rejects_jitter_outside_bounded_cap(engine: sa.Engine) -> None:
    with pytest.raises(ValueError, match="jitter_fn"):
        CockroachTransactionRunner(
            engine,
            policy=TransactionRetryPolicy(maximum_attempts=2),
            hooks=TransactionRetryHooks(jitter_fn=lambda cap: cap + 0.01),
        ).run(lambda connection: (_ for _ in ()).throw(database_error("40001")))


def test_application_exception_is_not_retried_or_wrapped(engine: sa.Engine) -> None:
    attempts = 0

    def work(connection: Connection) -> None:
        nonlocal attempts
        attempts += 1
        raise ValueError("domain validation failed")

    with pytest.raises(ValueError, match="domain validation failed"):
        runner(engine).run(work)

    assert attempts == 1
