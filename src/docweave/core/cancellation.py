"""Cooperative cancellation contracts for bounded local work."""

from collections.abc import Callable

CancellationCheck = Callable[[], bool]


class CancellationRequestedError(RuntimeError):
    """Signal an expected, user-requested stop without exposing private data."""


def raise_if_cancelled(cancellation_check: CancellationCheck | None) -> None:
    """Stop at a safe cooperative boundary when cancellation was requested."""
    if cancellation_check is not None and cancellation_check():
        raise CancellationRequestedError
