# Local Backup Restore

The SQL backup is protected operational data. Keep it outside this Git
repository at all times.

## Rules

- Do not commit `.sql`, `.dump`, `.backup`, `.tar`, or `.gz` files.
- Do not copy `/home/rag/backup.sql` into the repository.
- Do not delete, rename, overwrite, or modify `/home/rag/backup.sql`.
- Do not print database passwords in terminal logs or reports.

## Copy Backup Locally

Copy the server backup only to the approved local backup directory:

```bash
mkdir -p /home/hussein/backups
scp techlab-ai:/home/rag/backup.sql /home/hussein/backups/backup.sql
```

Expected local path:

```text
/home/hussein/backups/backup.sql
```

## Configure MySQL Locally

Create a local `.env` from the example and set credentials locally only:

```bash
cd /home/hussein/Documents/AI-RAG/ai-rag/construction-ai-rag-module
cp .env.example .env
```

Required values:

```env
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_DATABASE=construction_ai_dev
MYSQL_USER=<local_restore_user>
MYSQL_PASSWORD=<local_restore_password>
MYSQL_CONNECT_TIMEOUT_SECONDS=5
MYSQL_QUERY_TIMEOUT_SECONDS=15
MYSQL_MAX_ROWS=200
```

The restore user must be allowed to create/import the development database. For
runtime chat and schema discovery, prefer a separate read-only user.

## Restore Locally

Run from the AI module directory:

```bash
cd /home/hussein/Documents/AI-RAG/ai-rag/construction-ai-rag-module/ai_module
python -m ingestion_worker restore-backup \
  --file /home/hussein/backups/backup.sql \
  --database construction_ai_dev
```

The command:

- refuses relative backup paths;
- refuses backup files inside the Git repository;
- creates the target database if missing;
- imports the SQL through the local `mysql` client;
- reports only redacted status metadata.

## Restore on Server

Only after local code is committed, pushed, and pulled on the server:

```bash
ssh techlab-ai
cd /home/rag/AI-RAG/construction-ai-rag-module/ai_module
python -m ingestion_worker restore-backup \
  --file /home/rag/backup.sql \
  --database construction_ai_dev
```

The server command uses the existing backup in place. It must not move or edit
`/home/rag/backup.sql`.

## Verify

After restore:

```bash
python -m ingestion_worker schema-ingest --source construction_mysql
python -m ingestion_worker schema-status --source construction_mysql
python -m ingestion_worker smoke-chat --message "اعرض جميع اسماء المستخدمين"
```

If restore fails, fix the local/server MySQL credentials or permissions. Do not
weaken the repository backup-path refusal rule.
