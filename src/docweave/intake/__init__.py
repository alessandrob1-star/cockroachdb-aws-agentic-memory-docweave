"""Deterministic intake records built from local inspection steps."""

from docweave.intake.records import (
    DuplicateGroup,
    IntakeProgressCallback,
    IntakeRecord,
    IntakeResult,
    IntakeStatus,
    build_intake_records,
)

__all__ = [
    "DuplicateGroup",
    "IntakeProgressCallback",
    "IntakeRecord",
    "IntakeResult",
    "IntakeStatus",
    "build_intake_records",
]
