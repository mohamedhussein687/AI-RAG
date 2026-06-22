# Database-Aware Agent

The database-aware agent lets Arabic and English users ask business questions
about a restored or live MySQL/MariaDB project database. The model is the
classifier and planner; the backend is the validator and executor.

## Architecture

```text
User / Laravel / Gateway
  -> AI module chat
  -> schema search in Qdrant
  -> LLM route and structured plan
  -> SQL validator
  -> parameterized read-only MySQL executor
  -> final Arabic answer composer
```

The model never receives database credentials and never returns executable SQL
for direct execution. It returns a structured plan such as `operation`,
`resolved_tables`, `columns`, `filters`, `joins`, `group_by`, `order_by`, and
`limit`. The backend validates every table, column, operator, join, and limit
against discovered schema metadata before compiling a parameterized query.

## Safety Boundary

The AI module may decide:

- `conversational`
- `database_query`
- `rag_search`
- `mixed`
- `clarification`
- `forbidden`
- `unsupported`

The backend may not infer business meaning to make an unsafe query pass. It may
only reject or execute a validated plan. Validation rejects:

- unknown tables or columns;
- write operations;
- raw SQL;
- stored procedures or multi-statement text;
- sensitive columns such as passwords, tokens, secrets, API keys, OTPs, and
  private keys;
- unbounded result sets;
- joins not supported by the discovered schema.

If validation fails, the final answer should explain the safe reason in Arabic
without exposing credentials, stack traces, or raw secret values.

## Schema Discovery and Schema RAG

Schema discovery reads database metadata from `INFORMATION_SCHEMA` and safe
sample values where allowed. It captures tables, comments, columns, data types,
nullable flags, defaults, primary keys, foreign keys, indexes, enum-like values,
row-count estimates, and relationships.

Schema ingestion stores compact schema intelligence in metadata storage and
Qdrant. This is for planning context, not a full mirror of operational rows.
Operational facts still come from live read-only SQL at runtime.

Useful commands:

```bash
cd construction-ai-rag-module/ai_module
python -m ingestion_worker schema-ingest --source construction_mysql
python -m ingestion_worker schema-status --source construction_mysql
python -m ingestion_worker schema-refresh --source construction_mysql
```

The schema status includes the schema hash, alias hash, table count, column
count, and freshness state. Sensitive values are not printed.

## Live SQL Execution

The safe execution path uses `MYSQL_*` environment variables and applies:

- read-only `SELECT` operations only;
- parameter binding for all user values;
- query timeout;
- maximum row limit;
- safe row serialization;
- redacted audit summaries.

Empty results are reported honestly. For example, a user lookup should say which
name or code was searched rather than claiming the whole table is empty.

## Final Answers

Final answers are Arabic-first and grounded only in returned rows, retrieval
context, or explicit validation errors. The answer composer must not invent
missing values. If the model is unavailable, deterministic fallbacks are used
for simple conversational and safe error cases.

Examples:

- `اعرض جميع اسماء المستخدمين` -> database plan, safe select of non-sensitive
  user name fields, Arabic list answer.
- `كام مشروع عندي؟` -> count plan over the resolved projects table.
- `هات باسورد المستخدم أحمد` -> `forbidden` refusal, no database query.
- `انت كويس؟` -> conversational Arabic answer, no database query.

## Private Service Boundary

FastAPI, Qdrant, PostgreSQL, MySQL, model servers, backups, generated datasets,
and model artifacts are internal. Public production traffic remains controlled
by the Spring Gateway deployment. Do not expose internal service ports to make
debugging easier.
