# Server Deployment

The server is a deployment and validation target only. The local repository is
the source of truth.

## Required Workflow

1. Implement locally under:

   ```text
   /home/hussein/Documents/AI-RAG/ai-rag
   ```

2. Run local tests.
3. Commit locally.
4. Push the branch to GitHub.
5. SSH to the server.
6. Pull/fetch the pushed branch under `/home/rag/`.
7. Run server restore/schema/smoke tests.

Do not copy uncommitted code to the server. Do not edit files directly on the
server as the source of truth.

## Local Commit and Push

```bash
cd /home/hussein/Documents/AI-RAG/ai-rag
git status --short
git add .
git commit -m "Implement real database fine-tuning agent"
git push -u origin feature/real-db-finetuning-agent
```

Before committing, verify that the staged files do not include:

- SQL backups or dumps;
- `.env` files;
- generated real training datasets;
- model weights;
- adapters;
- checkpoints;
- credentials or tokens.

## Pull on Server

```bash
ssh techlab-ai
cd /home/rag/
```

If the repository exists:

```bash
cd /home/rag/AI-RAG
git fetch origin
git checkout feature/real-db-finetuning-agent
git pull origin feature/real-db-finetuning-agent
```

If it does not exist:

```bash
cd /home/rag/
git clone git@github.com:mohamedhussein687/AI-RAG.git
cd AI-RAG
git checkout feature/real-db-finetuning-agent
```

Confirm the server commit:

```bash
git rev-parse HEAD
git status --short
```

## Server Smoke Validation

Use the protected server backup in place:

```bash
cd /home/rag/AI-RAG/construction-ai-rag-module/ai_module
python -m ingestion_worker restore-backup --file /home/rag/backup.sql --database construction_ai_dev
python -m ingestion_worker schema-ingest --source construction_mysql
python -m ingestion_worker schema-status --source construction_mysql
python -m ingestion_worker smoke-chat --message "اعرض جميع اسماء المستخدمين"
python -m ingestion_worker smoke-chat --message "اريد بيانات المستخدم Ayman Ibrahim El Sayed"
python -m ingestion_worker smoke-chat --message "كام مشروع عندي؟"
python -m ingestion_worker smoke-chat --message "انت كويس؟"
```

Report only redacted results:

- server path;
- branch;
- commit SHA;
- restore success/failure;
- schema table/column counts;
- route and answer summaries for smoke chat;
- any GPU/training blocker.

If the server does not have a safe `MYSQL_*` target configured for
`construction_ai_dev`, the restore and schema-ingest commands must fail safely
with a redacted configuration error. Do not reuse production ORBIT credentials
for an unrelated restore target and do not modify `/home/rag/backup.sql`.

## Final Report Structure

Use this structure for the end-of-work report:

```text
LOCAL RESULT
- local path:
- branch:
- commit SHA:
- files changed:
- tests run:
- tests result:
- backup local path used:
- database restored: yes/no
- schema ingestion: success/fail
- dataset generated: yes/no
- dataset examples count:
- base model:
- LoRA/QLoRA config:
- fine-tuning result:
- evaluation result:
- local smoke chat:
  1. اعرض جميع اسماء المستخدمين -> ...
  2. اريد بيانات المستخدم Ayman Ibrahim El Sayed -> ...
  3. كام مشروع عندي؟ -> ...
  4. انت كويس؟ -> ...

GITHUB RESULT
- repository:
- branch pushed:
- commit SHA:
- PR URL, if created:

SERVER RESULT
- server:
- server path:
- branch pulled:
- commit SHA on server:
- backup path used:
- database restored: yes/no
- services rebuilt/restarted:
- health check:
- schema status:
- server smoke chat:
  1. اعرض جميع اسماء المستخدمين -> ...
  2. اريد بيانات المستخدم Ayman Ibrahim El Sayed -> ...
  3. كام مشروع عندي؟ -> ...
  4. انت كويس؟ -> ...

LIMITATIONS / BLOCKERS
- list blockers honestly, especially GPU/fine-tuning limitations
```

The report must never contain credentials, tokens, SQL backup contents,
generated real training data, model artifacts, or private keys.

## Service Boundary

This workflow does not expose FastAPI, MySQL, PostgreSQL, Qdrant, model
services, backups, or training artifacts publicly. Production public access
remains through the configured Spring Gateway only.
