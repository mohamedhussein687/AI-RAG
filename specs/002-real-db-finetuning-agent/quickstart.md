# Quickstart: Real Database Fine-Tuning Agent

This guide validates the feature locally first, then on the server only after the branch is committed and pushed.

## 1. Confirm Branch and Git Hygiene

```bash
cd /home/hussein/Documents/AI-RAG/ai-rag
git branch --show-current
git status --short
```

Expected:

- Branch is `feature/real-db-finetuning-agent`.
- No SQL backups, generated real datasets, model artifacts, `.env` files, or secrets are tracked.

## 2. Verify Ignore Rules

Ensure the repository ignores protected/generated artifacts:

```gitignore
*.sql
*.dump
*.backup
*.tar
*.gz
.env
.env.*
!.env.example
models/
checkpoints/
outputs/
lora_adapters/
wandb/
runs/
data/training/*.jsonl
!data/training/sample_fake.jsonl
```

## 3. Copy Backup Locally If Needed

Do not copy the backup into the repository.

```bash
mkdir -p /home/hussein/backups
scp techlab-ai:/home/rag/backup.sql /home/hussein/backups/backup.sql
```

Expected:

- Local backup path is `/home/hussein/backups/backup.sql`.
- `/home/hussein/Documents/AI-RAG/ai-rag` does not contain the backup.

## 4. Configure Local Environment

Create a local environment file from the example and set database credentials locally only:

```bash
cd construction-ai-rag-module
cp .env.example .env
```

Required local values:

```env
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_DATABASE=construction_ai_dev
MYSQL_USER=...
MYSQL_PASSWORD=...
MYSQL_CONNECT_TIMEOUT_SECONDS=5
MYSQL_QUERY_TIMEOUT_SECONDS=15
MYSQL_MAX_ROWS=200
```

Do not commit `.env`.

## 5. Restore Backup Locally

```bash
cd construction-ai-rag-module/ai_module
python -m ingestion_worker restore-backup --file /home/hussein/backups/backup.sql --database construction_ai_dev
```

Expected:

- Command refuses repository-contained backup paths.
- Database exists after restore.
- Output contains no database password.

## 6. Discover and Ingest Schema

```bash
python -m ingestion_worker schema-ingest --source construction_mysql
python -m ingestion_worker schema-status --source construction_mysql
```

Expected:

- Status reports source, schema hash, table count, column count, sensitive-field count, and fresh/stale state.
- Sensitive sample values are redacted or omitted.

## 7. Generate Training Dataset

```bash
python -m training.dataset_builder \
  --schema-source construction_mysql \
  --output data/training/db_agent_sft.jsonl
```

Expected:

- At least 500 examples for a small schema.
- 2,000 or more examples when enough entities exist.
- Dataset validates as JSONL chat format.
- Sensitive values are absent.
- Generated file remains untracked by Git.

## 8. Run Fine-Tuning or Smoke Training

Full training command:

```bash
python -m training.train_lora \
  --config training/configs/qwen_qlora.yaml \
  --dataset data/training/db_agent_sft.jsonl \
  --output outputs/db-agent-qwen-lora
```

If local hardware is insufficient, run the configured tiny smoke-training mode and record the exact blocker. Do not claim full fine-tuning success unless an adapter/model artifact is actually produced.

## 9. Evaluate the Agent

```bash
python -m training.evaluate_agent \
  --adapter outputs/db-agent-qwen-lora \
  --eval data/training/eval.jsonl
```

Expected report includes:

- Valid JSON output rate.
- Route accuracy.
- Table resolution accuracy.
- Sensitive-data refusal.
- No-write-operation compliance.
- Arabic answer behavior.
- Required smoke prompt results.

## 10. Local Smoke Chat

```bash
python -m ingestion_worker smoke-chat --message "اعرض جميع اسماء المستخدمين"
python -m ingestion_worker smoke-chat --message "اريد بيانات المستخدم Ayman Ibrahim El Sayed"
python -m ingestion_worker smoke-chat --message "كام مشروع عندي؟"
python -m ingestion_worker smoke-chat --message "انت كويس؟"
```

Expected:

- User-name and project-count questions route to database query.
- Conversational question routes conversational.
- Empty results describe the search strategy honestly.
- No sensitive fields are queried or printed.

## 11. Run Local Tests

```bash
python -m pytest
cd ../../construction-gateway
./mvnw test
```

Expected:

- Schema discovery, schema ingestion, dataset, training-script validation, SQL safety, chat routing, and gateway validation tests pass.

Latest Phase 8 local validation, recorded 2026-06-23:

```text
AI module focused Phase 8 tests:
  .venv/bin/python -m pytest tests/test_repository_hygiene.py tests/test_restore_backup.py -q
  Result: 7 passed, 1 warning

AI module full tests:
  .venv/bin/python -m pytest -q
  Result: 124 passed, 1 warning

Spring Gateway tests:
  ./mvnw test
  Result: 23 tests run, 0 failures, 0 errors, BUILD SUCCESS

Additional checks:
  git diff --check
  Result: pass

  .venv/bin/python -m compileall app ingestion_worker training tests
  Result: pass

  .venv/bin/python -m ingestion_worker restore-backup --help
  Result: pass
```

Backup restore was not executed during this local validation because no local
approved backup path was used in this phase. The restore command itself was
validated through mocked tests for path refusal, password redaction, MySQL
command construction, and error handling.

## 12. Commit and Push

```bash
cd /home/hussein/Documents/AI-RAG/ai-rag
git status --short
git add .
git commit -m "Implement real database fine-tuning agent"
git push -u origin feature/real-db-finetuning-agent
```

Before committing, confirm that Git does not include:

- SQL backups.
- Generated real training data.
- Model weights.
- Adapters.
- Checkpoints.
- `.env` files.
- Secrets.

## 13. Server Pull and Smoke Test

Only after the branch is pushed:

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

If missing:

```bash
cd /home/rag/
git clone git@github.com:mohamedhussein687/AI-RAG.git
cd AI-RAG
git checkout feature/real-db-finetuning-agent
```

Then validate with the protected server backup:

```bash
cd construction-ai-rag-module/ai_module
python -m ingestion_worker restore-backup --file /home/rag/backup.sql --database construction_ai_dev
python -m ingestion_worker schema-ingest --source construction_mysql
python -m ingestion_worker schema-status --source construction_mysql
python -m ingestion_worker smoke-chat --message "اعرض جميع اسماء المستخدمين"
python -m ingestion_worker smoke-chat --message "اريد بيانات المستخدم Ayman Ibrahim El Sayed"
python -m ingestion_worker smoke-chat --message "كام مشروع عندي؟"
python -m ingestion_worker smoke-chat --message "انت كويس؟"
```

Expected:

- Server commit SHA matches the pushed local commit.
- `/home/rag/backup.sql` is not moved, renamed, deleted, overwritten, or committed.
- Smoke tests report route, answer summary, safe query summary, and pass/fail.
- If full training is blocked by GPU/VRAM, the report says so explicitly.

## 14. Final Report Template

Use the required final structure:

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

LIMITATIONS / BLOCKERS
- list blockers honestly, especially GPU/fine-tuning limitations
```
