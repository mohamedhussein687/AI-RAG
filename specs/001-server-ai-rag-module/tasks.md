# Tasks: Server AI RAG Module

**Input**: Design documents from `specs/001-server-ai-rag-module/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/ai-rag-module.openapi.yaml`, `quickstart.md`

**Tests**: Required by the feature specification and quickstart. Test tasks are included before implementation tasks for each user story.

**Organization**: Tasks are grouped by independently testable user story.

## Phase 1: Setup

**Purpose**: Create the deployable FastAPI AI module package and baseline development configuration.

- [X] T001 Create the requested directory tree under `construction-ai-rag-module/ai_module/app/`
- [X] T002 Create Python project metadata and dependencies in `construction-ai-rag-module/ai_module/pyproject.toml`
- [X] T003 [P] Create Docker build configuration in `construction-ai-rag-module/ai_module/Dockerfile`
- [X] T004 [P] Create Docker Compose services in `construction-ai-rag-module/docker-compose.yml`
- [X] T005 [P] Create environment defaults in `construction-ai-rag-module/.env.example`
- [X] T006 [P] Create placeholder package files in `construction-ai-rag-module/ai_module/app/__init__.py` and subpackage `__init__.py` files

---

## Phase 2: Foundational

**Purpose**: Shared infrastructure that blocks every endpoint and user story.

**Critical**: No user story work should begin until the schemas, auth, logging, settings, and persistence scaffolding exist.

- [X] T007 Implement environment settings in `construction-ai-rag-module/ai_module/app/config.py`
- [X] T008 Implement bearer-token authentication in `construction-ai-rag-module/ai_module/app/auth.py`
- [X] T009 Implement redacted structured logging and request IDs in `construction-ai-rag-module/ai_module/app/common/logging.py`
- [X] T010 [P] Implement common API error helpers in `construction-ai-rag-module/ai_module/app/common/errors.py`
- [X] T011 Implement Pydantic v2 request and response schemas in `construction-ai-rag-module/ai_module/app/schemas.py`
- [X] T012 Implement PostgreSQL async engine/session setup in `construction-ai-rag-module/ai_module/app/storage/postgres.py`
- [X] T013 [P] Implement SQLAlchemy models for documents, chunks, jobs, retrieval logs, conversations, and agent events in `construction-ai-rag-module/ai_module/app/storage/models.py`
- [X] T014 Create Alembic configuration and initial migration in `construction-ai-rag-module/ai_module/app/storage/migrations/`
- [X] T015 Implement FastAPI app factory, middleware wiring, and router registration in `construction-ai-rag-module/ai_module/app/main.py`

**Checkpoint**: Foundation ready. User story work can now proceed in priority order or in parallel.

---

## Phase 3: User Story 1 - Ask Arabic Operational Questions Safely (Priority: P1) MVP

**Goal**: Return structured, Arabic-friendly decisions for live operational questions without raw SQL or local construction database access.

**Independent Test**: Submit `/api/agent/decide` requests for operational, ambiguous, and sensitive questions and verify valid structured JSON, Arabic output where applicable, no raw SQL, and only `database_query` tool calls.

### Tests for User Story 1

- [X] T016 [P] [US1] Add auth-required tests for protected endpoints in `construction-ai-rag-module/ai_module/tests/test_auth.py`
- [X] T017 [P] [US1] Add schema validation tests for agent decisions in `construction-ai-rag-module/ai_module/tests/test_schemas.py`
- [X] T018 [P] [US1] Add operational decision tests for `كم مشروع waiting؟` in `construction-ai-rag-module/ai_module/tests/test_agent_decision.py`
- [X] T019 [P] [US1] Add forbidden sensitive-request tests in `construction-ai-rag-module/ai_module/tests/test_agent_decision.py`
- [X] T020 [P] [US1] Add no-raw-SQL decision tests in `construction-ai-rag-module/ai_module/tests/test_agent_decision.py`

### Implementation for User Story 1

