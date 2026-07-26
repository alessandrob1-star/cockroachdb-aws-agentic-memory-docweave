"""Deterministic evidence segments derived from extracted page text."""

from dataclasses import dataclass

from docweave.extraction import ExtractedPage

MAXIMUM_EVIDENCE_SEGMENT_CHARACTERS = 800
MAXIMUM_EVIDENCE_SEGMENTS = 2_000


@dataclass(frozen=True, slots=True)
class EvidenceSegment:
    """One exact contiguous source span selectable by stable identifier."""

    segment_id: str
    page_index: int
    page_label: str
    text: str


def build_evidence_segments(
    pages: tuple[ExtractedPage, ...],
) -> tuple[EvidenceSegment, ...]:
    """Split nonblank page lines into bounded exact source spans."""
    segments: list[EvidenceSegment] = []
    for page in pages:
        page_sequence = 0
        for line in page.text.splitlines():
            remaining = line.strip()
            while remaining:
                chunk, remaining = _take_chunk(remaining)
                page_sequence += 1
                segments.append(
                    EvidenceSegment(
                        segment_id=f"p{page.page_index}_s{page_sequence}",
                        page_index=page.page_index,
                        page_label=page.page_label,
                        text=chunk,
                    )
                )
                if len(segments) > MAXIMUM_EVIDENCE_SEGMENTS:
                    raise ValueError("Evidence segment limit exceeded.")
    return tuple(segments)


def _take_chunk(value: str) -> tuple[str, str]:
    if len(value) <= MAXIMUM_EVIDENCE_SEGMENT_CHARACTERS:
        return value, ""
    limit = MAXIMUM_EVIDENCE_SEGMENT_CHARACTERS
    split_at = value.rfind(" ", 0, limit + 1)
    if split_at <= 0:
        split_at = limit
    chunk = value[:split_at].rstrip()
    remaining = value[split_at:].lstrip()
    return chunk, remaining
