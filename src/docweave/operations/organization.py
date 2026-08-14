"""Safe deterministic organization proposals for reviewed documents.

This module deliberately does not generate semantic names. It prepares a
transparent, deterministic copy plan from an existing classification proposal
so the user can inspect a safe destination before any future approval or file
mutation step.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from unicodedata import normalize

from docweave.analysis.taxonomy import TaxonomyClass
from docweave.core.paths import relative_posix_path
from docweave.operations.approval import operation_plan_fingerprint
from docweave.operations.planning import (
    FileOperation,
    FileOperationPlan,
    FileOperationRequest,
    plan_file_operation,
)

ORGANIZED_ROOT_FOLDER = "DocWeave Organized"
MAX_METADATA_FILENAME_PARTS = 4

_CLASS_DESTINATION_FOLDERS = {
    TaxonomyClass.ACCEPTANCE_DOCUMENT: "Acceptance Documents",
    TaxonomyClass.BANK_CERTIFICATION: "Bank Certifications",
    TaxonomyClass.BANK_STATEMENT: "Bank Statements",
    TaxonomyClass.CONTRACT: "Contracts",
    TaxonomyClass.INVOICE: "Invoices",
    TaxonomyClass.OTHER: "Other",
    TaxonomyClass.PAYMENT_NOTICE: "Payment Notices",
    TaxonomyClass.PURCHASE_ORDER: "Purchase Orders",
    TaxonomyClass.SUPPLIER_RECEIPT: "Supplier Receipts",
    TaxonomyClass.TECHNICAL_ATTACHMENT: "Technical Attachments",
    TaxonomyClass.TENDER_DOCUMENT: "Tender Documents",
    TaxonomyClass.UNCLASSIFIED: "Unclassified",
}

_WINDOWS_FORBIDDEN_FILENAME_CHARS = frozenset('<>:"/\\|?*')
_CLASS_FILENAME_PREFIXES = {
    TaxonomyClass.ACCEPTANCE_DOCUMENT: "acceptance",
    TaxonomyClass.BANK_CERTIFICATION: "bank-certification",
    TaxonomyClass.BANK_STATEMENT: "bank-statement",
    TaxonomyClass.CONTRACT: "contract",
    TaxonomyClass.INVOICE: "invoice",
    TaxonomyClass.OTHER: "document",
    TaxonomyClass.PAYMENT_NOTICE: "payment-notice",
    TaxonomyClass.PURCHASE_ORDER: "purchase-order",
    TaxonomyClass.SUPPLIER_RECEIPT: "supplier-receipt",
    TaxonomyClass.TECHNICAL_ATTACHMENT: "technical-attachment",
    TaxonomyClass.TENDER_DOCUMENT: "tender-document",
    TaxonomyClass.UNCLASSIFIED: "unclassified",
}
_FILENAME_METADATA_PRIORITY = (
    "supplier",
    "vendor",
    "issuer",
    "counterparty",
    "invoice_number",
    "invoice_id",
    "order_number",
    "purchase_order_number",
    "contract_number",
    "payment_reference",
    "document_id",
    "document_number",
    "document_reference",
    "reference",
    "issue_date",
    "date",
    "due_date",
)


@dataclass(frozen=True, slots=True)
class OrganizationProposal:
    """A non-mutating organization proposal bound to one exact operation plan."""

    source_relative_path: str
    proposed_class: TaxonomyClass
    destination_relative_path: str
    plan: FileOperationPlan
    plan_fingerprint: str

    @property
    def is_ready(self) -> bool:
        return self.plan.is_ready


def propose_safe_organization_copy(
    *,
    source_path: Path,
    authorized_root: Path,
    proposed_class: str | TaxonomyClass,
    metadata: Mapping[str, str] | None = None,
) -> OrganizationProposal:
    """Build a deterministic copy proposal without mutating the filesystem."""
    root = authorized_root.resolve(strict=True)
    source = source_path.resolve(strict=True)
    source_relative_path = relative_posix_path(source, root)
    taxonomy_class = _taxonomy_class(proposed_class)
    destination_relative_path = "/".join(
        (
            ORGANIZED_ROOT_FOLDER,
            _CLASS_DESTINATION_FOLDERS[taxonomy_class],
            _proposal_filename(
                taxonomy_class=taxonomy_class,
                source_filename=source.name,
                metadata={} if metadata is None else metadata,
            ),
        )
    )
    plan = plan_file_operation(
        FileOperationRequest(
            operation=FileOperation.COPY,
            source_root=root,
            source_relative_path=source_relative_path,
            destination_root=root,
            destination_relative_path=destination_relative_path,
        )
    )
    return OrganizationProposal(
        source_relative_path=source_relative_path,
        proposed_class=taxonomy_class,
        destination_relative_path=destination_relative_path,
        plan=plan,
        plan_fingerprint=operation_plan_fingerprint(plan),
    )


def _taxonomy_class(value: str | TaxonomyClass) -> TaxonomyClass:
    if isinstance(value, TaxonomyClass):
        return value
    try:
        return TaxonomyClass(value)
    except ValueError:
        return TaxonomyClass.UNCLASSIFIED


def _safe_pdf_filename(filename: str) -> str:
    normalized = normalize("NFKC", filename)
    cleaned = "".join(
        "_" if character in _WINDOWS_FORBIDDEN_FILENAME_CHARS else character
        for character in normalized
        if character.isprintable()
    )
    cleaned = " ".join(cleaned.split()).strip(" .")
    if cleaned == "":
        cleaned = "document.pdf"
    path = Path(cleaned)
    suffix = ".pdf"
    stem = path.stem.strip(" .") or "document"
    if path.suffix.casefold() != suffix:
        stem = cleaned.strip(" .")
    stem = stem[:96].strip(" .") or "document"
    if stem.upper() in {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"}:
        stem = f"{stem}_document"
    return f"{stem}{suffix}"


def _proposal_filename(
    *,
    taxonomy_class: TaxonomyClass,
    source_filename: str,
    metadata: Mapping[str, str],
) -> str:
    metadata_parts = _metadata_filename_parts(metadata)
    if not metadata_parts:
        return _safe_pdf_filename(source_filename)
    stem = "_".join((_CLASS_FILENAME_PREFIXES[taxonomy_class], *metadata_parts))
    return _safe_pdf_filename(f"{stem}.pdf")


def _metadata_filename_parts(metadata: Mapping[str, str]) -> tuple[str, ...]:
    normalized_metadata = {
        _metadata_key(key): value for key, value in metadata.items() if value.strip()
    }
    parts: list[str] = []
    for key in _FILENAME_METADATA_PRIORITY:
        value = normalized_metadata.get(key)
        if value is None:
            continue
        safe_part = _safe_filename_part(value)
        if safe_part and safe_part not in parts:
            parts.append(safe_part)
        if len(parts) >= MAX_METADATA_FILENAME_PARTS:
            break
    return tuple(parts)


def _metadata_key(value: str) -> str:
    return "_".join(value.strip().casefold().replace("-", "_").split())


def _safe_filename_part(value: str) -> str:
    filename = _safe_pdf_filename(value)
    return Path(filename).stem.casefold().replace(" ", "-")[:40].strip("-_ .")
