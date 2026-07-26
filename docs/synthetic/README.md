# Initial synthetic PDF corpus

The `pdf_sintetici` directory contains 30 entirely synthetic PDF documents for
DocWeave desktop discovery, table, preview, hyperlink, and later relationship
tests.

The corpus contains:

- 8 purchase orders;
- 8 supplier invoices;
- 7 payment confirmations; and
- 7 delivery notes.

Six dossiers contain a complete purchase-order, delivery-note, invoice, and
payment chain. The remaining records intentionally include incomplete and
missing references. Every person, organization, address, identifier, amount,
and transaction is fictional. No ProtoMaster data or private source document
was used.

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

These files do not demonstrate Amazon Bedrock analysis, CockroachDB
persistence, antivirus scanning, or production readiness.
