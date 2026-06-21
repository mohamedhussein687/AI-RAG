# Research: Server AI RAG Module

## Decision: Python 3.11+ FastAPI service with Pydantic v2 schemas

**Rationale**: The requested module is an HTTP service with strict request and response contracts. FastAPI and Pydantic v2 provide explicit validation, OpenAPI generation, async request handling, and a small operational footprint for Server 2.

**Alternatives considered**: A monolithic script-based service was rejected because the gateway needs stable HTTP contracts. A different backend runtime was rejected because the requested stack and local AI ecosystem are Python-centered.

## Decision: Strict bearer-token service authentication

**Rationale**: Server 2 should only accept calls from the trusted gateway or authorized internal callers. A single `AI_MODULE_TOKEN` gate is sufficient for service-to-service authentication in the initial scope, while user-level authorization is enforced from the supplied `user_context`.

**Alternatives considered**: User JWT validation on Server 2 was rejected for v1 because the gateway already owns user authentication and can provide normalized context. No service token was rejected because it would expose indexing and agent endpoints to accidental internal callers.

## Decision: No direct construction database access on Server 2

**Rationale**: The security boundary requires Spring Boot on Server 1 to remain the only service that can execute operational data queries. Server 2 only returns structured `database_query` plans using caller-provided schema metadata.

**Alternatives considered**: Read-only MySQL access was rejected because it violates the architecture and creates credential leakage risk. SQL generation was rejected because raw SQL must never be returned.

## Decision: Use structured tool-call plans instead of SQL

**Rationale**: Plans with operation, table, column, filters, grouping, ordering, and limits are expressive enough for the gateway to validate and translate while preventing SQL exposure and arbitrary query generation.

**Alternatives considered**: Natural-language tool instructions were rejected because they are hard to validate. SQL strings were rejected by requirement.

## Decision: Qdrant for local vector search with payload filters

**Rationale**: Qdrant supports vector search plus metadata payload filtering for tenant, project, source type, and document identifiers. It fits the local vector-search requirement and Docker Compose deployment model.

**Alternatives considered**: PostgreSQL-only vector search was rejected because the requested architecture explicitly includes Qdrant. In-memory vector search was rejected because indexed documents must survive restarts.

## Decision: PostgreSQL stores AI module metadata only

**Rationale**: PostgreSQL will hold documents, chunk records, indexing status, conversations, and structured logs. This keeps AI metadata local while avoiding any construction operational database credentials.

**Alternatives considered**: Storing all metadata in Qdrant payloads was rejected because document status, ingestion errors, and conversation/log records need relational metadata. File-only metadata was rejected for production operations.

## Decision: Dual permission enforcement for RAG

**Rationale**: Search should apply tenant/project/document constraints before and after vector retrieval. Qdrant filters reduce the candidate set, and application-level filtering prevents unauthorized chunks from leaking if payloads are incomplete or malformed.

**Alternatives considered**: Qdrant-only filtering was rejected because application-level security checks are easier to test and audit. Post-filter-only retrieval was rejected because it wastes retrieval capacity and risks poor relevance under strict permissions.

## Decision: Arabic-friendly chunking with overlap

**Rationale**: Arabic construction documents often include long paragraphs, headings, lists, and mixed Arabic-English identifiers. Chunking should normalize whitespace, preserve section hints, split on headings and sentence boundaries where possible, target roughly 700-1000 tokens, and preserve overlap for context continuity.

**Alternatives considered**: Fixed character splitting was rejected because it can split Arabic clauses and headings poorly. Whole-document retrieval was rejected because search responses must not return full documents.

## Decision: Embedding and reranking clients are interface-based

**Rationale**: The initial implementation can run embedding and reranking inside the API process or through local model endpoints. Stable `EmbeddingClient` and `RerankerClient` interfaces keep the service external-ready for dedicated embedding/reranker services later.

**Alternatives considered**: Hard-coding in-process model calls was rejected because the requested deployment keeps optional external services open. Remote third-party embedding APIs were rejected because the requirement is local embeddings.

## Decision: vLLM OpenAI-compatible endpoint for chat inference

**Rationale**: The gateway-facing API can use a standard OpenAI-compatible chat client while vLLM serves configurable local chat models. This supports the default Qwen model and larger alternatives without changing application code.

**Alternatives considered**: Custom model invocation code was rejected because OpenAI-compatible APIs simplify client code and testing. Cloud-only chat inference was rejected because the requirement is local inference on Server 2.

## Decision: JSON guard around agent model outputs

**Rationale**: `/api/agent/decide` must always return one supported structured JSON shape. The decision service should validate LLM output, repair only safe syntactic issues, reject unsupported shapes, and fall back to clarification or unsupported responses when validation fails.

**Alternatives considered**: Trusting model output was rejected because malformed JSON would break the gateway. Free-form answers from the decision endpoint were rejected because the gateway needs machine-readable decisions.

## Decision: Docker Compose deployment package

**Rationale**: The requested Server 2 deployment has four required services: API, chat inference, vector search, and metadata storage. Docker Compose gives operators a repeatable single-host deployment with environment-based model changes.

**Alternatives considered**: Bare-metal service installation was rejected for v1 because it is slower to reproduce. Kubernetes was rejected because the requested deployment is a Server 2 module and Compose is sufficient for the initial production-oriented package.

## Decision: Test with mocked model clients and local service boundaries

**Rationale**: Core correctness depends on auth, schemas, permission filtering, tool classification, source handling, and no-SQL behavior. These can be tested deterministically with mocked LLM/embedding/reranker clients and without requiring large GPU models in CI.

**Alternatives considered**: End-to-end tests against full Qwen models were rejected as mandatory CI tests because they are hardware-dependent. Manual-only testing was rejected because security behavior must be repeatable.
