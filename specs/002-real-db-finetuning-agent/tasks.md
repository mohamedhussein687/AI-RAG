# Tasks: Real Database Fine-Tuning Agent

**Input**: Design documents from `/specs/002-real-db-finetuning-agent/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Included because the feature specification explicitly requires local tests, smoke tests, dataset validation, SQL safety tests, training/evaluation validation, and server smoke verification.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, etc.)
- Each task includes exact file paths

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Establish branch hygiene, ignore rules, dependencies, and package layout required by all stories.

- [X] T001 Verify local branch is `feature/real-db-finetuning-agent` and record baseline `git status --short` in `specs/002-real-db-finetuning-agent/tasks.md`
  - Baseline recorded 2026-06-23:
    - Branch: `feature/real-db-finetuning-agent`
    - `git status --short` before Phase 1 implementation:
      - ` M .specify/feature.json`
      - ` M AGENTS.md`
      - `?? specs/002-real-db-finetuning-agent/`
- [X] T002 Update `.gitignore` with SQL backups, dumps, archives, env files, model outputs, checkpoints, adapters, runs, and generated real training data exclusions
- [X] T003 Update `construction-ai-rag-module/.env.example` with `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_DATABASE`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_CONNECT_TIMEOUT_SECONDS`, `MYSQL_QUERY_TIMEOUT_SECONDS`, `MYSQL_MAX_ROWS`, and fine-tuned LLM serving variables
- [X] T004 Add training, MySQL, and dataset optional dependencies to `construction-ai-rag-module/ai_module/pyproject.toml`
- [X] T005 [P] Create package skeleton files in `construction-ai-rag-module/ai_module/app/db/__init__.py` and `construction-ai-rag-module/ai_module/app/training/__init__.py`
- [X] T006 [P] Create committed fake training sample directory and file at `construction-ai-rag-module/ai_module/data/training/sample_fake.jsonl`
- [X] T007 [P] Create schema alias config at `construction-ai-rag-module/config/schema_aliases.yml`
- [X] T008 [P] Create documentation placeholders in `construction-ai-rag-module/ai_module/docs/database-aware-agent.md`, `construction-ai-rag-module/ai_module/docs/fine-tuning.md`, `construction-ai-rag-module/ai_module/docs/local-backup-restore.md`, and `construction-ai-rag-module/ai_module/docs/server-deployment.md`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Implement shared safe configuration, schema models, SQL safety primitives, and CLI routing used by all user stories.

**⚠️ CRITICAL**: No user story implementation should begin until this phase is complete.

- [X] T009 Add MySQL, training, schema alias, dataset, adapter, and serving settings to `construction-ai-rag-module/ai_module/app/config.py`
- [X] T010 Add shared sensitive-field detection constants and helpers in `construction-ai-rag-module/ai_module/app/schema/schema_models.py`
- [X] T011 Define `SchemaSnapshot`, `SchemaTable`, `SchemaColumn`, `AliasCatalog`, `StructuredQueryPlan`, and `QueryExecution` models in `construction-ai-rag-module/ai_module/app/schema/schema_models.py`
- [X] T012 Define database-aware request/response schemas for `/api/chat`, `/api/schema/ingest`, `/api/schema/search`, `/api/schema/status`, structured decisions, and final answers in `construction-ai-rag-module/ai_module/app/schemas.py`
- [X] T013 Add PostgreSQL metadata models for schema snapshots, schema chunks, training runs, and evaluation results in `construction-ai-rag-module/ai_module/app/storage/models.py`
- [X] T014 Add Alembic migration for schema intelligence and training metadata in `construction-ai-rag-module/ai_module/app/storage/migrations/versions/0003_schema_training_metadata.py`
- [X] T015 Implement read-only MySQL connection factory with timeout handling and redacted errors in `construction-ai-rag-module/ai_module/app/db/mysql.py`
- [X] T016 Implement structured plan validator for read-only operations, known tables, known columns, sensitive-column denial, operators, joins, limits, and raw SQL rejection in `construction-ai-rag-module/ai_module/app/db/sql_validator.py`
- [X] T017 Implement parameterized SQL compiler for validated plans in `construction-ai-rag-module/ai_module/app/db/sql_compiler.py`
- [X] T018 Implement read-only SQL executor with query timeout, max rows, safe row serialization, and redacted audit summary in `construction-ai-rag-module/ai_module/app/db/sql_executor.py`
- [X] T019 Extend `construction-ai-rag-module/ai_module/ingestion_worker/__main__.py` command parser with `restore-backup`, `schema-ingest`, `schema-status`, `schema-refresh`, and `smoke-chat` subcommands
- [X] T020 [P] Add SQL safety unit tests in `construction-ai-rag-module/ai_module/tests/test_sql_validator.py`
- [X] T021 [P] Add parameterized compiler unit tests in `construction-ai-rag-module/ai_module/tests/test_sql_compiler.py`
- [X] T022 [P] Add MySQL executor redaction and timeout tests in `construction-ai-rag-module/ai_module/tests/test_sql_executor.py`

