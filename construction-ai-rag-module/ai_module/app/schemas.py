from typing import Annotated, Any, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

DisplayType = Literal["text", "metric", "table", "answer_with_sources", "mixed", "clarification"]
DbOperation = Literal["count", "list", "sum", "avg", "min", "max", "group_count"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ConversationMessage(StrictModel):
    role: Literal["user", "assistant", "system", "tool"]
    content: str


class UserContext(StrictModel):
    id: str | None = None
    tenant_id: str
    project_ids: list[str] = Field(default_factory=list)
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)


class AllowedTable(StrictModel):
    name: str
    columns: list[str] = Field(default_factory=list)
    allowed_operations: list[DbOperation] = Field(default_factory=list)


class AllowedSchema(StrictModel):
    tables: list[AllowedTable] = Field(default_factory=list)

    def table(self, name: str) -> AllowedTable | None:
        return next((t for t in self.tables if t.name == name), None)


class ToolName(StrictModel):
    name: Literal["database_query", "knowledge_search"]


class AgentRules(StrictModel):
    return_sql: Literal[False] = False
    max_tool_calls: int = Field(default=5, ge=1, le=20)
    max_rows: int = Field(default=100, ge=1, le=1000)
    joins_allowed: bool = False


class Display(StrictModel):
    type: DisplayType
    data: dict[str, Any] = Field(default_factory=dict)


class Source(StrictModel):
    document_id: str
    title: str
    source_type: str
    chunk_id: str | None = None
    page_number: int | None = None
    section_title: str | None = None


class RagChunk(StrictModel):
    chunk_id: str
    document_id: str
    title: str
    source_type: str
    project_id: str | None = None
    chunk_index: int
    page_number: int | None = None
    section_title: str | None = None
    text: str
    score: float | None = None

    def source(self) -> Source:
        return Source(document_id=self.document_id, title=self.title, source_type=self.source_type, chunk_id=self.chunk_id, page_number=self.page_number, section_title=self.section_title)


class DatabaseFilter(StrictModel):
    column: str
    operator: Literal["eq", "ne", "gt", "gte", "lt", "lte", "in", "contains"]
    value: Any


class OrderBy(StrictModel):
    column: str
    direction: Literal["asc", "desc"] = "asc"


class DatabaseQueryPlan(StrictModel):
    operation: DbOperation
    table: str
    column: str | None = None
    filters: list[DatabaseFilter] = Field(default_factory=list)
    order_by: OrderBy | None = None
    group_by: str | None = None
    limit: int = Field(default=100, ge=1, le=1000)


class ToolCall(StrictModel):
    id: str
    tool: Literal["database_query"]
    plan: DatabaseQueryPlan


class AgentDecideRequest(StrictModel):
    conversation_id: str
    message: str = Field(min_length=1)
    locale: str = "ar"
    conversation_history: list[ConversationMessage] = Field(default_factory=list)
    user_context: UserContext
    allowed_schema: AllowedSchema = Field(default_factory=AllowedSchema)
    external_tools: list[ToolName] = Field(default_factory=list)
    local_tools: list[ToolName] = Field(default_factory=list)
    rules: AgentRules = Field(default_factory=AgentRules)


class FinalAnswerDecision(StrictModel):
    type: Literal["final_answer"]
    answer: str
    display: Display = Field(default_factory=lambda: Display(type="text"))
    sources: list[Source] = Field(default_factory=list)


class ClarificationDecision(StrictModel):
    type: Literal["clarification"]
    question: str


class ToolCallsDecision(StrictModel):
    type: Literal["tool_calls"]
    tool_calls: list[ToolCall]
    local_rag_results: list[RagChunk] = Field(default_factory=list)
    final_answer_instruction: str


class ForbiddenDecision(StrictModel):
    type: Literal["forbidden"]
    answer: str = "لا أستطيع الوصول إلى بيانات حساسة أو محظورة."


class UnsupportedDecision(StrictModel):
    type: Literal["unsupported"]
    answer: str = "لا أستطيع تنفيذ هذا الطلب من البيانات المتاحة."


AgentDecision = Annotated[FinalAnswerDecision | ClarificationDecision | ToolCallsDecision | ForbiddenDecision | UnsupportedDecision, Field(discriminator="type")]


class ToolResult(StrictModel):
    tool_call_id: str
    tool: Literal["database_query"]
    result: Any


class AgentFinalRequest(StrictModel):
    conversation_id: str
    message: str
    locale: str = "ar"
    conversation_history: list[ConversationMessage] = Field(default_factory=list)
    tool_results: list[ToolResult] = Field(default_factory=list)
    local_rag_results: list[RagChunk] = Field(default_factory=list)
    final_answer_instruction: str | None = None


class AgentFinalResponse(StrictModel):
    answer: str
    display: Display
    sources: list[Source] = Field(default_factory=list)


class AccessPolicy(StrictModel):
    permissions: list[str] = Field(default_factory=list)


class DocumentIndexRequest(StrictModel):
    tenant_id: str
    project_id: str | None = None
    title: str
    source_type: str
    content: str = Field(min_length=1)
    access_policy: AccessPolicy
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("document content must not be blank")
        return value


class DocumentIndexResponse(StrictModel):
    document_id: str
    status: Literal["pending", "processing", "indexed", "failed"]
    chunks_indexed: int = Field(ge=0)
    job_id: str | None = None


class RagFilters(StrictModel):
    document_types: list[str] = Field(default_factory=list)
    project_id: str | None = None


class RagSearchRequest(StrictModel):
    query: str = Field(min_length=1)
    user_context: UserContext
    top_k: int = Field(default=5, ge=1, le=20)
    filters: RagFilters = Field(default_factory=RagFilters)


class RagSearchResponse(StrictModel):
    results: list[RagChunk]


class HealthResponse(StrictModel):
    status: Literal["ok", "degraded"]
    dependencies: dict[str, Literal["ok", "disabled", "error"]]


def contains_forbidden_keys(value: Any) -> bool:
    forbidden = {"raw_sql", "sql", "query", "unsafe_write_action"}
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in forbidden:
                return True
            if contains_forbidden_keys(item):
                return True
    elif isinstance(value, list):
        return any(contains_forbidden_keys(item) for item in value)
    return False
