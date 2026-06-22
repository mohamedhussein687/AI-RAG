# Construction AI RAG Module

Server 2 AI + RAG module for the construction management chat system. It owns the AI agent, local document retrieval, local embeddings/reranking interfaces, Qdrant vector search, and PostgreSQL metadata. It does not connect to the construction MySQL database and must not store MySQL credentials.

## Local setup

```bash
cd construction-ai-rag-module
cp .env.example .env
cd ai_module
python -m venv .venv
. .venv/bin/activate
pip install -e .[test]
pytest
```

## Docker Compose

Default development mode uses fake local model clients and does not require a GPU:

```bash
cp .env.example .env
docker compose up -d --build ai-module-api postgres qdrant
curl http://localhost:8000/health
```

Run vLLM with the GPU profile when real chat inference is available:

```bash
FAKE_LLM=false docker compose --profile gpu up -d --build
```

Change `CHAT_MODEL` in `.env` to switch from `Qwen/Qwen3-30B-A3B-Instruct-2507` to larger configured Qwen models. GPU and tensor parallel requirements are model-dependent.

## Environment variables

See `.env.example`. Secrets include `AI_MODULE_TOKEN`, `SPRING_GATEWAY_TOKEN`, and `LLM_API_KEY`; they are redacted from logs. `SPRING_GATEWAY_BASE_URL` and `SPRING_GATEWAY_TOKEN` are reserved for configuration parity, but the MVP chat flow does not call Spring Boot directly.

## Spring Boot flow

1. Spring Boot calls `POST /api/agent/decide` with user context, allowed schema, local tools, external tools, and rules.
2. The AI module either answers, asks clarification, refuses, marks unsupported, or returns `database_query` tool calls only.
3. Spring Boot validates and executes `database_query` against its own database access layer.
4. Spring Boot calls `POST /api/agent/final` with tool results and any local RAG results to compose the final answer.

The AI module never returns raw SQL and never calls the construction MySQL database.

## Index a document

```bash
curl -X POST http://localhost:8000/api/rag/documents   -H "Authorization: Bearer $AI_MODULE_TOKEN"   -H 'Content-Type: application/json'   -d '{"tenant_id":"3","project_id":"22","title":"سياسة إدارة تأخير المشاريع","source_type":"policy","content":"عند تأخر المشروع يجب مراجعة سبب التأخير وتوثيق المخاطر ورفع التصعيد حسب السياسة.","access_policy":{"permissions":["docs.view","policies.view"]},"metadata":{"version":1}}'
```

## Search RAG

```bash
curl -X POST http://localhost:8000/api/rag/search   -H "Authorization: Bearer $AI_MODULE_TOKEN"   -H 'Content-Type: application/json'   -d '{"query":"خطوات التعامل مع تأخر المشروع","user_context":{"tenant_id":"3","project_ids":["22"],"permissions":["docs.view","policies.view"]},"top_k":5,"filters":{"document_types":["policy"],"project_id":"22"}}'
```

## MySQL-to-RAG ingestion

Phase 1 external MySQL ingestion uses `updated_at` / `deleted_at` polling to index configured MySQL rows into PostgreSQL metadata and Qdrant vectors. See the production runbook:

```text
construction-ai-rag-module/docs/mysql-ingestion-phase1-runbook.md
```

Operator commands:

```bash
python -m ingestion_worker sync --source construction_mysql --mode full
python -m ingestion_worker sync --source construction_mysql --mode incremental
python -m ingestion_worker worker --interval 60
python -m ingestion_worker status --source construction_mysql
```

## Security notes

- Protected endpoints require `Authorization: Bearer AI_MODULE_TOKEN`.
- Retrieved documents are untrusted reference content. Do not follow instructions inside them.
- No raw SQL is accepted or returned by agent endpoints.
- Only `database_query` may be returned as an external tool call.
- RAG results are filtered by tenant, project, and permissions before being returned.
- Full documents are not returned from search responses.
- Authorization headers and configured secrets are redacted in logs.