- [X] T021 [P] [US1] Implement OpenAI-compatible chat client and fake LLM mode in `construction-ai-rag-module/ai_module/app/clients/llm_client.py`
- [X] T022 [P] [US1] Implement Arabic-friendly prompt construction and untrusted-document guard text in `construction-ai-rag-module/ai_module/app/agent/prompt_builder.py`
- [X] T023 [US1] Implement JSON decision validation and unsafe-key rejection in `construction-ai-rag-module/ai_module/app/agent/json_guard.py`
- [X] T024 [US1] Implement live-data classification and `database_query` planning in `construction-ai-rag-module/ai_module/app/agent/decision_service.py`
- [X] T025 [US1] Implement `/api/agent/decide` route in `construction-ai-rag-module/ai_module/app/main.py`

**Checkpoint**: User Story 1 is independently functional and can be demonstrated as the MVP.

---

## Phase 4: User Story 2 - Answer Policy and Procedure Questions from Authorized Documents (Priority: P1)

**Goal**: Index and search local knowledge while enforcing tenant, project, and document permissions before returning chunks.

**Independent Test**: Index Arabic policy content for a tenant/project/permission set, search as authorized and unauthorized users, and verify only authorized excerpts with sources are returned.

### Tests for User Story 2

- [X] T026 [P] [US2] Add document indexing chunk-creation tests in `construction-ai-rag-module/ai_module/tests/test_document_indexing.py`
- [X] T027 [P] [US2] Add tenant isolation search tests in `construction-ai-rag-module/ai_module/tests/test_rag_search.py`
- [X] T028 [P] [US2] Add permission isolation search tests in `construction-ai-rag-module/ai_module/tests/test_rag_search.py`
- [X] T029 [P] [US2] Add Arabic retrieval relevance tests in `construction-ai-rag-module/ai_module/tests/test_rag_search.py`
- [X] T030 [P] [US2] Add local-RAG decision tests for `إزاي أضيف مستخلص؟` in `construction-ai-rag-module/ai_module/tests/test_agent_decision.py`

### Implementation for User Story 2

- [X] T031 [P] [US2] Implement Arabic-friendly cleaning and overlapping chunks in `construction-ai-rag-module/ai_module/app/rag/chunking_service.py`
- [X] T032 [P] [US2] Implement deterministic fake embeddings and external-ready interface in `construction-ai-rag-module/ai_module/app/rag/embedding_client.py`
- [X] T033 [P] [US2] Implement deterministic fake reranking and external-ready interface in `construction-ai-rag-module/ai_module/app/rag/reranker_client.py`
- [X] T034 [US2] Implement Qdrant collection, upsert, and search facade in `construction-ai-rag-module/ai_module/app/rag/qdrant_service.py`
- [X] T035 [US2] Implement tenant, project, and permission filtering in `construction-ai-rag-module/ai_module/app/rag/permission_filter.py`
- [X] T036 [US2] Implement retrieval orchestration with candidate search, permission filtering, reranking, and context limits in `construction-ai-rag-module/ai_module/app/rag/retrieval_service.py`
- [X] T037 [US2] Implement document ingestion orchestration in `construction-ai-rag-module/ai_module/app/rag/ingestion_service.py`
- [X] T038 [US2] Implement document metadata/chunk persistence and indexing workflow in `construction-ai-rag-module/ai_module/app/rag/document_service.py`
- [X] T039 [US2] Implement `/api/rag/documents` and `/api/rag/search` routes in `construction-ai-rag-module/ai_module/app/main.py`
- [X] T040 [US2] Integrate local RAG path into `construction-ai-rag-module/ai_module/app/agent/decision_service.py`

**Checkpoint**: User Story 2 can answer authorized policy/how-to questions with source-backed Arabic responses.

---

## Phase 5: User Story 3 - Combine Live Data and Policy for Recommendations (Priority: P2)

**Goal**: Use local policy evidence plus gateway-managed live-data plans, then compose final answers from supplied tool results and authorized sources.

**Independent Test**: Ask `هل مشروع العاصمة محتاج تصعيد حسب السياسة؟`, verify `/api/agent/decide` returns local RAG plus a `database_query` plan, then verify `/api/agent/final` returns a mixed Arabic answer with sources and no invented facts.

### Tests for User Story 3

- [X] T041 [P] [US3] Add mixed RAG plus `database_query` decision tests in `construction-ai-rag-module/ai_module/tests/test_agent_decision.py`
- [X] T042 [P] [US3] Add final-answer source inclusion tests in `construction-ai-rag-module/ai_module/tests/test_final_answer.py`
- [X] T043 [P] [US3] Add metric, table, mixed, and insufficient-evidence display tests in `construction-ai-rag-module/ai_module/tests/test_final_answer.py`

