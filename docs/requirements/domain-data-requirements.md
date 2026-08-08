# Domain and Data Requirements

**Project:** DocWeave  
**Last updated:** 2026-08-08  
**Status:** Focused hackathon scope

## Purpose

DocWeave organizes messy PDF folders with agentic memory. The current
hackathon product stores the memory needed to explain one complete workflow:

```text
PDF -> Bedrock analysis -> proposal -> human decision -> file path history
```

## Document Classes

The current taxonomy is `docweave_mvp_v0_1`:

| Code | Meaning |
| --- | --- |
| `invoice` | Supplier invoice |
| `contract` | Contract or agreement |
| `purchase_order` | Purchase order |
| `tender_document` | Tender, bid, quotation, or procurement document |
| `payment_notice` | Payment workflow evidence |
| `bank_certification` | Bank-originated payment evidence |
| `supplier_receipt` | Supplier acknowledgement or receipt |
| `bank_statement` | Bank statement |
| `acceptance_document` | Acceptance of work, goods, or services |
| `technical_attachment` | Technical or delivery attachment |
| `other` | Supported document outside configured primary classes |
| `unclassified` | Insufficient or unsafe evidence |

## Required Data

The current physical schema is intentionally small:

| Table | Required data |
| --- | --- |
| `documents` | Original directory/name, current directory/name, digest, page count, status. |
| `agent_runs` | Provider, model, task, timestamps, input hash, validated output JSON, summary. |
| `proposals` | Proposed category, directory, filename, confidence, evidence summary, status. |
| `human_decisions` | Human actor label, decision, reason, timestamp. |
| `file_history` | Previous directory/name, next directory/name, operation, status, timestamp. |
| `document_relationships` | Optional source, target, type, confidence, evidence summary. |

## Rules

- A model proposal is not a file action.
- File moves and renames require explicit human approval.
- Original filenames and original directories must remain queryable after a
  file is moved.
- Raw private company data must not be committed.
- Synthetic data may imitate document shapes, not real private identifiers or
  records.
- JSON may store bounded model output, but the demo facts must be visible in
  typed relational columns.

## Deferred

The current demo does not require broad workspace administration, vector
retrieval, a large canonical business-entity model, or a 300-PDF evaluation
corpus. Those are future-product items, not required for the focused
submission loop.
