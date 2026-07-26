# DocWeave User Workflows

**Version:** 0.1
**Baseline approved:** 2026-07-21
**Implementation status:** In progress; desktop folder authorization,
progressive discovery status, cancellation, and in-memory selection implemented

## 1. Interaction model

DocWeave presents the same product concepts across a PySide6 desktop client and
a complete cloud application. The desktop client operates on explicitly
authorized local folders. The cloud application operates on a real cloud-backed
workspace. Both use the same production agent workflows, CockroachDB memory,
review rules, and activity history.

The normal user never needs direct database access, cloud-console access, or
command-line knowledge.

## 2. Primary navigation

The approved conceptual navigation contains:

- **Workspaces** — create or resume a document project;
- **Documents** — browse, preview, search, sort, and filter documents;
- **Review Queue** — prioritize uncertain or policy-selected results;
- **Batches** — inspect progress, failures, approval, and completion;
- **Relationships** — navigate linked documents with evidence;
- **Activity History** — understand who or what changed each item;
- **Settings** — manage taxonomy, limits, review policy, and members according
  to role.

Labels may change after user-experience testing, but these capabilities may not
disappear without an approved requirement change.

## 3. Workflow A — create or resume a workspace

1. The user signs in and selects an existing workspace or chooses **New
   workspace**.
2. DocWeave explains the workspace boundary and the storage mode.
3. On desktop, the user authorizes one or more local roots. In cloud, the user
   selects or creates a cloud document workspace.
4. DocWeave displays existing progress if the source was scanned previously.
5. The user chooses **Resume** or requests a fresh comparison scan.

Expected result: the user sees prior work and current source state without
losing checkpoints or reprocessing completed documents.

## 4. Workflow B — discover a large folder safely

1. The user selects **Scan documents**.
2. DocWeave progressively inventories the source and shows discovered counts.
3. Each file is matched against persistent identity and prior processing state.
4. The summary separates new, unchanged, changed, moved, missing, unsupported,
   unreadable, and duplicate candidates.
5. DocWeave proposes bounded batches of no more than the configured limit.
6. The user confirms which documents should enter analysis.

Expected result: a 10,000-file source can be inventoried while the user
interface remains responsive, and already completed documents are not silently
submitted again.

## 5. Workflow C — analyze and prepare proposals

1. The user starts an approved batch.
2. DocWeave extracts usable content and records extraction quality.
3. Specialized agents analyze classification, naming, destination, and document
   relationships.
4. Verification controls check structure, authorization, consistency, and
   conflicts.
5. Results are checkpointed per document.
6. Each proposal records confidence, explanation, evidence, model provenance,
   and status.
7. The user may leave the application and resume later.

Expected result: completion, failure, and interruption are explicit for every
document; no unfinished file is presented as successfully analyzed.

## 6. Workflow D — review by confidence

1. The user opens **Review Queue**.
2. The default view prioritizes low calibrated confidence and errors.
3. The user may sort either direction and filter by category, batch, user,
   status, date, confidence band, or operation.
4. Selecting a row opens the PDF preview beside the proposal and evidence.
5. The user approves, rejects, edits, or defers the proposal.
6. A correction records both the agent proposal and human final value.
7. The system preserves the feedback with provenance for controlled future use.

Expected result: a non-technical reviewer can understand what is uncertain,
why it is uncertain, and what action is available.

## 7. Workflow E — high-confidence quality sampling

1. The reviewer selects **Quality sample**.
2. DocWeave creates a reproducible random or policy-based sample from
   high-confidence results.
3. The reviewer marks each sampled result correct or incorrect.
4. DocWeave reports the observed error rate and possible confidence-calibration
   concern.
5. A concerning result blocks or escalates the batch according to policy.

Expected result: systemic overconfidence can be detected even when low-score
items look correct.

## 8. Workflow F — preview and approve an operation batch

1. The user chooses copy mode or move mode.
2. DocWeave displays a before-and-after table for every proposed action.
3. The summary identifies new folders, collisions, invalid names, files changed
   since analysis, warnings, estimated time, and estimated cloud cost.
4. The user removes, edits, or defers individual rows.
5. The authorization policy determines whether the operator may approve or a
   separate reviewer is required.
6. The approving user confirms the exact bounded plan.

Expected result: the approved plan is specific, understandable, and immutable;
later source-state changes trigger revalidation rather than silent execution.

## 9. Workflow G — execute copy or move operations

1. DocWeave revalidates identity, source state, destination, permissions, and
   authorization immediately before each action.
2. The operation is executed once using a unique execution identity.
3. The resulting file is verified.
4. Persistent state and audit history record intended and actual outcomes.
5. Failures stop or isolate only the affected items according to policy.
6. Progress is checkpointed and can resume after interruption.

Expected result: every file has an unambiguous status, and retrying does not
create duplicate copies or repeat completed moves.

## 10. Workflow H — inspect and restore one file

1. The user opens a document from Documents or Activity History.
2. The timeline displays discovered state and every proposal, correction,
   operation, and restore.
3. The user chooses **Restore previous state** or **Restore original state**.
4. DocWeave previews the exact effect and checks for missing folders,
   collisions, external changes, and authorization.
5. Missing authorized directories may be recreated as part of the approved
   restore.
6. For a move, the file returns to the selected prior location. For a copy, the
   original remains and the DocWeave-created copy moves to recoverable trash
   where supported.
7. The restore is appended to history.

Expected result: one questionable item can be corrected without disturbing the
remaining batch or erasing evidence of what happened.

## 11. Workflow I — restore a selection or batch

1. A reviewer selects documents or a completed batch.
2. DocWeave produces a restore preview and conflict report.
3. Conflicted files are isolated for individual decisions; unrelated safe
   restores remain independently actionable.
4. A reviewer explicitly approves the bounded restore plan.
5. DocWeave executes, verifies, checkpoints, and reports per-file results.

Expected result: a poor bulk decision can be reversed safely without treating
partial failures as complete success.

## 12. Workflow J — project-manager oversight

1. The project manager opens **Activity History** or a team dashboard.
2. Filters identify work by operator, reviewer, agent, batch, status, date, or
   action type.
3. The manager inspects proposals, confidence, corrections, approvals, errors,
   and restores.
4. According to policy, the manager may request correction, approve pending
   work, or initiate a restore.

Expected result: responsibility and outcome are visible without reading logs or
querying CockroachDB directly.

## 13. Required empty, loading, and failure states

Every primary view shall intentionally handle:

- no workspace or no documents;
- active scan or analysis;
- paused or cancelled work;
- partial batch completion;
- unavailable network or cloud service;
- expired authentication;
- unreadable or unsupported file;
- naming or destination collision;
- stale proposal caused by an external file change;
- insufficient permission;
- failed restore;
- service cost or usage limit reached.

Each state explains what happened, whether data is safe, and the next permitted
action. A silent spinner or fabricated success message is not acceptable.

## 14. Usability validation

The workflows shall be tested with representative non-technical users. A
successful moderated session requires a participant to complete scanning,
low-confidence review, approval, Activity History inspection, and an
individual restore without database or command-line assistance.
