from pathlib import Path

from docweave.analysis.taxonomy import TaxonomyClass
from docweave.operations import (
    ORGANIZED_ROOT_FOLDER,
    FileOperation,
    FileOperationStatus,
    propose_safe_organization_copy,
)


def write_file(path: Path, content: bytes = b"%PDF-1.7\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def test_proposes_class_folder_copy_without_mutating_files(tmp_path: Path) -> None:
    source = tmp_path / "incoming" / "received_file_003.pdf"
    write_file(source)

    proposal = propose_safe_organization_copy(
        source_path=source,
        authorized_root=tmp_path,
        proposed_class=TaxonomyClass.INVOICE,
    )

    assert proposal.source_relative_path == "incoming/received_file_003.pdf"
    assert proposal.proposed_class is TaxonomyClass.INVOICE
    assert proposal.destination_relative_path == (
        f"{ORGANIZED_ROOT_FOLDER}/Invoices/received_file_003.pdf"
    )
    assert proposal.plan.operation is FileOperation.COPY
    assert proposal.plan.status is FileOperationStatus.READY
    assert proposal.plan.destination_path == (
        tmp_path / ORGANIZED_ROOT_FOLDER / "Invoices" / "received_file_003.pdf"
    ).resolve(strict=False)
    assert proposal.plan_fingerprint
    assert not (tmp_path / ORGANIZED_ROOT_FOLDER).exists()


def test_unknown_class_is_disclosed_as_unclassified(tmp_path: Path) -> None:
    source = tmp_path / "scan.pdf"
    write_file(source)

    proposal = propose_safe_organization_copy(
        source_path=source,
        authorized_root=tmp_path,
        proposed_class="../../evil",
    )

    assert proposal.proposed_class is TaxonomyClass.UNCLASSIFIED
    assert proposal.destination_relative_path == (
        f"{ORGANIZED_ROOT_FOLDER}/Unclassified/scan.pdf"
    )
    assert proposal.plan.is_ready


def test_uses_validated_metadata_for_more_meaningful_filename(
    tmp_path: Path,
) -> None:
    source = tmp_path / "received_file_003.pdf"
    write_file(source)

    proposal = propose_safe_organization_copy(
        source_path=source,
        authorized_root=tmp_path,
        proposed_class="invoice",
        metadata={
            "supplier": "ACME SRL",
            "invoice_number": "INV-2026-004",
            "ignored_field": "not used",
        },
    )

    assert proposal.destination_relative_path == (
        f"{ORGANIZED_ROOT_FOLDER}/Invoices/invoice_acme-srl_inv-2026-004.pdf"
    )
    assert proposal.plan.is_ready


def test_sanitizes_dangerous_pdf_filename(tmp_path: Path) -> None:
    source = tmp_path / "invoice:ACME*Q1?.pdf"
    write_file(source)

    proposal = propose_safe_organization_copy(
        source_path=source,
        authorized_root=tmp_path,
        proposed_class="invoice",
    )

    assert proposal.destination_relative_path == (
        f"{ORGANIZED_ROOT_FOLDER}/Invoices/invoice_ACME_Q1_.pdf"
    )
    assert proposal.plan.is_ready


def test_blocks_source_outside_authorized_root(tmp_path: Path) -> None:
    authorized_root = tmp_path / "authorized"
    outside_root = tmp_path / "outside"
    authorized_root.mkdir()
    source = outside_root / "invoice.pdf"
    write_file(source)

    try:
        propose_safe_organization_copy(
            source_path=source,
            authorized_root=authorized_root,
            proposed_class="invoice",
        )
    except ValueError:
        pass
    else:
        raise AssertionError("outside source must be blocked")
