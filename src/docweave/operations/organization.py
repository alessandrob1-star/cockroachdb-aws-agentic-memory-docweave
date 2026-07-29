"""Safe deterministic organization proposals for reviewed documents.

This module deliberately does not generate semantic names. It prepares a
transparent, deterministic copy plan from an existing classification proposal
so the user can inspect a safe destination before any future approval or file
mutation step.
"""

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
            _safe_pdf_filename(source.name),
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
