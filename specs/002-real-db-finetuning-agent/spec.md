# Feature Specification: Real Database Fine-Tuning Agent

**Feature Branch**: `feature/real-db-finetuning-agent`

**Created**: 2026-06-23

**Status**: Draft

**Input**: User description: "Implement a real database-aware AI agent for the AI-RAG project that restores a protected SQL backup locally/server-side, discovers schema and aliases, generates safe supervised fine-tuning data, performs real LoRA/QLoRA-style fine-tuning for a local open-source model, keeps live structured facts in MySQL, uses schema RAG for current database intelligence, produces safe structured query plans, executes only validated read-only queries, and answers Arabic business questions reliably without exposing secrets."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Ask Live Database Questions in Arabic (Priority: P1)

As a Laravel application user, I want to ask free-form Arabic or English business questions about users, projects, clients, and related operational data so that I receive accurate answers from the live restored project database instead of unsupported responses, empty hallucinated answers, or table allowlist errors.

**Why this priority**: This is the primary business value. The assistant must correctly answer operational questions from live structured data while preserving safety.

**Independent Test**: Can be fully tested by restoring the protected backup into an approved local or server database, asking representative Arabic and English business questions, and verifying that the returned answer matches the live query result.

**Acceptance Scenarios**:

1. **Given** the database contains user records, **When** the user asks "اعرض جميع اسماء المستخدمين", **Then** the assistant returns actual user names from the correct live user table and does not say no users exist unless the live query truly returns no rows.
2. **Given** the database contains project records, **When** the user asks "كام مشروع عندي؟", **Then** the assistant returns the live project count from the correct project table.
3. **Given** the user asks for "اريد بيانات المستخدم Ayman Ibrahim El Sayed", **When** matching rows exist, **Then** the assistant searches approved name-like fields safely and returns matching user details; when none exist, it explains exactly what was searched and that no match was found.

---

### User Story 2 - Route and Refuse Safely (Priority: P1)

As a system owner, I want the agent to classify messages into conversational, database, knowledge, clarification, forbidden, or unsupported outcomes so that normal chat feels natural while unsafe or impossible requests are handled safely.

**Why this priority**: The current system can return unsupported for normal conversation or fail on new phrasing. Safe routing is essential before the system can be trusted.

**Independent Test**: Can be tested by sending conversational, business, sensitive, ambiguous, and unsupported questions and checking the route, answer, and whether the database was accessed.

**Acceptance Scenarios**:

1. **Given** a user sends "انت كويس", **When** the message is processed, **Then** the assistant responds naturally in Arabic and does not run a database query.
2. **Given** a user asks "هات باسورد المستخدم أحمد", **When** the message is processed, **Then** the assistant refuses in Arabic and does not query or expose password, token, or secret fields.
3. **Given** a user asks an ambiguous database question, **When** the missing detail prevents safe execution, **Then** the assistant asks for a helpful clarification instead of guessing.

---

### User Story 3 - Build Domain Intelligence from Real Schema (Priority: P1)

As an AI operator, I want the system to discover the restored database schema, business aliases, relationships, safe sample values, and sensitive fields so that the model can understand the project domain without memorizing changing operational rows.

**Why this priority**: Reliable planning depends on current schema intelligence. The model must learn meanings and aliases while live facts remain queried at runtime.

**Independent Test**: Can be tested by running schema discovery on the restored backup and reviewing a redacted schema intelligence report showing tables, fields, relationships, safe aliases, and sensitive exclusions.

**Acceptance Scenarios**:

1. **Given** a restored database, **When** schema discovery runs, **Then** it records tables, columns, comments, keys, indexes, relationships, row-count estimates, and safe samples while excluding sensitive values.
2. **Given** aliases for users, projects, and clients, **When** schema intelligence is generated, **Then** aliases enhance the discovered schema without overriding facts from the database.
3. **Given** a schema change, **When** schema status is checked, **Then** the system reports whether indexed schema intelligence is current or stale.

---

### User Story 4 - Generate Safe Fine-Tuning Data (Priority: P2)

As an AI engineer, I want a repeatable dataset-generation workflow that creates supervised examples from schema intelligence, aliases, relationships, safe samples, and expected agent behavior so that the model learns route classification, safe planning, Arabic business vocabulary, and refusal behavior.

