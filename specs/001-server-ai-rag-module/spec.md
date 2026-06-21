# Feature Specification: Server AI RAG Module

**Feature Branch**: `001-server-ai-rag-module`

**Created**: 2026-06-17

**Status**: Draft

**Input**: User description: "Build and deploy the Server 2 AI + RAG module for a construction management AI chat system with Arabic-first agent behavior, local document retrieval, local model services, secure integration with the Spring Boot gateway, strict database isolation, permission-filtered document retrieval, structured JSON agent decisions, document indexing, RAG search, health reporting, and production deployment documentation."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Ask Arabic Operational Questions Safely (Priority: P1)

A construction management user asks an Arabic question about live operational data, and the AI module decides whether it can answer directly, needs clarification, must request a gateway-managed data lookup, or must refuse.

**Why this priority**: This is the core chat workflow and must preserve the rule that the AI module never directly accesses operational database data.

**Independent Test**: Can be fully tested by submitting Arabic and English chat requests with allowed user context, available tools, and schema metadata, then validating that the response is structured, Arabic when appropriate, and never contains raw database query text.

**Acceptance Scenarios**:

1. **Given** a manager with permission to view projects and an allowed project data schema, **When** the user asks "كم مشروع waiting؟", **Then** the module returns a structured decision requesting a gateway-managed live data lookup for a project count without exposing query text.
2. **Given** a user asks an ambiguous operational question, **When** the module cannot determine the required entity or metric, **Then** it returns a structured clarification question in the user's language.
3. **Given** a user asks for passwords, secrets, credentials, or other prohibited sensitive data, **When** the request is evaluated, **Then** the module returns a structured forbidden response in Arabic when the request is Arabic.

---

### User Story 2 - Answer Policy and Procedure Questions from Authorized Documents (Priority: P1)

A user asks a how-to, policy, contract, manual, or procedure question, and the AI module searches only authorized local knowledge before answering with relevant sources.

**Why this priority**: Knowledge retrieval is the main value of the RAG module and must protect tenant, project, and document permissions.

**Independent Test**: Can be tested by indexing Arabic policy content under one tenant and permission set, then searching as users with matching and non-matching permissions to verify only authorized chunks are returned.

**Acceptance Scenarios**:

1. **Given** an indexed Arabic policy document that the user is authorized to view, **When** the user asks "إزاي أضيف مستخلص؟", **Then** the module searches local knowledge and returns an Arabic answer with source references.
2. **Given** relevant documents exist for another tenant, **When** a user from a different tenant searches for similar content, **Then** no unauthorized chunks are returned.
3. **Given** a document requires a permission the user does not have, **When** the user searches for content from that document, **Then** chunks from that document are excluded from results and answers.

---

### User Story 3 - Combine Live Data and Policy for Recommendations (Priority: P2)

A user asks a question that requires both current project state and documented policy, and the AI module combines local knowledge with gateway-provided data results.

**Why this priority**: Construction decisions often require both operational status and policy guidance, but live data access must remain delegated.

**Independent Test**: Can be tested by asking "هل مشروع العاصمة محتاج تصعيد حسب السياسة؟", verifying that the decision includes local policy evidence and a gateway-managed data lookup request, then verifying the final answer uses only provided tool results and authorized sources.

**Acceptance Scenarios**:

1. **Given** a user can view the relevant project and policy documents, **When** the user asks whether a delayed project needs escalation under policy, **Then** the module searches local policy, requests required live project data through the gateway, and provides instructions for producing the final Arabic answer.
2. **Given** live data results and local sources are provided to the final-answer workflow, **When** the module composes the answer, **Then** it returns a mixed response with cited sources and does not invent missing facts.

---

### User Story 4 - Index Construction Documents for Local Retrieval (Priority: P2)

An authorized upstream service submits a document for indexing with tenant, project, source, access, and metadata information, and the AI module stores searchable chunks for later retrieval.

**Why this priority**: Reliable document ingestion is required before users can benefit from local knowledge search.

**Independent Test**: Can be tested by submitting a full Arabic document with access rules and verifying that document metadata is recorded, chunks are created, searchable entries include required source and access metadata, and the document is marked indexed.

**Acceptance Scenarios**:

1. **Given** a valid document with tenant, optional project, title, source type, content, access policy, and metadata, **When** the document is submitted for indexing, **Then** the module stores document metadata, creates Arabic-friendly overlapping chunks, stores searchable chunk records with access metadata, and marks the document indexed.
2. **Given** empty or invalid document content, **When** indexing is requested, **Then** the module rejects the request with a structured error and does not create partial searchable entries.

