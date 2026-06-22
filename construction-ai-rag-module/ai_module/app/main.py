from uuid import uuid4
import logging
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from app.auth import require_module_token
from app.config import Settings, get_settings
from app.common.logging import configure_logging
from app.schemas import AgentDecideRequest, AgentFinalRequest, DocumentIndexRequest, RagSearchRequest, HealthResponse, SchemaIngestRequest, SchemaSearchRequest
from app.agent.decision_service import DecisionService
from app.agent.final_answer_service import FinalAnswerService
from app.rag.document_service import DocumentService
from app.rag.retrieval_service import RetrievalService
from app.rag.qdrant_service import get_qdrant_service
from app.rag.embedding_client import EmbeddingClient
from app.rag.reranker_client import RerankerClient
from app.schema.schema_service import SchemaService
from app.clients.llm_client import LlmClient
from app.storage.postgres import health as postgres_health

configure_logging()
app = FastAPI(title="Construction AI RAG Module")
log = logging.getLogger(__name__)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request.state.request_id = request.headers.get("x-request-id", str(uuid4()))
    response = await call_next(request)
    response.headers["x-request-id"] = request.state.request_id
    return response


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", "unknown")
    log.exception("unhandled_exception request_id=%s path=%s", request_id, request.url.path)
    return JSONResponse(status_code=500, content={"error": {"code": "internal_error", "message": "Internal server error"}, "request_id": request_id})


async def dependency_health(settings: Settings) -> dict[str, str]:
    return {
        "postgres": await postgres_health(settings),
        "qdrant": await get_qdrant_service(settings).health(),
        "llm": await LlmClient(settings).health(),
        "embedding": await EmbeddingClient(settings).health(),
        "reranker": await RerankerClient(settings).health(),
        "migrations": await postgres_health(settings),
    }


@app.get("/health", response_model=HealthResponse)
async def health(settings: Settings = Depends(get_settings)):
    deps = await dependency_health(settings)
    status = "ok" if all(v in {"ok", "disabled"} for v in deps.values()) else "degraded"
    return HealthResponse(status=status, dependencies=deps, version=settings.release_sha)


@app.get("/health/live")
async def live():
    return {"status": "ok"}


@app.get("/health/ready", response_model=HealthResponse)
async def ready(settings: Settings = Depends(get_settings)):
    deps = await dependency_health(settings)
    acceptable = {"ok"} if settings.production_mode else {"ok", "disabled"}
    status = "ok" if all(v in acceptable for v in deps.values()) else "degraded"
    return HealthResponse(status=status, dependencies=deps, version=settings.release_sha)


@app.post("/api/agent/decide", dependencies=[Depends(require_module_token)])
async def decide(request: AgentDecideRequest, settings: Settings = Depends(get_settings)):
    return await DecisionService(settings).decide(request)


@app.post("/api/agent/final", dependencies=[Depends(require_module_token)])
async def final(request: AgentFinalRequest, settings: Settings = Depends(get_settings)):
    return await FinalAnswerService(settings).final(request)


@app.post("/api/rag/documents", status_code=201, dependencies=[Depends(require_module_token)])
async def index_document(request: DocumentIndexRequest, settings: Settings = Depends(get_settings)):
    return await DocumentService(settings).index(request)


@app.post("/api/rag/search", dependencies=[Depends(require_module_token)])
async def search(request: RagSearchRequest, settings: Settings = Depends(get_settings)):
    return await RetrievalService(settings).search(request)


@app.post("/api/schema/ingest", dependencies=[Depends(require_module_token)])
async def ingest_schema(request: SchemaIngestRequest, settings: Settings = Depends(get_settings)):
    return await SchemaService(settings).ingest(request)


@app.post("/api/schema/search", dependencies=[Depends(require_module_token)])
async def search_schema(request: SchemaSearchRequest, settings: Settings = Depends(get_settings)):
    return await SchemaService(settings).search(request)


@app.post("/api/chat", dependencies=[Depends(require_module_token)])
async def module_chat(request: AgentDecideRequest, settings: Settings = Depends(get_settings)):
    decision = await DecisionService(settings).decide(request)
    if getattr(decision, "type", None) != "tool_calls":
        return decision
    final_request = AgentFinalRequest(
        conversation_id=request.conversation_id,
        message=request.message,
        locale=request.locale,
        conversation_history=request.conversation_history,
        tool_results=[],
        local_rag_results=getattr(decision, "local_rag_results", []),
        final_answer_instruction=getattr(decision, "final_answer_instruction", None),
    )
    return await FinalAnswerService(settings).final(final_request)