**Why this priority**: Fine-tuning quality depends on representative, safe, balanced training examples. The generated dataset must not leak secrets or operational sensitive values.

**Independent Test**: Can be tested by generating a dataset from the restored schema and validating counts, route balance, JSON validity, absence of sensitive fields/values, and coverage of required examples.

**Acceptance Scenarios**:

1. **Given** schema intelligence is available, **When** dataset generation runs, **Then** it creates at least 500 supervised examples for small schemas and 2,000 or more when enough schema coverage exists.
2. **Given** sensitive columns exist, **When** dataset generation runs, **Then** no secret, password, token, credential, or private key values appear in generated examples.
3. **Given** required smoke questions, **When** the dataset is inspected, **Then** it includes examples for listing users, finding users by name, counting projects, conversational messages, sensitive-data refusal, clarification, unsupported requests, and final Arabic answers.

---

### User Story 5 - Run Real Fine-Tuning and Evaluation (Priority: P2)

As an AI engineer, I want to run a real local-model supervised fine-tuning workflow and evaluate the resulting adapter/model so that the agent improves on database-aware planning without claiming success when hardware is insufficient.

**Why this priority**: The user explicitly requires real fine-tuning, not RAG-only behavior. Honest reporting is required if the current machine cannot complete full training.

**Independent Test**: Can be tested by running a full fine-tuning job where resources permit or a tiny smoke-training job where resources are constrained, then evaluating route accuracy, structured output validity, safe refusal, and Arabic answer quality.

**Acceptance Scenarios**:

1. **Given** a valid training dataset and sufficient compute, **When** fine-tuning runs, **Then** a reusable adapter/model artifact is produced and can be evaluated.
2. **Given** local hardware is insufficient for full fine-tuning, **When** the workflow is run, **Then** the system performs the largest safe smoke test possible and reports the exact resource blocker without faking success.
3. **Given** evaluation data, **When** evaluation runs, **Then** results include JSON validity, route accuracy, table-resolution accuracy, sensitive-data refusal, no-write-operation compliance, and Arabic answer behavior.

---

### User Story 6 - Deploy Through GitHub and Validate on Server (Priority: P3)

As an operator, I want all source changes made locally, committed, pushed, pulled on the server, and smoke-tested there so that the server remains a deployment target rather than the source of truth.

**Why this priority**: This preserves release discipline and prevents untracked production hotfixes or accidental exposure of the protected SQL backup.

**Independent Test**: Can be tested by confirming the branch exists locally and on GitHub, the server has pulled the same commit under `/home/rag/`, and server smoke tests were run using the server backup path without committing the backup.

**Acceptance Scenarios**:

1. **Given** local changes are complete, **When** deployment validation starts, **Then** the branch is committed and pushed before any server pull or test.
2. **Given** the protected backup exists on the server, **When** server tests run, **Then** the backup remains at `/home/rag/backup.sql` and is not moved, renamed, deleted, modified, or committed.
3. **Given** server smoke tests run, **When** results are reported, **Then** the report clearly states the pulled commit, database restore status, schema status, health result, chat smoke results, and any GPU or training blockers.

### Edge Cases