**Checkpoint**: Foundation ready. User story implementation can proceed.

---

## Phase 3: User Story 1 - Ask Live Database Questions in Arabic (Priority: P1) 🎯 MVP

**Goal**: Users can ask Arabic/English database questions and receive accurate live answers from the restored database through validated structured plans.

**Independent Test**: Restore backup, ingest schema, then run smoke-chat for "اعرض جميع اسماء المستخدمين", "اريد بيانات المستخدم Ayman Ibrahim El Sayed", and "كام مشروع عندي؟"; verify answers match live database results or honest no-match explanations.

### Tests for User Story 1

- [X] T023 [P] [US1] Add schema-backed chat tests for listing users, user-by-name lookup, and project count in `construction-ai-rag-module/ai_module/tests/test_database_aware_chat.py`
- [X] T024 [P] [US1] Add empty-result behavior tests in `construction-ai-rag-module/ai_module/tests/test_database_aware_chat.py`
- [X] T025 [P] [US1] Add Spring Gateway database-plan validation tests in `construction-gateway/src/test/java/com/construction/rag/gateway/SafeDatabaseQueryServiceTest.java`
- [X] T026 [P] [US1] Add API contract tests for `/api/chat` and `/api/agent/decide` in `construction-ai-rag-module/ai_module/tests/test_database_agent_contracts.py`

### Implementation for User Story 1

- [X] T027 [US1] Implement `/api/chat` database-aware orchestration in `construction-ai-rag-module/ai_module/app/main.py`
- [X] T028 [US1] Update decision request handling to retrieve schema context before model planning in `construction-ai-rag-module/ai_module/app/agent/decision_service.py`
- [X] T029 [US1] Update prompt construction for structured database planning without raw SQL in `construction-ai-rag-module/ai_module/app/agent/prompt_builder.py`
- [X] T030 [US1] Update JSON guard to validate required database plan shape in `construction-ai-rag-module/ai_module/app/agent/json_guard.py`
- [X] T031 [US1] Implement final answer composition from executed rows and empty-result summaries in `construction-ai-rag-module/ai_module/app/agent/final_answer_service.py`
- [X] T032 [US1] Integrate plan validation, compilation, execution, and final-answer flow in `construction-ai-rag-module/ai_module/app/main.py`
- [X] T033 [US1] Update Spring Gateway `/api/chat` flow to forward AI-generated plans for validation/execution without business intent inference in `construction-gateway/src/main/java/com/construction/rag/gateway/RagGatewayController.java`
- [X] T034 [US1] Update Spring Gateway safe query validation to accept only exact schema-backed plan tables and columns in `construction-gateway/src/main/java/com/construction/rag/gateway/SafeDatabaseQueryService.java`
- [X] T035 [US1] Add `smoke-chat` CLI implementation for local database-aware chat validation in `construction-ai-rag-module/ai_module/ingestion_worker/smoke_chat.py`

**Checkpoint**: User Story 1 is functional and testable independently.

---

## Phase 4: User Story 2 - Route and Refuse Safely (Priority: P1)

**Goal**: The agent classifies conversational, database, knowledge, clarification, forbidden, and unsupported messages safely and refuses sensitive data requests.

**Independent Test**: Send conversational, sensitive, ambiguous, and unsupported prompts; verify route, answer, database access decision, and sensitive refusal behavior.

### Tests for User Story 2

