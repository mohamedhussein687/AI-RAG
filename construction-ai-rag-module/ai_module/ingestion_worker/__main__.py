from __future__ import annotations

import argparse
import asyncio
import json
import logging

from app.common.logging import configure_logging
from ingestion_worker.sync import RagSyncService, run_loop


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

    args = parser.parse_args()
    if args.command == "sync":
        asyncio.run(_sync_once(args.source, args.table, args.mode, args.dry_run))
    elif args.command == "worker":
        asyncio.run(run_loop(interval=args.interval, source_name=args.source, dry_run=args.dry_run))
    elif args.command == "status":
        asyncio.run(_status(args.source, args.table, args.json))


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