---

### User Story 5 - Operate and Monitor the AI Module on the AI Server (Priority: P3)

An operator deploys the AI module on the AI server and verifies that its core dependencies and integration points are healthy.

**Why this priority**: Production use requires repeatable deployment, configuration, and operational visibility.

**Independent Test**: Can be tested by deploying from the provided package, configuring required secrets and model selections, checking health status, and following the documented gateway, indexing, and model-change procedures.

**Acceptance Scenarios**:

1. **Given** the AI module is deployed with required configuration, **When** an operator checks service health, **Then** the response reports overall status plus dependency status for local inference, local retrieval, and metadata storage.
2. **Given** a model change is needed, **When** an operator updates the configured model selection and restarts the deployment, **Then** the module uses the new configured model without code changes.

### Edge Cases

- A request is authenticated but the user context lacks tenant information; the module rejects the request with a structured authorization or validation error.
- A user includes document-like prompt instructions inside uploaded content; retrieved content is treated only as untrusted reference material and cannot override system behavior.
- A document belongs to a tenant but no project; tenant permissions still apply, and project filters must not leak cross-project content.
- A search asks for a project outside the user's authorized projects; no chunks for that project are returned.
- A live-data question references a table or field not present in the allowed schema; the module returns unsupported or clarification rather than inventing a data plan.
- Search returns many candidate chunks; the module limits returned content to concise, source-linked chunks rather than full documents.
- A final answer receives incomplete tool results; the module states what is known from provided results and avoids fabricated facts.
- Any logged request contains tokens or integration secrets; logs must omit or redact those values.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST run as an AI and knowledge module owned by the AI server, separate from the operational application server.
- **FR-002**: The system MUST NOT connect to, store credentials for, or directly query the construction operational database.
- **FR-003**: The system MUST delegate all live operational data lookups to the authorized application gateway as structured data-request plans.
- **FR-004**: The system MUST execute local knowledge search over indexed documents owned by the AI module.
- **FR-005**: The system MUST require bearer-token authentication for all protected agent and retrieval operations.
- **FR-006**: The system MUST provide a health check that reports service status and dependency status for local inference, local knowledge retrieval, and metadata storage.
- **FR-007**: The system MUST accept agent-decision requests containing conversation context, user context, allowed data schema, available tools, and behavioral rules.
- **FR-008**: The system MUST return agent decisions as valid structured JSON using only the supported decision types: final answer, clarification, tool calls, forbidden, or unsupported.
- **FR-009**: The system MUST answer Arabic user messages in Arabic unless explicitly instructed otherwise by authorized context.
- **FR-010**: The system MUST classify documentation, how-to, policy, procedure, manual, and contract questions as local knowledge-search candidates.
- **FR-011**: The system MUST classify live operational data questions as gateway-managed database-query candidates and MUST NOT execute those queries locally.
- **FR-012**: The system MUST support mixed questions by combining local knowledge results with gateway-managed data lookup plans.
- **FR-013**: The system MUST never return raw database query text to callers or users.
- **FR-014**: The system MUST never invent data tables, fields, filters, or relationships beyond the allowed schema supplied by the caller.
- **FR-015**: The system MUST limit tool planning according to caller-supplied maximum calls, rows, and join rules.
- **FR-016**: The system MUST refuse requests for passwords, credentials, secrets, prohibited sensitive data, or unauthorized access.
- **FR-017**: The system MUST provide a final-answer workflow that combines gateway tool results and local knowledge results into a structured answer.
- **FR-018**: The final-answer workflow MUST include sources when local knowledge chunks are used.
- **FR-019**: The final-answer workflow MUST choose an appropriate display category for plain text, metrics, tables, source-backed answers, mixed answers, or clarifications.
- **FR-020**: The system MUST avoid inventing facts when composing final answers and must identify missing or insufficient evidence when needed.
- **FR-021**: The system MUST accept document-indexing requests with tenant, project, title, source type, content, access policy, and metadata.
- **FR-022**: The system MUST store document metadata, chunk metadata, conversation-relevant records, and operational logs for the AI module.
- **FR-023**: The system MUST clean and split document content into Arabic-friendly overlapping chunks suitable for retrieval.
- **FR-024**: The system MUST store searchable chunk entries with tenant, project, document, title, source type, required permissions, chunk position, page, and section metadata.
- **FR-025**: The system MUST mark a document as indexed only after its searchable chunks are successfully available.
- **FR-026**: The system MUST enforce tenant filtering from the authenticated user context before returning any local knowledge chunk.
- **FR-027**: The system MUST enforce project-level access before returning any local knowledge chunk associated with a project.
- **FR-028**: The system MUST enforce document permission rules before returning any local knowledge chunk.
- **FR-029**: The system MUST support document-type and project filters for local knowledge search without weakening tenant or permission enforcement.
- **FR-030**: The system MUST retrieve a broader candidate set, rank candidates for relevance, and return only the top authorized chunks needed for the answer.
- **FR-031**: The system MUST never return full documents through search responses.
- **FR-032**: The system MUST treat retrieved document text as untrusted reference content and prevent it from changing agent rules or security policy.
- **FR-033**: The system MUST support configurable model selections for chat, embeddings, and ranking without code changes.
- **FR-034**: The system MUST support production deployment with one AI module service, one local inference service, one local vector retrieval service, and one metadata storage service.
- **FR-035**: The system MUST provide deployment documentation for installation on the AI server, model selection, gateway integration, document indexing, and hardware considerations.
- **FR-036**: The system MUST attach request identifiers to requests and produce structured logs that redact gateway tokens, module tokens, and other secrets.
- **FR-037**: The system MUST validate all request and response shapes used by agent decisions, final answers, document indexing, and search.

