# Initial synthetic PDF corpus

The `pdf_sintetici` directory contains 100 entirely synthetic PDF documents for
DocWeave desktop discovery, preview, analysis, rename, review, and restore
tests.

The initial 30-file seed corpus contains:

- 8 purchase orders;
- 8 supplier invoices;
- 7 payment confirmations; and
- 7 delivery notes.

Six dossiers contain a complete purchase-order, delivery-note, invoice, and
payment chain. The remaining records intentionally include incomplete and
missing references. Every person, organization, address, identifier, amount,
and transaction is fictional. No ProtoMaster data or private source document
was used.

The additional 70 PDFs expand the folder so the dashboard behaves like a real
cleanup task rather than a tiny fixture. Their names are still intentionally
opaque: `attachment_081.pdf`, `batch_a_071.pdf`, `file_10290.pdf`,
`scan_009314.pdf`, and similar. The names should not reveal the class or
business entity.

Each PDF has two pages, an explicit synthetic-data banner, expected reference
fields, and one HTTPS annotation targeting `example.com`. The annotation is
present to test DocWeave's guarded external-link workflow; it is not evidence
of a real vendor portal.

Filenames are intentionally neutral, inconsistent, and category-free. Expected
categories and business identifiers appear only inside the PDFs and in the
separate reference manifest. This prevents discovery and later classification
evaluations from succeeding merely by reading a descriptive filename.

`initial-corpus-manifest.json` records category, document and dossier
identifiers, relationships, page count, SHA-256 digest, and provenance.
Expected labels are deterministic reference data and must never be presented
as model-generated analysis.

`pdf-corpus-manifest.json` records the current 100-file public demo corpus:
filename, extracted document identifier, page count, digest, and synthetic-data
flag. It is a corpus inventory, not model output.

These files do not demonstrate Amazon Bedrock analysis, CockroachDB
persistence, antivirus scanning, or production readiness.