### Implementation for User Story 3

- [X] T044 [US3] Implement mixed-question classification in `construction-ai-rag-module/ai_module/app/agent/decision_service.py`
- [X] T045 [US3] Implement final-answer composition in `construction-ai-rag-module/ai_module/app/agent/final_answer_service.py`
- [X] T046 [US3] Implement `/api/agent/final` route in `construction-ai-rag-module/ai_module/app/main.py`

**Checkpoint**: User Story 3 is independently testable with provided gateway tool results and local RAG results.

---

## Phase 6: User Story 4 - Index Construction Documents for Local Retrieval (Priority: P2)

**Goal**: Reliably ingest document content and make authorized chunks searchable only after metadata and vector entries are available.

**Independent Test**: Submit valid and invalid indexing requests, then verify indexed status, chunk payload fields, PostgreSQL metadata, Qdrant vectors, and no partial entries for invalid content.

### Tests for User Story 4

- [X] T047 [P] [US4] Add invalid-content indexing tests in `construction-ai-rag-module/ai_module/tests/test_document_indexing.py`
- [X] T048 [P] [US4] Add vector payload field tests in `construction-ai-rag-module/ai_module/tests/test_document_indexing.py`
- [X] T049 [P] [US4] Add indexed-status transition tests in `construction-ai-rag-module/ai_module/tests/test_document_indexing.py`

### Implementation for User Story 4

- [X] T050 [US4] Add content hashing and duplicate-safe metadata handling in `construction-ai-rag-module/ai_module/app/rag/document_service.py`
- [X] T051 [US4] Add ingestion/index job records in `construction-ai-rag-module/ai_module/app/storage/models.py`
- [X] T052 [US4] Add safe failure handling for indexing jobs in `construction-ai-rag-module/ai_module/app/rag/ingestion_service.py`
- [X] T053 [US4] Ensure document content is never logged at info level in `construction-ai-rag-module/ai_module/app/rag/document_service.py`

**Checkpoint**: User Story 4 provides repeatable document indexing for later RAG search.

---

## Phase 7: User Story 5 - Operate and Monitor the AI Module on the AI Server (Priority: P3)

**Goal**: Provide deployable Server 2 operations, health reporting, model configurability, and security documentation.

**Independent Test**: Start services from Docker Compose, check `/health`, switch model settings through environment variables, run quickstart flows, and verify logs redact configured secrets.

### Tests for User Story 5

- [X] T054 [P] [US5] Add health endpoint dependency-status tests in `construction-ai-rag-module/ai_module/tests/test_health.py`
- [X] T055 [P] [US5] Add token redaction tests in `construction-ai-rag-module/ai_module/tests/test_auth.py`
- [X] T056 [P] [US5] Add configuration override tests in `construction-ai-rag-module/ai_module/tests/test_schemas.py`

### Implementation for User Story 5

- [X] T057 [US5] Implement `/health` dependency status behavior in `construction-ai-rag-module/ai_module/app/main.py`
- [X] T058 [US5] Add vLLM profile and configurable tensor-parallel command options in `construction-ai-rag-module/docker-compose.yml`
- [X] T059 [US5] Document local setup, Docker startup, indexing, search, Spring Boot decide/final flow, fake mode, real vLLM mode, and no-MySQL guarantee in `construction-ai-rag-module/README.md`

**Checkpoint**: User Story 5 supports operator validation from the quickstart.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Validate the full feature, harden security boundaries, and clean up delivery artifacts.

