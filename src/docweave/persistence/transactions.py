"""Bounded CockroachDB serializable transaction execution.

This module owns transaction retry policy only. It does not open a connection
until ``run`` is called, create schemas, resolve credentials, or persist
application records by itself.
"""

from collections.abc import Callable
from dataclasses import dataclass
from secrets import randbelow
from time import sleep
from typing import TypeVar

from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import DBAPIError

_SERIALIZATION_FAILURE_SQLSTATE = "40001"
_MAX_ATTEMPTS_LIMIT = 10
_JITTER_STEPS = 1_000
_SQLSTATE_LENGTH = 5

T = TypeVar("T")
TransactionWork = Callable[[Connection], T]
RetryObserver = Callable[["TransactionRetry"], None]
Sleep = Callable[[float], None]
Jitter = Callable[[float], float]


def _full_jitter(cap: float) -> float:
    if cap == 0:
        return 0.0
    return cap * randbelow(_JITTER_STEPS + 1) / _JITTER_STEPS


@dataclass(frozen=True, slots=True)
class TransactionRetryPolicy:
    """Bounded retry settings for serializable transactions."""

    maximum_attempts: int = 4
    initial_backoff_seconds: float = 0.05
    maximum_backoff_seconds: float = 1.0

    def __post_init__(self) -> None:
        if not 1 <= self.maximum_attempts <= _MAX_ATTEMPTS_LIMIT:
            raise ValueError(
                f"maximum_attempts must be between 1 and {_MAX_ATTEMPTS_LIMIT}"
            )
        if self.initial_backoff_seconds < 0:
            raise ValueError("initial_backoff_seconds must not be negative")
        if self.maximum_backoff_seconds < self.initial_backoff_seconds:
            raise ValueError(
                "maximum_backoff_seconds must not be less than initial_backoff_seconds"
            )


@dataclass(frozen=True, slots=True)
class TransactionRetryHooks:
    """Injectable retry side effects for telemetry and deterministic tests."""

    retry_observer: RetryObserver | None = None
    sleep_fn: Sleep = sleep
    jitter_fn: Jitter = _full_jitter


@dataclass(frozen=True, slots=True)
class TransactionRetry:
    """Sanitized evidence emitted before one serialization retry."""

    failed_attempt: int
    maximum_attempts: int
    sqlstate: str
    delay_seconds: float


@dataclass(frozen=True, slots=True)
class TransactionRun[T]:
    """Successful transaction value and the number of attempts used."""

    value: T
    attempts: int


class TransactionExecutionError(RuntimeError):
    """Sanitized database failure safe for application-level reporting."""

    def __init__(
        self,
        *,
        sqlstate: str | None,
        attempts: int,
        retryable: bool,
    ) -> None:
        super().__init__("database transaction failed")
        self.sqlstate = sqlstate
        self.attempts = attempts
        self.retryable = retryable


class CockroachTransactionRunner:
    """Run one unit of work in a bounded serializable transaction.

    A new connection and transaction are created for every retry. Only
    CockroachDB serialization failures (SQLSTATE 40001) are retried. Other
    database failures are surfaced immediately through a sanitized exception.
    """

    def __init__(
        self,
        engine: Engine,
        *,
        policy: TransactionRetryPolicy | None = None,
        hooks: TransactionRetryHooks | None = None,
    ) -> None:
        self._engine = engine
        self._policy = policy or TransactionRetryPolicy()
        self._hooks = hooks or TransactionRetryHooks()

    def run(self, work: TransactionWork[T]) -> TransactionRun[T]:
        """Execute ``work`` atomically, retrying serialization conflicts."""
        for attempt in range(1, self._policy.maximum_attempts + 1):
            try:
                with self._engine.connect() as raw_connection:
                    connection = raw_connection.execution_options(
                        isolation_level="SERIALIZABLE"
                    )
                    with connection.begin():
                        value = work(connection)
                return TransactionRun(value=value, attempts=attempt)
            except DBAPIError as error:
                sqlstate = _safe_sqlstate(error)
                retryable = sqlstate == _SERIALIZATION_FAILURE_SQLSTATE
                if not retryable or attempt == self._policy.maximum_attempts:
                    raise TransactionExecutionError(
                        sqlstate=sqlstate,
                        attempts=attempt,
                        retryable=retryable,
                    ) from None

                delay = self._retry_delay(failed_attempt=attempt)
                retry = TransactionRetry(
                    failed_attempt=attempt,
                    maximum_attempts=self._policy.maximum_attempts,
                    sqlstate=_SERIALIZATION_FAILURE_SQLSTATE,
                    delay_seconds=delay,
                )
                if self._hooks.retry_observer is not None:
                    self._hooks.retry_observer(retry)
                self._hooks.sleep_fn(delay)

        raise AssertionError("transaction attempt loop did not return or raise")

    def _retry_delay(self, *, failed_attempt: int) -> float:
        cap = min(
            self._policy.initial_backoff_seconds * (2 ** (failed_attempt - 1)),
            self._policy.maximum_backoff_seconds,
        )
        delay = self._hooks.jitter_fn(cap)
        if not 0 <= delay <= cap:
            raise ValueError("jitter_fn must return a value between zero and its cap")
        return delay


def _safe_sqlstate(error: DBAPIError) -> str | None:
    original = error.orig
    candidate = getattr(original, "sqlstate", None)
    if candidate is None:
        candidate = getattr(original, "pgcode", None)
    if not isinstance(candidate, str):
        return None
    normalized = candidate.strip().upper()
    if len(normalized) != _SQLSTATE_LENGTH or not normalized.isalnum():
        return None
    return normalized
