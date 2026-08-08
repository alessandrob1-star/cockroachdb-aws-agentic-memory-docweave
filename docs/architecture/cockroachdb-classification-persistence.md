# CockroachDB Classification Persistence

**Status:** Current hackathon path  
**Last updated:** 2026-08-08

One Analyze action writes:

1. `docweave.documents` - the PDF identity, original path, current path, digest,
   page count, and status.
2. `docweave.agent_runs` - the Amazon Bedrock provider, model, task, input hash,
   validated output JSON, and summary.
3. `docweave.proposals` - the non-authoritative class, proposed folder,
   proposed filename, confidence signal, and evidence summary.

The write path is implemented in
`src/docweave/persistence/simple_memory_repository.py`.

The proposal remains non-authoritative until a human records a decision.
Filename and folder changes happen only after approval.