- Backup file is missing locally: the system instructs the operator to copy it securely from the approved server path into the approved local backup directory and still prevents committing it.
- Backup file path points inside the repository: restore is refused to reduce accidental commit risk.
- Database credentials are absent: workflows fail with clear configuration guidance and never print passwords.
- Schema contains multiple plausible physical tables for a logical entity: the agent must use schema intelligence and aliases; if still ambiguous, it must ask a clarification rather than guess.
- A user asks for password, token, secret, credential, reset, OTP, or private-key information: the assistant refuses and does not query sensitive columns.
- Fine-tuning output is invalid JSON or unsafe: evaluation fails and the model is not considered accepted.
- Live query returns zero rows: the assistant explains what was searched instead of claiming general absence of data.
- Schema changes after fine-tuning: schema intelligence can be refreshed independently, and live SQL remains the source for current facts.
- Server lacks adequate GPU or memory for full training: inference/schema components can still be validated, while full fine-tuning is reported as blocked until resources are available.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The project MUST use `feature/real-db-finetuning-agent` as the local feature branch for this work.
- **FR-002**: All source changes MUST be made locally first, then committed and pushed before any server pull, deployment, or smoke test.
- **FR-003**: The server MUST be used only for pulling committed code, restoring/testing with the approved backup, running server smoke tests, and reporting results.
- **FR-004**: The protected SQL backup MUST NOT be committed, copied into the repository, deleted, renamed, overwritten, or modified.
- **FR-005**: The system MUST provide a safe database-restore workflow that validates the backup path, refuses repository-contained backups, creates the target database when appropriate, imports the backup, and reports clear success or failure.
- **FR-006**: Database connectivity MUST be configured through environment-specific settings, with no real credentials committed.
- **FR-007**: The system MUST discover database schema details including tables, table descriptions where available, columns, column descriptions where available, data types, nullable flags, defaults, primary keys, foreign keys, indexes, enum-like values where available, approximate row counts, safe sample rows, and detected relationships.
- **FR-008**: The system MUST mark sensitive fields and prevent sensitive sample values from appearing in schema output, generated datasets, logs, or user responses.
- **FR-009**: The system MUST support a manually editable alias catalog that enhances discovered schema intelligence for users, projects, clients, and similar business entities without replacing discovered facts.
- **FR-010**: The system MUST support schema ingestion, schema search, and schema status checks so that the agent can retrieve current schema intelligence.
- **FR-011**: Schema intelligence MUST be refreshed or reported stale when discovered schema or alias definitions change.
- **FR-012**: The system MUST generate supervised training examples from discovered schema, aliases, relationships, safe samples, common Arabic/English/mixed questions, forbidden requests, conversational turns, clarification cases, unsupported cases, safe query-plan examples, and final Arabic answer examples.
- **FR-013**: Generated real-data training files MUST be excluded from version control; only a tiny fake sample training file may be committed.
- **FR-014**: The generated dataset MUST contain at least 500 examples for a small schema and 2,000 or more examples when the schema has enough entities to support that size.
- **FR-015**: The training dataset MUST be balanced across database-query, conversational, forbidden, clarification, unsupported, and final-answer behavior.
- **FR-016**: The system MUST support real supervised adapter-style fine-tuning for a local open-source model and produce a reusable adapter or model artifact when resources permit.
- **FR-017**: The fine-tuning workflow MUST support configurable base model, dataset path, output path, training size controls, precision/quantization mode, resume behavior, adapter saving, and optional adapter merging.
- **FR-018**: The system MUST provide evaluation that checks structured-output validity, route accuracy, table-resolution accuracy, sensitive-data refusal, no-write-operation compliance, Arabic answer quality, and required smoke prompts.
- **FR-019**: If full fine-tuning cannot run on available hardware, the system MUST run a safe tiny smoke test where possible and clearly report the hardware/resource blocker.
- **FR-020**: Runtime chat MUST treat the fine-tuned or base local model as the primary route classifier and query planner, while still validating all plans before execution.
- **FR-021**: Runtime chat MUST continue querying live structured facts from MySQL; fine-tuning MUST NOT be treated as a replacement for live database queries.
- **FR-022**: Runtime schema search MUST provide current schema context to the model; fine-tuning MUST NOT be treated as a replacement for schema freshness.
- **FR-023**: The agent MUST classify messages into conversational, database query, knowledge search, mixed, clarification, forbidden, or unsupported outcomes.
- **FR-024**: The agent MUST output structured query plans rather than executable raw SQL.
- **FR-025**: Query plans MUST support read-only selection, counting, and aggregate operations over approved schema fields.
- **FR-026**: The system MUST reject write operations, destructive operations, stored procedures, multiple statements, unknown tables, unknown columns, sensitive columns, unsafe wildcard behavior, and unsafe or unbounded results.
- **FR-027**: The system MUST execute only validated, parameterized, read-only queries and enforce row limits and query timeouts.
- **FR-028**: The assistant MUST answer conversational Arabic messages naturally without returning unsupported or accessing the database.
- **FR-029**: The assistant MUST refuse requests for passwords, tokens, secrets, credentials, private keys, reset codes, OTPs, and similar sensitive data.
- **FR-030**: When no live rows match a user request, the assistant MUST explain the search strategy and filters used rather than inventing facts.
- **FR-031**: The assistant MUST compose final Arabic answers from returned live rows only and must not invent operational facts.
- **FR-032**: The system MUST expose chat, decision, and final-answer capabilities needed by the existing AI-RAG flow while preserving private/internal boundaries already required by the project.
- **FR-033**: Documentation MUST explain the difference between fine-tuning, schema intelligence, RAG, and live SQL, including what is and is not trained.
- **FR-034**: Documentation MUST explain local backup copy, local restore, server restore from `/home/rag/backup.sql`, dataset generation, fine-tuning, evaluation, serving, schema refresh, smoke tests, and the GitHub-push/server-pull workflow.
- **FR-035**: Final reporting MUST include local path, branch, commit, changed files, tests, backup use, database restore status, schema ingestion status, dataset count, model/config, fine-tuning/evaluation outcome, GitHub push result, server pull result, server health, server smoke tests, and honest blockers.

