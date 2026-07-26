"""Approved initial taxonomy identifiers used by classification contracts."""

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