- [X] T036 [P] [US2] Add conversational route tests for Arabic social messages in `construction-ai-rag-module/ai_module/tests/test_database_aware_chat.py`
- [X] T037 [P] [US2] Add forbidden sensitive request tests for password, token, secret, OTP, private key, and credential prompts in `construction-ai-rag-module/ai_module/tests/test_agent_decision.py`
- [X] T038 [P] [US2] Add clarification and unsupported route tests in `construction-ai-rag-module/ai_module/tests/test_agent_decision.py`
- [X] T039 [P] [US2] Add no-database-call assertions for conversational and forbidden requests in `construction-ai-rag-module/ai_module/tests/test_database_aware_chat.py`

### Implementation for User Story 2

- [X] T040 [US2] Refactor route classification prompt and structured output handling in `construction-ai-rag-module/ai_module/app/agent/decision_service.py`
- [X] T041 [US2] Add forbidden-route and clarification-route schemas in `construction-ai-rag-module/ai_module/app/schemas.py`
- [X] T042 [US2] Add sensitive-request refusal prompt instructions in `construction-ai-rag-module/ai_module/app/agent/prompt_builder.py`
- [X] T043 [US2] Add deterministic service-failure fallback for obvious conversational prompts only in `construction-ai-rag-module/ai_module/app/agent/decision_service.py`
- [X] T044 [US2] Ensure final-answer service refuses sensitive data and never uses sensitive tool results in `construction-ai-rag-module/ai_module/app/agent/final_answer_service.py`
- [X] T045 [US2] Add redacted route, decision, and error logging fields in `construction-ai-rag-module/ai_module/app/common/logging.py`

**Checkpoint**: User Story 2 is functional and testable independently.

---

## Phase 5: User Story 3 - Build Domain Intelligence from Real Schema (Priority: P1)

**Goal**: Operators can discover, enrich, hash, ingest, search, and status-check real restored database schema without exposing secrets.

**Independent Test**: Run schema discovery and schema status against the restored database; verify tables, columns, keys, indexes, relationships, aliases, safe samples, sensitive exclusions, and stale/fresh hash behavior.

### Tests for User Story 3

- [X] T046 [P] [US3] Add schema discovery tests for tables, columns, comments, keys, indexes, foreign keys, enum-like values, and row counts in `construction-ai-rag-module/ai_module/tests/test_schema_discovery.py`
- [X] T047 [P] [US3] Add sensitive sample exclusion tests in `construction-ai-rag-module/ai_module/tests/test_schema_discovery.py`
- [X] T048 [P] [US3] Add schema hash change tests in `construction-ai-rag-module/ai_module/tests/test_schema_hash.py`
- [X] T049 [P] [US3] Add Qdrant schema search relevance tests in `construction-ai-rag-module/ai_module/tests/test_schema_ingestion.py`
- [X] T050 [P] [US3] Add CLI schema command tests in `construction-ai-rag-module/ai_module/tests/test_ingestion_worker_schema_commands.py`

### Implementation for User Story 3

- [X] T051 [US3] Implement MySQL/MariaDB table, column, key, index, foreign-key, comment, enum, and row-count discovery in `construction-ai-rag-module/ai_module/app/schema/schema_discovery.py`
- [X] T052 [US3] Implement safe sample extraction and sensitive-value redaction in `construction-ai-rag-module/ai_module/app/schema/schema_discovery.py`
- [X] T053 [US3] Implement alias loading and alias hash support in `construction-ai-rag-module/ai_module/app/schema/schema_models.py`
- [X] T054 [US3] Implement schema hash calculation in `construction-ai-rag-module/ai_module/app/schema/schema_hash.py`
- [X] T055 [US3] Implement schema chunk generation and ingestion into metadata/Qdrant in `construction-ai-rag-module/ai_module/app/schema/schema_ingestion.py`
- [X] T056 [US3] Implement schema search over Qdrant with metadata filters in `construction-ai-rag-module/ai_module/app/schema/schema_search.py`
- [X] T057 [US3] Implement schema status and stale detection in `construction-ai-rag-module/ai_module/app/schema/schema_service.py`
- [X] T058 [US3] Add `/api/schema/ingest`, `/api/schema/search`, and `/api/schema/status` handlers in `construction-ai-rag-module/ai_module/app/main.py`
- [X] T059 [US3] Implement `schema-ingest`, `schema-status`, and `schema-refresh` CLI commands in `construction-ai-rag-module/ai_module/ingestion_worker/schema_commands.py`

