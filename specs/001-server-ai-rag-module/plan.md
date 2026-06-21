# Implementation Plan: Server AI RAG Module

**Branch**: `001-server-ai-rag-module` | **Date**: 2026-06-17 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/001-server-ai-rag-module/spec.md`

## Summary

Build a production-oriented AI and RAG module under `construction-ai-rag-module/` for Server 2. The module exposes authenticated FastAPI endpoints for health, agent decisions, final answer composition, document indexing, and local RAG search. It keeps all live construction database access on Server 1 by returning structured `database_query` plans only, while executing local knowledge search against Qdrant with PostgreSQL metadata, local embeddings, local reranking, and OpenAI-compatible chat inference through vLLM. Arabic-first behavior, strict permission filtering, JSON-only agent decisions, secret-redacted structured logging, and Docker Compose deployment are mandatory.

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**: FastAPI, Pydantic v2, httpx, uvicorn, SQLAlchemy async, asyncpg, qdrant-client, OpenAI-compatible HTTP client, pytest, pytest-asyncio, respx or pytest-httpx

**Storage**: PostgreSQL for document/chunk/conversation/log metadata; Qdrant for local vector search; no construction MySQL connection or credentials

**Testing**: pytest with async API tests, schema validation tests, mocked LLM/embedding/reranker/gateway clients, and isolated permission-filtering tests

**Target Platform**: Linux Server 2 deployment through Docker Compose with GPU availability determined by selected local models

**Project Type**: Standalone backend web service plus deployment package

**Performance Goals**: Search retrieves candidate chunks, filters permissions, reranks, and returns final chunks within acceptable interactive chat latency; exact latency depends on selected local models and GPU capacity. Health and auth checks should be lightweight and deterministic.

**Constraints**: Arabic-first responses for Arabic input; all protected endpoints require `Authorization: Bearer AI_MODULE_TOKEN`; never access construction MySQL; never store Spring or Laravel secrets in logs; never return raw SQL; always validate structured response schemas; retrieved documents are untrusted reference content.

**Scale/Scope**: Initial service supports one AI module API, one vLLM chat service, one Qdrant service, one PostgreSQL metadata service, local-ready embedding/reranking interfaces, document indexing, local search, and the agent decision/final-answer workflow needed by Spring Boot Gateway.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

The current constitution file contains placeholder principles only, so there are no project-level gates to enforce. This plan applies feature-specific gates from the specification:

- **Database isolation**: PASS. Construction MySQL access remains outside Server 2; Server 2 returns `database_query` plans only.
- **Access control**: PASS. Tenant, project, and document permission filtering are required before returning chunks or sources.
- **Structured outputs**: PASS. Agent decision and final-answer schemas are defined and contract-tested.
- **Observability without secret leakage**: PASS. Request IDs and structured logs are required with token redaction.
- **Test coverage for security behavior**: PASS. The plan includes auth, tenant isolation, permission isolation, schema validation, and forbidden-request tests.

## Project Structure

### Documentation (this feature)

```text
specs/001-server-ai-rag-module/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── ai-rag-module.openapi.yaml
└── tasks.md
```

### Source Code (repository root)

```text
construction-ai-rag-module/
├── docker-compose.yml
├── .env.example
├── README.md
└── ai_module/
    ├── pyproject.toml
    ├── app/
    │   ├── main.py
    │   ├── config.py
    │   ├── auth.py
    │   ├── schemas.py
    │   ├── agent/
    │   │   ├── decision_service.py
    │   │   ├── final_answer_service.py
    │   │   ├── prompt_builder.py
    │   │   └── json_guard.py
    │   ├── rag/
    │   │   ├── document_service.py
    │   │   ├── ingestion_service.py
    │   │   ├── chunking_service.py
    │   │   ├── embedding_client.py
    │   │   ├── reranker_client.py
    │   │   ├── qdrant_service.py
    │   │   ├── retrieval_service.py
    │   │   └── permission_filter.py
    │   ├── storage/
    │   │   ├── postgres.py
    │   │   ├── models.py
    │   │   └── migrations/
    │   ├── clients/
    │   │   ├── llm_client.py
    │   │   └── spring_client.py
    │   └── common/
    │       ├── errors.py
    │       └── logging.py
    └── tests/
        ├── test_health.py
        ├── test_auth.py
        ├── test_document_indexing.py
        ├── test_rag_search.py
        ├── test_agent_decision.py
        ├── test_final_answer.py
        └── test_schemas.py
```

**Structure Decision**: Use the user-requested `construction-ai-rag-module/` deployment package as the feature root. Keep all application code under `ai_module/app/`, colocate tests under `ai_module/tests/`, and keep deployment and operator documentation at the package root.

## Complexity Tracking

No constitution violations identified.

## Phase 0: Research

Research completed in [research.md](./research.md). Key decisions:

- Use FastAPI/Pydantic v2 with strict discriminated schemas for all agent decisions.
- Use Qdrant payload filters plus an application-level permission filter so unauthorized chunks cannot be returned if vector payloads drift.
- Use PostgreSQL metadata for documents, chunks, conversations, and logs while keeping all construction operational data outside Server 2.
- Use vLLM OpenAI-compatible chat inference and configuration-driven model names.
- Implement embedding and reranking behind local interfaces that can run in-process first and move to dedicated services later.

## Phase 1: Design & Contracts

Design artifacts generated:

- [data-model.md](./data-model.md)
- [contracts/ai-rag-module.openapi.yaml](./contracts/ai-rag-module.openapi.yaml)
- [quickstart.md](./quickstart.md)

## Post-Design Constitution Check

The Phase 1 design preserves the pre-design gates:

- **Database isolation**: PASS. Contracts include `database_query` plans but no SQL endpoint or MySQL configuration.
- **Access control**: PASS. Data model and search contract carry tenant, project, and permission fields used for filtering.
- **Structured outputs**: PASS. OpenAPI contracts define all decision variants and final answer display types.
- **Observability without secret leakage**: PASS. Quickstart includes log redaction validation.
- **Test coverage for security behavior**: PASS. Quickstart and future tasks cover auth, tenant isolation, permission isolation, forbidden requests, and schema validation.