### Key Entities *(include if feature involves data)*

- **SQL Backup**: Protected database dump used for local/server development validation; must remain outside version control and must not be modified in place on the server.
- **Restored Project Database**: Local or server-side database created from the backup for schema discovery, safe live query testing, dataset generation, and smoke tests.
- **Schema Catalog**: Discovered and enriched representation of tables, columns, relationships, safe samples, sensitive markers, aliases, and schema hash/status.
- **Alias Catalog**: Human-editable business vocabulary mapping Arabic/English domain terms to candidate entities and fields that enhances, but does not override, discovered schema.
- **Training Dataset**: Generated supervised chat examples used to teach routing, safe planning, refusals, Arabic business vocabulary, and final-answer behavior.
- **Fine-Tuned Adapter/Model**: Reusable model artifact produced by real supervised fine-tuning and evaluated before being considered acceptable.
- **Structured Query Plan**: Model-produced JSON decision that describes route, operation, logical entities, resolved tables, columns, filters, joins, grouping, ordering, limit, and confirmation needs without raw SQL.
- **Query Validation Result**: Safety decision that approves or rejects a structured plan based on schema, sensitive-field rules, read-only rules, and bounded execution.
- **Chat Response**: Final user-facing Arabic answer, route, optional display data, and safe query summary.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: At least 95% of required smoke questions route to the expected category on the evaluation set.
- **SC-002**: 100% of accepted database plans in the test suite are valid structured plans and contain no executable raw SQL.
- **SC-003**: 100% of sensitive-data requests in the test suite are refused without querying or exposing sensitive values.
- **SC-004**: 100% of generated real-data training examples pass secret/sensitive-value scanning before use.
- **SC-005**: Dataset generation creates at least 500 examples for a small schema and 2,000 or more examples for a sufficiently rich schema.
- **SC-006**: The assistant answers the four required smoke prompts correctly or with honest no-match responses after the restored database is available.
- **SC-007**: Evaluation reports JSON validity, route accuracy, table-resolution accuracy, sensitive refusal, no-write-operation compliance, and Arabic answer behavior for every evaluated model artifact.
- **SC-008**: No protected SQL backup, generated real training dataset, model weight, adapter, credential, secret, or environment file appears in Git status before commit.
- **SC-009**: Server validation uses the same pushed commit SHA as the local branch and reports all smoke-test outcomes without uncommitted server edits.
- **SC-010**: If full training is blocked by hardware, the final report identifies the exact blocker and still demonstrates the implemented pipeline with the largest safe local/server smoke test possible.

## Assumptions

- The existing project repository is available locally at `/home/hussein/Documents/AI-RAG/ai-rag`; if missing in a future environment, it will be cloned from `mohamedhussein687/AI-RAG`.
- The protected backup already exists on the server at `/home/rag/backup.sql`; local use requires copying it to `/home/hussein/backups/backup.sql`.
- The backup contains enough schema and safe sample data to generate meaningful domain examples after sensitive values are removed or masked.
- Live operational facts will always come from the current database at runtime; fine-tuning teaches behavior, vocabulary, and planning rather than memorizing rows.
- Schema search is used for current schema intelligence and long-lived descriptions; it is not a replacement for live structured queries.
- The existing gateway and AI module security boundaries remain in force, including private internal services and no public database exposure.
- Full fine-tuning may require GPU resources beyond the local machine; in that case, a smoke-training path and exact full-training command are acceptable until suitable hardware is available.
- The first implementation targets the restored project database and approved smoke questions; broader production rollout requires separate operational approval after validation.
