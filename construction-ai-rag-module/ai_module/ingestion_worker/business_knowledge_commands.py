from __future__ import annotations

from pathlib import Path

from app.config import get_settings
from app.rag.document_service import DocumentService
from app.schemas import AccessPolicy, DocumentIndexRequest


def add_business_knowledge_parser(subcommands):
    parser = subcommands.add_parser("business-knowledge-ingest", help="index PROJECT_MASTER_KNOWLEDGE_BASE.md into the business knowledge Qdrant collection")
    parser.add_argument("--file", default="PROJECT_MASTER_KNOWLEDGE_BASE.md")
    parser.add_argument("--tenant-id", default=None)
    parser.add_argument("--project-id", default=None)
    parser.add_argument("--title", default="PROJECT_MASTER_KNOWLEDGE_BASE.md")
    return parser


async def run_business_knowledge_ingest(args) -> int:
    settings = get_settings()
    path = Path(args.file)
    if not path.exists():
        raise SystemExit(f"business knowledge file not found: {path}")
    content = path.read_text(encoding="utf-8")
    tenant_id = args.tenant_id or settings.schema_source_name
    response = await DocumentService(settings).index(
        DocumentIndexRequest(
            tenant_id=tenant_id,
            project_id=args.project_id or tenant_id,
            title=args.title,
            source_type="business_knowledge",
            content=content,
            access_policy=AccessPolicy(permissions=["live-data.read", "knowledge.read"]),
            metadata={
                "source_identity": f"business_knowledge:{path.resolve()}",
                "source_path": str(path.resolve()),
                "version": settings.index_version,
                "is_active": True,
                "target_collection": settings.qdrant_business_collection,
            },
        )
    )
    print(response.model_dump_json())
    return 0
