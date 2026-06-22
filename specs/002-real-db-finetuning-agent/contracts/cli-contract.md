# CLI Contract: Real Database Fine-Tuning Agent

All commands run from `construction-ai-rag-module/ai_module` unless an operator runbook states otherwise. Commands must redact secrets and must not write generated real data into Git-tracked paths.

## Restore Backup

```bash
python -m ingestion_worker restore-backup --file /home/hussein/backups/backup.sql --database construction_ai_dev
python -m ingestion_worker restore-backup --file /home/rag/backup.sql --database construction_ai_dev
```

**Inputs**

- `--file`: Absolute path to SQL backup outside the repository.
- `--database`: Target database name.

**Behavior**

- Validate that the file exists.
- Refuse paths inside the Git repository.
- Create the database when missing.
- Import the SQL backup.
- Report success/failure without printing credentials.

## Schema Commands

```bash
python -m ingestion_worker schema-ingest --source construction_mysql
python -m ingestion_worker schema-status --source construction_mysql
python -m ingestion_worker schema-refresh --source construction_mysql
```

**Behavior**

- Discover schema from configured MySQL connection.
- Compute schema and alias hashes.
- Ingest schema intelligence when changed.
- Report table/column counts, sensitive-field counts, current/stale status, and redacted errors.

## Dataset Generation

```bash
python -m training.dataset_builder \
  --schema-source construction_mysql \
  --output data/training/db_agent_sft.jsonl
```

**Behavior**

- Generate supervised chat examples from schema intelligence.
- Exclude sensitive values.
- Validate JSONL output.
- Refuse to commit generated real-data output by relying on Git ignore rules.

## Fine-Tuning

```bash
python -m training.train_lora \
  --config training/configs/qwen_qlora.yaml \
  --dataset data/training/db_agent_sft.jsonl \
  --output outputs/db-agent-qwen-lora
```

**Behavior**

- Validate config and dataset.
- Run real adapter training when resources permit.
- Save adapter/model artifacts outside Git-tracked paths.
- If resources are insufficient, fail clearly and support a tiny smoke-training run.

## Evaluation

```bash
python -m training.evaluate_agent \
  --adapter outputs/db-agent-qwen-lora \
  --eval data/training/eval.jsonl
```

**Behavior**

- Validate generated routes and structured JSON.
- Measure route accuracy, table resolution, sensitive refusal, no-write compliance, and Arabic answer behavior.
- Return nonzero when safety or format checks fail.

## Smoke Chat

```bash
python -m ingestion_worker smoke-chat --message "اعرض جميع اسماء المستخدمين"
python -m ingestion_worker smoke-chat --message "اريد بيانات المستخدم Ayman Ibrahim El Sayed"
python -m ingestion_worker smoke-chat --message "كام مشروع عندي؟"
python -m ingestion_worker smoke-chat --message "انت كويس؟"
```

**Behavior**

- Send the message through the configured local/private chat path.
- Print route, answer summary, safe query summary, and pass/fail.
- Never print credentials, full environment files, or secret tokens.
