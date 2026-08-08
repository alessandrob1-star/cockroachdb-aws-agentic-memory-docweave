# CockroachDB Operation Persistence

**Status:** Current dashboard approval path  
**Last updated:** 2026-08-08

DocWeave keeps file mutation authority with the human reviewer.

When a proposal is approved, the dashboard:

1. validates the planned move/rename inside the authorized root;
2. executes the file operation;
3. records the human decision in `docweave.human_decisions`;
4. records before/after path memory in `docweave.file_history`;
5. updates `docweave.documents.current_directory`,
   `docweave.documents.current_filename`, and status.

The user can select a moved PDF in the dashboard and immediately see:

- original directory;
- original filename;
- current directory;
- current filename;
- approval/move status.

This is the only file-operation persistence story used for the current
hackathon demo.