**Checkpoint**: User Story 3 is functional and testable independently.

---

## Phase 6: User Story 4 - Generate Safe Fine-Tuning Data (Priority: P2)

**Goal**: Operators can generate a balanced supervised training dataset from schema intelligence without leaking secrets.

**Independent Test**: Generate dataset from discovered schema; verify JSONL chat format, count thresholds, route balance, required prompt coverage, and no sensitive values.

### Tests for User Story 4

- [X] T060 [P] [US4] Add dataset format and minimum-count tests in `construction-ai-rag-module/ai_module/tests/test_dataset_builder.py`
- [X] T061 [P] [US4] Add dataset sensitive-value scanning tests in `construction-ai-rag-module/ai_module/tests/test_dataset_builder.py`
- [X] T062 [P] [US4] Add route-balance and required-smoke-question coverage tests in `construction-ai-rag-module/ai_module/tests/test_dataset_builder.py`

### Implementation for User Story 4

- [X] T063 [US4] Implement dataset builder CLI and library in `construction-ai-rag-module/ai_module/training/dataset_builder.py`
- [X] T064 [P] [US4] Add database-query example templates in `construction-ai-rag-module/ai_module/training/templates/database_query.yml`
- [X] T065 [P] [US4] Add conversational, forbidden, clarification, unsupported, and final-answer templates in `construction-ai-rag-module/ai_module/training/templates/behavior.yml`
- [X] T066 [US4] Implement schema/alias/sample driven example expansion in `construction-ai-rag-module/ai_module/training/dataset_builder.py`
- [X] T067 [US4] Implement dataset validation for JSONL format, structured JSON outputs, counts, balance, and sensitive-value absence in `construction-ai-rag-module/ai_module/training/dataset_builder.py`
- [X] T068 [US4] Add fake sample data covering database, conversational, forbidden, clarification, unsupported, and final-answer examples in `construction-ai-rag-module/ai_module/data/training/sample_fake.jsonl`
- [X] T069 [US4] Document dataset generation and safety checks in `construction-ai-rag-module/ai_module/training/README.md`

**Checkpoint**: User Story 4 is functional and testable independently.

---

## Phase 7: User Story 5 - Run Real Fine-Tuning and Evaluation (Priority: P2)

**Goal**: Engineers can run real LoRA/QLoRA training or an honest smoke-training path, then evaluate output quality and safety.

**Independent Test**: Validate configs, run a tiny training smoke test where possible, run evaluation on sample eval data, and report full-training blockers honestly if hardware is insufficient.

### Tests for User Story 5

- [X] T070 [P] [US5] Add training config loading and dataset validation tests in `construction-ai-rag-module/ai_module/tests/test_training_scripts.py`
- [X] T071 [P] [US5] Add evaluation metric and invalid-output tests in `construction-ai-rag-module/ai_module/tests/test_evaluate_agent.py`
- [X] T072 [P] [US5] Add tiny smoke-training dry-run tests in `construction-ai-rag-module/ai_module/tests/test_training_scripts.py`

### Implementation for User Story 5

- [X] T073 [US5] Implement LoRA/QLoRA training CLI in `construction-ai-rag-module/ai_module/training/train_lora.py`
- [X] T074 [US5] Implement evaluation CLI for JSON validity, route accuracy, table resolution, refusal, no-write compliance, and Arabic behavior in `construction-ai-rag-module/ai_module/training/evaluate_agent.py`
- [X] T075 [P] [US5] Add Qwen LoRA config in `construction-ai-rag-module/ai_module/training/configs/qwen_lora.yaml`
- [X] T076 [P] [US5] Add Qwen QLoRA config in `construction-ai-rag-module/ai_module/training/configs/qwen_qlora.yaml`
- [X] T077 [US5] Add model serving configuration support for fine-tuned model/adapters in `construction-ai-rag-module/ai_module/app/config.py`
- [X] T078 [US5] Update LLM client model selection and fine-tuned mode metadata in `construction-ai-rag-module/ai_module/app/clients/llm_client.py`
- [X] T079 [US5] Document training, evaluation, adapter merge/serve options, and hardware blockers in `construction-ai-rag-module/ai_module/docs/fine-tuning.md`

**Checkpoint**: User Story 5 is functional and testable independently.

---

## Phase 8: User Story 6 - Deploy Through GitHub and Validate on Server (Priority: P3)

