"""Approved initial taxonomy used by contracts and CockroachDB seed commands."""

from dataclasses import dataclass
from enum import StrEnum

TAXONOMY_VERSION = "docweave_mvp_v0_1"


class TaxonomyClass(StrEnum):
    """Stable class codes in the approved initial taxonomy."""

    ACCEPTANCE_DOCUMENT = "acceptance_document"
    BANK_CERTIFICATION = "bank_certification"
    BANK_STATEMENT = "bank_statement"
    CONTRACT = "contract"
    INVOICE = "invoice"
    OTHER = "other"
    PAYMENT_NOTICE = "payment_notice"
    PURCHASE_ORDER = "purchase_order"
    SUPPLIER_RECEIPT = "supplier_receipt"
    TECHNICAL_ATTACHMENT = "technical_attachment"
    TENDER_DOCUMENT = "tender_document"
    UNCLASSIFIED = "unclassified"


@dataclass(frozen=True, slots=True)
class TaxonomyDefinition:
    """One approved, versioned taxonomy class definition."""

    class_code: TaxonomyClass
    display_name: str
    definition: str
    expected_evidence: str
    is_abstention: bool = False


TAXONOMY_DEFINITIONS = (
    TaxonomyDefinition(
        TaxonomyClass.INVOICE,
        "Invoice",
        "Supplier charge linked to an order, contract, or project.",
        "Invoice number, taxable amount, tax, total, or due date.",
    ),
    TaxonomyDefinition(
        TaxonomyClass.CONTRACT,
        "Contract",
        "Agreement governing commercial terms and obligations.",
        "Parties, obligations, signatures, or effective dates.",
    ),
    TaxonomyDefinition(
        TaxonomyClass.PURCHASE_ORDER,
        "Purchase Order",
        "Authorized order linked to a supplier and contract.",
        "Order number, buyer, supplier, or ordered items.",
    ),
    TaxonomyDefinition(
        TaxonomyClass.TENDER_DOCUMENT,
        "Tender Document",
        "Procurement, bid, proposal, quotation, or tender material.",
        "Tender identifier, proposal, deadline, eligibility, or scope.",
    ),
    TaxonomyDefinition(
        TaxonomyClass.PAYMENT_NOTICE,
        "Payment Notice",
        "Evidence that an invoice entered a payment workflow.",
        "Invoice reference, payment status, or due or scheduled date.",
    ),
    TaxonomyDefinition(
        TaxonomyClass.BANK_CERTIFICATION,
        "Bank Certification",
        "Bank-originated evidence supporting payment.",
        "Bank issuer, certified reference, amount, account, or transaction.",
    ),
    TaxonomyDefinition(
        TaxonomyClass.SUPPLIER_RECEIPT,
        "Supplier Receipt",
        "Supplier acknowledgement or payment receipt.",
        "Supplier acknowledgement, amount, invoice, or payment reference.",
    ),
    TaxonomyDefinition(
        TaxonomyClass.BANK_STATEMENT,
        "Bank Statement",
        "Statement containing one or more payment references.",
        "Statement period, transaction rows, payment references, or account.",
    ),
    TaxonomyDefinition(
        TaxonomyClass.ACCEPTANCE_DOCUMENT,
        "Acceptance Document",
        "Evidence that goods, work, or services were accepted.",
        "Acceptance statement, received items or services, approver, or date.",
    ),
    TaxonomyDefinition(
        TaxonomyClass.TECHNICAL_ATTACHMENT,
        "Technical Attachment",
        "Material, asset, plant, measurement, or delivery detail.",
        "Technical specification, asset, material, measurement, or delivery.",
    ),
    TaxonomyDefinition(
        TaxonomyClass.OTHER,
        "Other",
        "Supported document for which no configured primary class applies.",
        "Sufficient content to exclude the configured primary classes.",
    ),
    TaxonomyDefinition(
        TaxonomyClass.UNCLASSIFIED,
        "Unclassified",
        "Insufficient, conflicting, unreadable, suspicious, or unsupported evidence.",
        "Explicit evidence limitation or unresolved contradiction.",
        is_abstention=True,
    ),
)
