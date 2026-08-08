"""Tiny shared persistence contracts for the simple DocWeave memory schema."""

from __future__ import annotations

from enum import StrEnum


class PersistenceDisposition(StrEnum):
    """Outcome of an idempotent memory write."""

    APPLIED = "applied"
    IDEMPOTENT_REPLAY = "idempotent_replay"