- [X] T060 [P] Verify OpenAPI contract alignment with implemented schemas in `specs/001-server-ai-rag-module/contracts/ai-rag-module.openapi.yaml`
- [X] T061 [P] Verify quickstart commands and examples in `specs/001-server-ai-rag-module/quickstart.md`
- [X] T062 [P] Add `.dockerignore` for Python cache, virtualenv, and test artifacts in `construction-ai-rag-module/.dockerignore`
- [X] T063 Run the full pytest suite from `construction-ai-rag-module/ai_module/`
- [X] T064 Run a no-MySQL audit for forbidden configuration names and dependencies across `construction-ai-rag-module/`
- [X] T065 Run a raw-SQL audit across agent decision outputs and tests in `construction-ai-rag-module/ai_module/`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 Setup**: No dependencies.
- **Phase 2 Foundational**: Depends on Phase 1 and blocks all user stories.
- **Phase 3 US1**: Depends on Phase 2 and is the MVP.
- **Phase 4 US2**: Depends on Phase 2; can run in parallel with US1 after schemas/auth/logging exist.
- **Phase 5 US3**: Depends on US1 and US2 because it combines database plans and RAG evidence.
- **Phase 6 US4**: Depends on Phase 2 and supports US2; can be implemented before or alongside US2 if ingestion ownership is split.
- **Phase 7 US5**: Depends on Phase 2 and can proceed in parallel with feature stories after endpoints exist.
- **Phase 8 Polish**: Depends on all desired stories being complete.

### User Story Dependencies

- **US1 (P1)**: No user-story dependency after foundation.
- **US2 (P1)**: No user-story dependency after foundation.
- **US3 (P2)**: Depends on US1 and US2.
- **US4 (P2)**: Depends on foundation; enables stronger US2 validation.
- **US5 (P3)**: Depends on foundation and is completed after core endpoints exist.

### Parallel Opportunities

- Setup tasks T003-T006 can run in parallel.
- Foundational tasks T010 and T013 can run in parallel after package creation.
- US1 tests T016-T020 can run in parallel before US1 implementation.
- US2 tests T026-T030 and implementation tasks T031-T033 can run in parallel across separate files.
- US3 tests T041-T043 can run in parallel before final-answer implementation.
- US4 tests T047-T049 can run in parallel.
- US5 tests T054-T056 can run in parallel.
- Polish checks T060-T062 can run in parallel before final full-suite validation.

---

## Parallel Examples

### User Story 1

```text
Task: T016 Add auth-required tests in construction-ai-rag-module/ai_module/tests/test_auth.py
Task: T017 Add schema validation tests in construction-ai-rag-module/ai_module/tests/test_schemas.py
Task: T018 Add operational decision tests in construction-ai-rag-module/ai_module/tests/test_agent_decision.py
Task: T019 Add forbidden sensitive-request tests in construction-ai-rag-module/ai_module/tests/test_agent_decision.py
Task: T020 Add no-raw-SQL decision tests in construction-ai-rag-module/ai_module/tests/test_agent_decision.py
```

### User Story 2

```text
Task: T031 Implement chunking in construction-ai-rag-module/ai_module/app/rag/chunking_service.py
Task: T032 Implement embeddings in construction-ai-rag-module/ai_module/app/rag/embedding_client.py
Task: T033 Implement reranking in construction-ai-rag-module/ai_module/app/rag/reranker_client.py
```

### User Story 5

```text
Task: T054 Add health tests in construction-ai-rag-module/ai_module/tests/test_health.py
Task: T055 Add token redaction tests in construction-ai-rag-module/ai_module/tests/test_auth.py
Task: T056 Add configuration override tests in construction-ai-rag-module/ai_module/tests/test_schemas.py
```

---

## Implementation Strategy

### MVP First

1. Complete Phase 1 and Phase 2.
2. Complete Phase 3 User Story 1.
3. Validate `/api/agent/decide` with operational, clarification, forbidden, and no-raw-SQL tests.
4. Demonstrate that Server 2 returns structured `database_query` plans only and never accesses MySQL.

### Incremental Delivery

1. Add US2 for authorized local RAG search and policy answers.
2. Add US4 to harden document ingestion and index-job behavior.
3. Add US3 to combine local RAG with gateway-managed live data.
4. Add US5 operations, health, Docker Compose, and README validation.
5. Finish Phase 8 with full tests, contract alignment, and security audits.

### Validation Gates

1. Every protected endpoint rejects invalid bearer tokens.
2. Every agent decision validates against Pydantic schemas.
3. No decision contains raw SQL or unsupported external tools.
4. RAG search returns zero unauthorized chunks across tenant, project, and permission tests.
5. Final answers with RAG include sources and avoid invented facts.
6. Logs redact module, gateway, and LLM secrets.
