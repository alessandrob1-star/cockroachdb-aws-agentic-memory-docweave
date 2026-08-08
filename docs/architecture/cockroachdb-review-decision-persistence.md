# CockroachDB Human Decision Memory

**Status:** Current hackathon path
**Last updated:** 2026-08-08

The dashboard never treats an LLM proposal as final by itself.

When a reviewer approves or rejects a proposal, DocWeave writes one row to
`docweave.human_decisions`. If the approval also moves or renames a file, it
writes the before and after path to `docweave.file_history` and updates the
current path on `docweave.documents`.

This gives the demo a simple explanation:

1. `proposals` records what the model suggested.
2. `human_decisions` records what the human accepted or rejected.
3. `file_history` records what changed on disk.
4. `documents` keeps both the original path and the current path easy to read.

The review command and cockpit use the same simple memory repository:
`src/docweave/persistence/simple_memory_repository.py`.
