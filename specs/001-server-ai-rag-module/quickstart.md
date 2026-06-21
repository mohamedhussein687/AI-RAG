# Quickstart: Server AI RAG Module

This guide validates the planned Server 2 AI and RAG module after implementation.

## Prerequisites

- Linux host for Server 2 with Docker and Docker Compose.
- GPU capacity appropriate for the selected chat, embedding, and reranking models.
- Spring Boot Gateway base URL and service token for Server 1 integration.
- A generated `AI_MODULE_TOKEN` shared only with the gateway or trusted internal callers.

## 1. Configure the module

```bash
cd construction-ai-rag-module
cp .env.example .env
```

Set at minimum:

```text
AI_MODULE_TOKEN=change-me
SPRING_GATEWAY_BASE_URL=http://server-1-gateway:8080
SPRING_GATEWAY_TOKEN=change-me

CHAT_MODEL=Qwen/Qwen3-30B-A3B-Instruct-2507
LLM_BASE_URL=http://vllm-chat:8100/v1
LLM_API_KEY=local-key
LLM_TEMPERATURE=0

EMBEDDING_MODEL=Qwen/Qwen3-Embedding-4B
RERANKER_MODEL=Qwen/Qwen3-Reranker-4B

QDRANT_URL=http://qdrant:6333
POSTGRES_URL=postgresql+asyncpg://ai:ai@postgres:5432/ai_rag
```

To change the chat model, update `CHAT_MODEL` and any vLLM tensor-parallel environment values, then restart the deployment.

## 2. Start services

```bash
docker compose up -d --build
```

Expected services:

- `ai-module-api`
- `vllm-chat`
- `qdrant`
- `postgres`

Optional embedding and reranking services may be added later without changing the public API contract.

## 3. Check health

```bash
curl http://localhost:8000/health
```

Expected outcome:

- Response contains `status`.
- Response contains dependency entries for local inference, vector search, and metadata storage.

## 4. Verify auth is required

```bash
curl -i -X POST http://localhost:8000/api/rag/search   -H 'Content-Type: application/json'   -d '{"query":"test","user_context":{"tenant_id":"3","permissions":["docs.view"]}}'
```

Expected outcome:

- HTTP 401.
- No search work is performed.

## 5. Index an Arabic policy document

```bash
curl -X POST http://localhost:8000/api/rag/documents   -H "Authorization: Bearer $AI_MODULE_TOKEN"   -H 'Content-Type: application/json'   -d '{
    "tenant_id": "3",
    "project_id": "22",
    "title": "سياسة إدارة تأخير المشاريع",
    "source_type": "policy",
    "content": "عند تأخر المشروع يجب مراجعة سبب التأخير وتوثيق المخاطر ورفع التصعيد حسب مدة التأخير وتأثيره على الجدول الزمني.",
    "access_policy": {
      "permissions": ["docs.view", "policies.view"]
    },
    "metadata": {
      "version": 1
    }
  }'
```

Expected outcome:

- Response status is indexed.
- `chunks_indexed` is at least 1.
- Metadata and searchable vector payload include tenant, project, document, source, permission, chunk, page, and section fields where available.

## 6. Search with authorized context

```bash
curl -X POST http://localhost:8000/api/rag/search   -H "Authorization: Bearer $AI_MODULE_TOKEN"   -H 'Content-Type: application/json'   -d '{
    "query": "خطوات التعامل مع تأخر المشروع",
    "user_context": {
      "tenant_id": "3",
      "project_ids": ["22"],
      "permissions": ["docs.view", "policies.view"]
    },
    "top_k": 5,
    "filters": {
      "document_types": ["policy", "manual"],
      "project_id": "22"
    }
  }'
```

Expected outcome:

- Results contain authorized excerpts only.
- Results do not contain full documents.
- Returned chunks include source metadata.

## 7. Verify tenant and permission isolation

Repeat the previous search with:

- `tenant_id` changed to another tenant.
- `permissions` changed to omit `policies.view`.
- `project_ids` changed to exclude `22`.

Expected outcome:

- No unauthorized chunks are returned.

## 8. Validate live data decision

```bash
curl -X POST http://localhost:8000/api/agent/decide   -H "Authorization: Bearer $AI_MODULE_TOKEN"   -H 'Content-Type: application/json'   -d '{
    "conversation_id": "conv_123",
    "message": "كم مشروع waiting؟",
    "locale": "ar",
    "conversation_history": [],
    "user_context": {
      "id": "15",
      "tenant_id": "3",
      "roles": ["manager"],
      "permissions": ["projects.view", "docs.view"]
    },
    "allowed_schema": {
      "tables": [
        {
          "name": "projects",
          "columns": ["id", "status", "tenant_id"],
          "allowed_operations": ["count", "list"]
        }
      ]
    },
    "available_tools": [
      {"name": "database_query"},
      {"name": "knowledge_search"}
    ],
    "rules": {
      "return_sql": false,
      "max_tool_calls": 5,
      "max_rows": 100,
      "joins_allowed": false
    }
  }'
```

Expected outcome:

- Response type is `tool_calls`.
- Tool is `database_query`.
- Plan uses allowed schema only.
- Response contains no raw SQL.

## 9. Validate RAG-only decision

Ask:

```text
إزاي أضيف مستخلص؟
```

Expected outcome:

- The decision uses local knowledge search or returns a source-backed final answer.
- Arabic output is used.
- Any returned local RAG chunks are authorized.

## 10. Validate mixed decision and final answer

Ask:

```text
هل مشروع العاصمة محتاج تصعيد حسب السياسة؟
```

Expected outcome for `/api/agent/decide`:

- Local policy evidence is included when available.
- A `database_query` tool call is returned for live project state.

Then call `/api/agent/final` with gateway tool results and local RAG results.

Expected outcome:

- Response `display.type` is `mixed`.
- Answer is Arabic.
- Sources are included when RAG chunks are used.
- Missing facts are not invented.

## 11. Validate forbidden behavior

Ask for passwords, credentials, secrets, or unauthorized sensitive data.

Expected outcome:

- Response type is `forbidden`.
- Arabic requests receive Arabic refusal text.
- No tool call is generated.

## 12. Run automated tests

From the module directory:

```bash
cd construction-ai-rag-module/ai_module
pytest
```

Required test coverage:

- Health endpoint.
- Auth required.
- Document indexing creates chunks.
- RAG search respects tenant ID.
- RAG search respects permissions.
- Arabic query retrieves Arabic chunks.
- Decision returns `database_query` for "كم مشروع waiting؟".
- Decision uses local RAG for "إزاي أضيف مستخلص؟".
- Decision uses both RAG and `database_query` for "هل مشروع العاصمة محتاج تصعيد حسب السياسة؟".
- Forbidden response for password and sensitive requests.
- Final answer includes sources when RAG is used.
- Output schemas validate.

## 13. Validate logging

Inspect service logs after the tests.

Expected outcome:

- Logs include request IDs.
- Logs do not include `AI_MODULE_TOKEN`, `SPRING_GATEWAY_TOKEN`, Laravel secrets, Spring secrets, or raw SQL.