**Goal**: The feature is committed, pushed, pulled under `/home/rag/`, and validated on the server without using the server as a development workspace.

**Independent Test**: Confirm local and server commits match, server uses `/home/rag/backup.sql`, schema status runs, smoke chat runs, and no uncommitted server edits are required.

### Tests for User Story 6

- [X] T080 [P] [US6] Add documentation checks for no backup/model/dataset artifacts in Git in `construction-ai-rag-module/ai_module/tests/test_repository_hygiene.py`
- [X] T081 [P] [US6] Add restore-path refusal tests for repository-contained SQL files in `construction-ai-rag-module/ai_module/tests/test_restore_backup.py`

### Implementation for User Story 6

- [X] T082 [US6] Implement backup restore command with path validation and redacted reporting in `construction-ai-rag-module/ai_module/ingestion_worker/restore_backup.py`
- [X] T083 [US6] Update `construction-ai-rag-module/ai_module/ingestion_worker/__main__.py` to wire the restore command to `restore_backup.py`
- [X] T084 [US6] Document local backup copy, local restore, and server restore in `construction-ai-rag-module/ai_module/docs/local-backup-restore.md`
- [X] T085 [US6] Document GitHub push then server pull workflow in `construction-ai-rag-module/ai_module/docs/server-deployment.md`
- [X] T086 [US6] Update `construction-ai-rag-module/README.md` with links to database-aware agent, fine-tuning, restore, and server deployment docs
- [X] T087 [US6] Run local tests and record command/results in `specs/002-real-db-finetuning-agent/quickstart.md`
- [ ] T088 [US6] Commit local changes and push `feature/real-db-finetuning-agent` to GitHub repository `mohamedhussein687/AI-RAG`
- [ ] T089 [US6] Pull pushed branch under `/home/rag/AI-RAG` on `ssh techlab-ai` without copying uncommitted files and record the pulled SHA in `specs/002-real-db-finetuning-agent/quickstart.md`
- [ ] T090 [US6] Run server restore, schema ingest/status, and smoke-chat commands using `/home/rag/backup.sql` and record redacted results in `specs/002-real-db-finetuning-agent/quickstart.md`

**Checkpoint**: User Story 6 is functional and testable independently.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Final security, docs, cleanup, and release readiness across all stories.

