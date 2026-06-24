from __future__ import annotations

import argparse
import asyncio
import json
import logging

from app.common.logging import configure_logging
from ingestion_worker.restore_backup import RestoreBackupError, run_restore_backup
from ingestion_worker.schema_catalog_builder import add_schema_catalog_parser, run_schema_catalog
from ingestion_worker.business_knowledge_commands import add_business_knowledge_parser, run_business_knowledge_ingest
from ingestion_worker.sync import RagSyncService, run_loop
from ingestion_worker.smoke_chat import run_smoke_chat
from ingestion_worker.schema_commands import run_schema_command


def main() -> None:
    configure_logging()
    parser = argparse.ArgumentParser(prog="python -m ingestion_worker")
    subcommands = parser.add_subparsers(dest="command", required=True)

    sync = subcommands.add_parser("sync", help="run a one-shot source sync")
    sync.add_argument("--source", default=None)
    sync.add_argument("--table", default=None)
    sync.add_argument("--mode", choices=["full", "incremental"], default="incremental")
    sync.add_argument("--dry-run", action="store_true")

    worker = subcommands.add_parser("worker", help="run incremental sync loop")
    worker.add_argument("--source", default=None)
    worker.add_argument("--interval", type=int, default=60)
    worker.add_argument("--dry-run", action="store_true")

    status = subcommands.add_parser("status", help="show sync health and indexed-document counts")
    status.add_argument("--source", default=None)
    status.add_argument("--table", default=None)
    status.add_argument("--json", action="store_true")

    restore = subcommands.add_parser("restore-backup", help="restore an external SQL backup into a local/server MySQL database")
    restore.add_argument("--file", required=True)
    restore.add_argument("--database", required=True)

    schema_ingest = subcommands.add_parser("schema-ingest", help="discover and ingest schema intelligence")
    schema_ingest.add_argument("--source", default="construction_mysql")
    schema_ingest.add_argument("--force", action="store_true")

    schema_status = subcommands.add_parser("schema-status", help="show schema intelligence status")
    schema_status.add_argument("--source", default="construction_mysql")
    schema_status.add_argument("--json", action="store_true")

    schema_refresh = subcommands.add_parser("schema-refresh", help="force schema rediscovery and ingestion")
    schema_refresh.add_argument("--source", default="construction_mysql")

    smoke_chat = subcommands.add_parser("smoke-chat", help="run a local database-aware chat smoke prompt")
    smoke_chat.add_argument("--message", required=True)
    smoke_chat.add_argument("--source", default="construction_mysql")

    add_schema_catalog_parser(subcommands)
    add_business_knowledge_parser(subcommands)

    args = parser.parse_args()
    if args.command == "sync":
        asyncio.run(_sync_once(args.source, args.table, args.mode, args.dry_run))
    elif args.command == "worker":
        asyncio.run(run_loop(interval=args.interval, source_name=args.source, dry_run=args.dry_run))
    elif args.command == "status":
        asyncio.run(_status(args.source, args.table, args.json))
    elif args.command == "restore-backup":
        try:
            raise SystemExit(run_restore_backup(args.file, args.database))
        except RestoreBackupError as exc:
            raise SystemExit(f"restore-backup failed: {exc}") from exc
    elif args.command == "schema-ingest":
        raise SystemExit(asyncio.run(run_schema_command("schema-ingest", source=args.source, force=args.force, as_json=True)))
    elif args.command == "schema-status":
        raise SystemExit(asyncio.run(run_schema_command("schema-status", source=args.source, as_json=args.json)))
    elif args.command == "schema-refresh":
        raise SystemExit(asyncio.run(run_schema_command("schema-refresh", source=args.source, force=True, as_json=True)))
    elif args.command == "smoke-chat":
        raise SystemExit(run_smoke_chat(args.message, source=args.source))
    elif args.command == "schema-catalog":
        raise SystemExit(asyncio.run(run_schema_catalog(args)))
    elif args.command == "business-knowledge-ingest":
        raise SystemExit(asyncio.run(run_business_knowledge_ingest(args)))


async def _sync_once(source: str | None, table: str | None, mode: str, dry_run: bool) -> None:
    service = RagSyncService()
    results = await service.sync_configured(source_name=source, table_name=table, mode=mode, dry_run=dry_run)
    for item in results:
        logging.getLogger(__name__).info(
            "rag_sync_result source=%s table=%s scanned=%s indexed=%s skipped=%s deleted=%s errors=%s dry_run=%s",
            item.source,
            item.table,
            item.scanned,
            item.indexed,
            item.skipped,
            item.deleted,
            item.errors,
            dry_run,
        )


async def _status(source: str | None, table: str | None, as_json: bool) -> None:
    service = RagSyncService()
    results = await service.status(source_name=source, table_name=table)
    rows = [
        {
            "source": item.source,
            "table": item.table,
            "tenant_id": item.tenant_id,
            "project_id": item.project_id,
            "last_sync_at": item.last_sync_at.isoformat() if item.last_sync_at else None,
            "last_success_at": item.last_success_at.isoformat() if item.last_success_at else None,
            "status": item.status,
            "last_error": item.last_error,
            "indexed_documents": item.indexed_documents,
            "inactive_documents": item.inactive_documents,
        }
        for item in results
    ]
    if as_json:
        print(json.dumps({"tables": rows}, ensure_ascii=False, indent=2))
        return
    for row in rows:
        print(
            "source={source} table={table} tenant={tenant_id} project={project_id} "
            "status={status} last_success_at={last_success_at} indexed={indexed_documents} "
            "inactive={inactive_documents} last_error={last_error}".format(**row)
        )

if __name__ == "__main__":
    main()
