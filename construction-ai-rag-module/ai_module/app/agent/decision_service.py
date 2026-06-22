from app.config import Settings
from app.schemas import (
    AgentDecideRequest,
    ClarificationDecision,
    Display,
    FinalAnswerDecision,
    ForbiddenDecision,
    UnsupportedDecision,
)
from .json_guard import validate_decision
from .prompt_builder import prefer_arabic
from app.rag.retrieval_service import RetrievalService
from app.schemas import RagSearchRequest, RagFilters
from app.clients.llm_client import LlmClient
import json

SENSITIVE = ("password", "باسورد", "كلمة السر", "secret", "credential", "token")
DOC_TERMS = ("إزاي", "how to", "policy", "سياسة", "procedure", "إجراء", "manual", "دليل", "contract", "عقد", "مستخلص")
DELAY_TERMS = ("متأخر", "delayed", "delay")


class DecisionService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.retrieval = RetrievalService(settings)
        self.llm = LlmClient(settings)

    async def decide(self, request: AgentDecideRequest):
        text = request.message.lower()
        arabic = prefer_arabic(request.message, request.locale)
        if any(term in text for term in SENSITIVE):
            return validate_decision(ForbiddenDecision(type="forbidden").model_dump())

        if self._has_database_catalog(request):
            return await self._qwen_database_decision(request, arabic)

        is_doc = any(term.lower() in text for term in DOC_TERMS)
        is_mixed = (any(t in text for t in DELAY_TERMS) and ("سياسة" in text or "policy" in text))

        local_results = []
        if is_doc or is_mixed:
            search = RagSearchRequest(query=request.message, user_context=request.user_context, top_k=self.settings.max_retrieved_chunks, filters=RagFilters())
            local_results = (await self.retrieval.search(search)).results

        if is_mixed:
            return validate_decision(UnsupportedDecision(type="unsupported").model_dump())

        if is_doc:
            if not local_results:
                answer = "لم أجد مستندات ذات صلة متاحة لك." if arabic else "No relevant authorized documents were found."
                return validate_decision(FinalAnswerDecision(type="final_answer", answer=answer, display=Display(type="answer_with_sources"), sources=[]).model_dump())
            answer = self._rag_answer(local_results, arabic)
            return validate_decision(FinalAnswerDecision(type="final_answer", answer=answer, display=Display(type="answer_with_sources", data={"chunks": len(local_results)}), sources=[c.source() for c in local_results]).model_dump())

        question = "هل يمكنك توضيح البيانات أو المستندات المطلوبة؟" if arabic else "Can you clarify what data or documents you need?"
        return validate_decision(ClarificationDecision(type="clarification", question=question).model_dump())

    def _has_database_catalog(self, request: AgentDecideRequest) -> bool:
        return any(t.name == "database_query" for t in request.external_tools) and bool(request.semantic_catalog.get("tables"))

    async def _qwen_database_decision(self, request: AgentDecideRequest, arabic: bool):
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a database intent planner. Return only strict JSON. "
                    "Never return SQL. Never invent tables, columns, values, joins, or credentials. "
                    "Use only the semantic catalog. If the requested entity, relation, field, or value is not clearly represented, return unsupported. "
                    "The catalog has tables_index for choosing entities and allowed table operations. Detailed tables include columns for filters, grouping, sorting, lists, and aggregates. "
                    "For simple count questions you may use a table from tables_index when count is allowed, even if that table is not in detailed tables. "
                    "For filters, grouping, sorting, listing, or aggregates, use only columns present in detailed tables. "
                    "Allowed JSON decisions: "
                    '{"type":"tool_calls","tool_calls":[{"id":"db_1","tool":"database_query","plan":{"operation":"count|list|group_count|sum|avg|min|max","table":"logical_table","column":"logical_column_optional","filters":[{"column":"logical_column","operator":"eq|ne|gt|gte|lt|lte|contains","value": "..."}],"group_by":"logical_column_optional","order_by":{"column":"logical_column","direction":"asc|desc"},"limit":20}}],"local_rag_results":[],"final_answer_instruction":"Answer in Arabic."} '
                    'or {"type":"unsupported","answer":"لا أستطيع تنفيذ هذا الطلب من البيانات المتاحة."}. '
                    "Equivalent natural-language phrasings must produce the same plan."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "question": request.message,
                        "locale": request.locale,
                        "max_rows": min(request.rules.max_rows, 20),
                        "semantic_catalog": request.semantic_catalog,
                    },
                    ensure_ascii=False,
                ),
            },
        ]
        decision = await self.llm.chat_json(messages)
        if not decision:
            return validate_decision(UnsupportedDecision(type="unsupported").model_dump())
        if decision.get("type") == "tool_calls":
            decision["local_rag_results"] = []
            decision["final_answer_instruction"] = self._instruction(arabic)
            for i, call in enumerate(decision.get("tool_calls", []), start=1):
                call.setdefault("id", f"db_{i}")
                call["tool"] = "database_query"
                plan = call.get("plan", {})
                plan["limit"] = min(int(plan.get("limit", request.rules.max_rows)), 20)
        return validate_decision(decision)

    def _instruction(self, arabic: bool) -> str:
        return "Answer in Arabic using database results and local RAG results." if arabic else "Answer using database results and local RAG results."

    def _rag_answer(self, chunks, arabic: bool) -> str:
        if arabic:
            return "حسب المستندات المتاحة: " + chunks[0].text
        return "Based on the available documents: " + chunks[0].text