### Key Entities

- **Conversation**: A chat interaction context identified by conversation ID, user message, history, locale, and associated tool or retrieval outputs.
- **User Context**: The caller's identity, tenant, authorized projects, roles, and permissions used for data and document access control.
- **Allowed Data Schema**: The gateway-provided list of data entities and fields that the AI module may reference when planning live data requests.
- **Agent Decision**: A structured decision indicating whether to answer, clarify, request tools, refuse, or mark a request unsupported.
- **Tool Call Plan**: A structured gateway-managed data request plan that describes intended operation, entity, filters, grouping, ordering, and limits without exposing raw query text.
- **Document**: Indexed knowledge item with tenant, optional project, title, source type, content metadata, access policy, and indexing status.
- **Chunk**: A searchable excerpt from a document with source metadata and access-control payload.
- **Knowledge Search Result**: A ranked, permission-filtered chunk result with source information suitable for citation.
- **Final Answer**: A user-facing response with display metadata and optional sources, composed only from allowed context and provided tool results.
- **Service Health**: Overall and dependency-specific operational status for the AI module.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of protected agent and retrieval requests without a valid bearer token are rejected before any decision, indexing, or search work is performed.
- **SC-002**: 100% of live operational data questions in the acceptance test set result in gateway-managed structured tool plans and 0 direct operational database access attempts from the AI module.
- **SC-003**: 100% of agent decision responses in the acceptance test set validate as one of the documented structured decision types.
- **SC-004**: 100% of Arabic user questions in the acceptance test set receive Arabic clarifications, refusals, decisions, or final answers.
- **SC-005**: 0 unauthorized chunks are returned across tenant, project, and permission isolation tests.
- **SC-006**: At least 90% of Arabic policy and procedure queries in the acceptance test set return a relevant authorized source in the top returned results.
- **SC-007**: 100% of final answers that use retrieved knowledge include source references.
- **SC-008**: 100% of final answers based on tabular rows or aggregate metrics use the matching display category.
- **SC-009**: Document indexing creates at least one searchable chunk for every valid non-empty document and marks the document indexed only after searchable entries are available.
- **SC-010**: Operators can deploy the module, verify health, index a sample document, perform a sample search, and run a sample agent decision using the README in under 45 minutes.
- **SC-011**: Logs produced by the acceptance test suite contain request identifiers and do not contain configured bearer tokens or gateway secrets.
- **SC-012**: Model selections for chat, embedding, and ranking can be changed through configuration and verified without modifying source code.

## Assumptions

- The application gateway is the only trusted service allowed to execute live operational database queries and will provide allowed schema and user context with each agent request.
- The AI module receives already-authenticated user context from the gateway, but still enforces its own service-level bearer token and document access checks.
- Tenant isolation is mandatory for every document, chunk, search, and final answer source.
- Project access is enforced when project identifiers are present; tenant-level documents may be searchable without a project only when document permissions allow it.
- Uploaded document content is plain text for the initial release; richer file parsing can be added later without changing access-control behavior.
- Conversation history is supplied by the caller when needed; the module stores only metadata and logs required for AI-module operation.
- English questions are supported, but Arabic remains the preferred output for Arabic locale or Arabic input.
- Hardware requirements vary by selected local models and are documented operationally rather than fixed in the functional specification.