- [ ] T091 [P] Update `construction-ai-rag-module/ai_module/docs/database-aware-agent.md` with architecture, safety boundaries, schema RAG, live SQL, and final answer behavior
- [ ] T092 [P] Update `construction-ai-rag-module/ai_module/docs/fine-tuning.md` with the difference between fine-tuning and RAG, what is trained, and what is never trained
- [ ] T093 [P] Update `construction-ai-rag-module/ai_module/docs/server-deployment.md` with exact final report structure and server smoke workflow
- [ ] T094 Run full Python test suite from `construction-ai-rag-module/ai_module` and fix failures in touched files
- [ ] T095 Run full Spring Gateway Maven tests from `construction-gateway` and fix failures in touched files
- [ ] T096 Run secret/artifact hygiene check with `git status --short` and `git diff --cached --name-only` from repository root
- [ ] T097 Run OpenAPI/YAML validation for `specs/002-real-db-finetuning-agent/contracts/database-agent.openapi.yaml`
- [ ] T098 Verify quickstart commands are accurate against implemented CLI paths in `specs/002-real-db-finetuning-agent/quickstart.md`
- [ ] T099 Prepare final redacted report using the structure in `specs/002-real-db-finetuning-agent/quickstart.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies.
- **Foundational (Phase 2)**: Depends on Phase 1 and blocks all user stories.
- **US1 (Phase 3)**: Depends on Phase 2 and is the MVP runtime flow.
- **US2 (Phase 4)**: Depends on Phase 2; can run in parallel with US1 after foundational tasks, but should be validated before production smoke.
- **US3 (Phase 5)**: Depends on Phase 2; can run in parallel with US1/US2 and provides schema intelligence required for strongest US1 behavior.
- **US4 (Phase 6)**: Depends on US3 schema intelligence.
- **US5 (Phase 7)**: Depends on US4 dataset generation.
- **US6 (Phase 8)**: Depends on completed local implementation and tests for intended deployment scope.
- **Polish (Phase 9)**: Depends on all desired user stories.

### User Story Dependencies

- **US1 Ask Live Database Questions**: MVP; depends on foundation and benefits from US3 but can be smoke-tested with a minimal schema fixture.
- **US2 Route and Refuse Safely**: Independent after foundation; should be completed before exposing any database-aware chat behavior.
- **US3 Build Domain Intelligence**: Independent after foundation; required before robust production schema-aware planning and dataset generation.
- **US4 Generate Safe Fine-Tuning Data**: Depends on US3.
- **US5 Run Real Fine-Tuning and Evaluation**: Depends on US4.
- **US6 Deploy Through GitHub and Validate on Server**: Depends on completed local implementation, commit, and push.

### Within Each User Story

- Write tests first and verify they fail when practical.
- Implement models and schemas before services.
- Implement services before endpoint/CLI integration.
- Validate story independently before moving to dependent stories.

---

## Parallel Opportunities

- T005, T006, T007, and T008 can run in parallel.
- T020, T021, and T022 can run in parallel after T016-T018 interfaces are planned.
- T023, T024, T025, and T026 can run in parallel.
- T036, T037, T038, and T039 can run in parallel.
- T046, T047, T048, T049, and T050 can run in parallel.
- T064 and T065 can run in parallel.
- T070, T071, and T072 can run in parallel.
- T075 and T076 can run in parallel.
- T080 and T081 can run in parallel.
- T091, T092, and T093 can run in parallel.

---

## Parallel Example: User Story 1

```bash
Task: "T023 [P] [US1] Add schema-backed chat tests for listing users, user-by-name lookup, and project count in construction-ai-rag-module/ai_module/tests/test_database_aware_chat.py"
Task: "T024 [P] [US1] Add empty-result behavior tests in construction-ai-rag-module/ai_module/tests/test_database_aware_chat.py"
Task: "T025 [P] [US1] Add Spring Gateway database-plan validation tests in construction-gateway/src/test/java/com/construction/rag/gateway/SafeDatabaseQueryServiceTest.java"
Task: "T026 [P] [US1] Add API contract tests for /api/chat and /api/agent/decide in construction-ai-rag-module/ai_module/tests/test_database_agent_contracts.py"
```

## Parallel Example: User Story 3

```bash
Task: "T046 [P] [US3] Add schema discovery tests for tables, columns, comments, keys, indexes, foreign keys, enum-like values, and row counts in construction-ai-rag-module/ai_module/tests/test_schema_discovery.py"
Task: "T047 [P] [US3] Add sensitive sample exclusion tests in construction-ai-rag-module/ai_module/tests/test_schema_discovery.py"
Task: "T048 [P] [US3] Add schema hash change tests in construction-ai-rag-module/ai_module/tests/test_schema_hash.py"
Task: "T049 [P] [US3] Add Qdrant schema search relevance tests in construction-ai-rag-module/ai_module/tests/test_schema_ingestion.py"
```

## Parallel Example: User Story 4

```bash
Task: "T064 [P] [US4] Add database-query example templates in construction-ai-rag-module/ai_module/training/templates/database_query.yml"
Task: "T065 [P] [US4] Add conversational, forbidden, clarification, unsupported, and final-answer templates in construction-ai-rag-module/ai_module/training/templates/behavior.yml"
```

---

## Implementation Strategy

### MVP First (User Story 1 + Required Safety Slice)

1. Complete Phase 1 setup.
2. Complete Phase 2 foundation.
3. Complete enough of US3 to discover and search schema for the restored database.
4. Complete US2 forbidden/conversational safety checks.
5. Complete US1 live database chat MVP.
6. Validate with the three required live database questions and one conversational prompt.

### Incremental Delivery

1. Deliver schema discovery/search and safe SQL execution.
2. Deliver database-aware chat and refusal behavior.
3. Deliver dataset generation.
4. Deliver real training/evaluation scripts.
5. Deliver GitHub-pushed server validation.

### Server Validation Rule

Server work starts only after local commit and GitHub push. Do not copy uncommitted local code to `techlab-ai`; pull the pushed branch under `/home/rag/` and run server smoke tests there.

### Artifact Safety Rule

Before every commit, verify that Git does not include SQL backups, generated real datasets, model outputs, adapters, checkpoints, `.env` files, tokens, passwords, or private keys.
