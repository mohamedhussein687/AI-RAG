from app.config import Settings
from app.schemas import (
    AgentDecideRequest,
    ClarificationDecision,
    DatabaseFilter,
    DatabaseQueryPlan,
    Display,
    FinalAnswerDecision,
    ForbiddenDecision,
    ToolCall,
    ToolCallsDecision,
    UnsupportedDecision,
)
from .json_guard import validate_decision
from .prompt_builder import prefer_arabic
from app.rag.retrieval_service import RetrievalService
from app.schemas import RagSearchRequest, RagFilters

SENSITIVE = ("password", "باسورد", "كلمة السر", "secret", "credential", "token")
DOC_TERMS = ("إزاي", "how to", "policy", "سياسة", "procedure", "إجراء", "manual", "دليل", "contract", "عقد", "مستخلص")
LIVE_TERMS = ("waiting", "project", "مشروع", "مشاريع", "status", "count", "كم")
DELAY_TERMS = ("متأخر", "delayed", "delay")


class DecisionService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.retrieval = RetrievalService(settings)

    async def decide(self, request: AgentDecideRequest):
        text = request.message.lower()
        arabic = prefer_arabic(request.message, request.locale)
        if any(term in text for term in SENSITIVE):
            return validate_decision(ForbiddenDecision(type="forbidden").model_dump())

        is_doc = any(term.lower() in text for term in DOC_TERMS)
        is_live = self._is_live_question(text)
        is_mixed = (any(t in text for t in DELAY_TERMS) and ("سياسة" in text or "policy" in text))

        local_results = []
        if is_doc or is_mixed:
            search = RagSearchRequest(query=request.message, user_context=request.user_context, top_k=self.settings.max_retrieved_chunks, filters=RagFilters())
            local_results = (await self.retrieval.search(search)).results

        if is_mixed:
            call = self._projects_count_call(request, text)
            if call is None:
                return validate_decision(UnsupportedDecision(type="unsupported").model_dump())
            return validate_decision(ToolCallsDecision(type="tool_calls", tool_calls=[call], local_rag_results=local_results, final_answer_instruction=self._instruction(arabic)).model_dump())

        if is_live:
            call = self._projects_count_call(request, text)
            if call is None:
                return validate_decision(UnsupportedDecision(type="unsupported").model_dump())
            return validate_decision(ToolCallsDecision(type="tool_calls", tool_calls=[call], local_rag_results=[], final_answer_instruction=self._instruction(arabic)).model_dump())

        if is_doc:
            if not local_results:
                answer = "لم أجد مستندات ذات صلة متاحة لك." if arabic else "No relevant authorized documents were found."
                return validate_decision(FinalAnswerDecision(type="final_answer", answer=answer, display=Display(type="answer_with_sources"), sources=[]).model_dump())
            answer = self._rag_answer(local_results, arabic)
            return validate_decision(FinalAnswerDecision(type="final_answer", answer=answer, display=Display(type="answer_with_sources", data={"chunks": len(local_results)}), sources=[c.source() for c in local_results]).model_dump())

        question = "هل يمكنك توضيح البيانات أو المستندات المطلوبة؟" if arabic else "Can you clarify what data or documents you need?"
        return validate_decision(ClarificationDecision(type="clarification", question=question).model_dump())

    def _is_live_question(self, text: str) -> bool:
        return ("waiting" in text and ("مشروع" in text or "project" in text)) or ("كم" in text and "مشروع" in text)

    def _projects_count_call(self, request: AgentDecideRequest, text: str) -> ToolCall | None:
        if not any(t.name == "database_query" for t in request.external_tools):
            return None
        table = request.allowed_schema.table("projects")
        if table is None:
            return None
        if table.allowed_operations and "count" not in table.allowed_operations:
            return None
        if table.columns and "status" not in table.columns:
            return None
        filters = []
        if "waiting" in text:
            filters.append(DatabaseFilter(column="status", operator="eq", value="waiting"))
        plan = DatabaseQueryPlan(operation="count", table="projects", column=None, filters=filters, order_by=None, group_by=None, limit=min(request.rules.max_rows, 100))
        return ToolCall(id="db_1", tool="database_query", plan=plan)

    def _instruction(self, arabic: bool) -> str:
        return "Answer in Arabic using database results and local RAG results." if arabic else "Answer using database results and local RAG results."

    def _rag_answer(self, chunks, arabic: bool) -> str:
        if arabic:
            return "حسب المستندات المتاحة: " + chunks[0].text
        return "Based on the available documents: " + chunks[0].text
