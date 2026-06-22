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
import logging
import re

SENSITIVE = ("password", "باسورد", "كلمة السر", "secret", "credential", "token")
DOC_TERMS = ("إزاي", "how to", "policy", "سياسة", "procedure", "إجراء", "manual", "دليل", "contract", "عقد", "مستخلص")
DELAY_TERMS = ("متأخر", "delayed", "delay")
PROJECT_TERMS = ("مشروع", "مشاريع", "المشاريع", "project", "projects")
COUNT_TERMS = ("كم", "عدد", "count", "how many", "total")
log = logging.getLogger(__name__)


class DecisionService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.retrieval = RetrievalService(settings)
        self.llm = LlmClient(settings)

    async def decide(self, request: AgentDecideRequest):
        text = request.message.lower()
        arabic = prefer_arabic(request.message, request.locale)
        if self._has_database_catalog(request):
            guarded = self._deterministic_database_guard(request)
            if guarded:
                plan = guarded["tool_calls"][0]["plan"]
                log.info(
                    "agent_decision route=database_query intent=%s selected_table=%s operation=%s reason=%s",
                    guarded.get("intent"),
                    plan.get("table"),
                    plan.get("operation"),
                    guarded.get("reason"),
                )
                guarded.pop("intent", None)
                guarded.pop("reason", None)
                return validate_decision(guarded)
            return await self._qwen_database_decision(request, arabic)

        if any(term in text for term in SENSITIVE):
            return validate_decision(ForbiddenDecision(type="forbidden").model_dump())

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
        return any(t.name == "database_query" for t in request.external_tools) and (
            bool(request.semantic_catalog.get("tables")) or bool(request.semantic_catalog.get("tables_index"))
        )

    async def _qwen_database_decision(self, request: AgentDecideRequest, arabic: bool):
        messages = [
            {
                "role": "system",
                "content": (
                    "You convert a natural-language question into a database_query tool-call JSON object. Return exactly one strict JSON object and nothing else. "
                    "Never output SQL, SELECT, FROM, executable query text, markdown, explanations, tables not in catalog, columns not in catalog, values not supported by catalog, joins, or credentials. "
                    "You are the only intent understanding engine. Determine the entity, operation, filters, grouping, sorting, and aggregation from the user message. "
                    "Use only the semantic catalog. If the requested entity, relation, field, or value is not clearly represented, return unsupported. "
                    "For greetings, small-talk, wellbeing questions, thanks, and conversational messages that do not ask for business data, do not call tools. Return a natural Arabic final_answer. "
                    "For identity questions such as who are you, your name, or what project you work on, do not call tools. Return exactly "
                    '{"type":"final_answer","answer":"أنا مساعد ORBIT AI، شغال على مشروع ORBIT، وأقدر أساعدك في قراءة وتحليل بيانات المشروع حسب الصلاحيات المتاحة.","display":{"type":"text","data":{}},"sources":[]}. '
                    "The domain_entities section contains authoritative business mappings. Operational project questions in Arabic or English must use domain entity projects and table projects. "
                    "Never use CMS/content/website tables such as about_us, pages, settings, banners, sliders, or web_* for operational business questions unless the user explicitly asks about website content. "
                    "The catalog has tables_index for choosing entities and allowed table operations. Detailed tables include columns for filters, grouping, sorting, lists, and aggregates. "
                    "For simple count questions you may use a table from tables_index when count is allowed, even if that table is not in detailed tables. "
                    "For filters, grouping, sorting, listing, or aggregates, use only columns present in detailed tables. "
                    "For a count, output this exact shape with the chosen table: "
                    '{"type":"tool_calls","tool_calls":[{"id":"db_1","tool":"database_query","plan":{"operation":"count","table":"logical_table","filters":[],"limit":20}}],"local_rag_results":[],"final_answer_instruction":"Answer in Arabic."}. '
                    "For list/group/aggregate, use the same top-level shape and only add allowed plan fields from this set: column, filters, group_by, order_by, limit. "
                    'If unsupported, output exactly {"type":"unsupported","answer":"لا أستطيع تنفيذ هذا الطلب من البيانات المتاحة."}. '
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
            log.info("agent_decision route=unsupported intent=unknown selected_table=none operation=none reason=empty_llm_response")
            return validate_decision(UnsupportedDecision(type="unsupported").model_dump())
        if decision.get("type") == "tool_calls":
            decision["local_rag_results"] = []
            decision["final_answer_instruction"] = self._instruction(arabic)
            for i, call in enumerate(decision.get("tool_calls", []), start=1):
                call.setdefault("id", f"db_{i}")
                call["tool"] = "database_query"
                plan = call.get("plan", {})
                plan["limit"] = min(int(plan.get("limit", request.rules.max_rows)), 20)
                log.info(
                    "agent_decision route=database_query intent=llm_structured selected_table=%s operation=%s reason=qwen_plan",
                    plan.get("table"),
                    plan.get("operation"),
                )
        elif decision.get("type") == "final_answer":
            log.info("agent_decision route=conversational intent=llm_final_answer selected_table=none operation=none reason=qwen_final_answer")
        else:
            log.info("agent_decision route=%s intent=llm_non_tool selected_table=none operation=none reason=qwen_decision", decision.get("type"))
        return validate_decision(decision)

    def _deterministic_database_guard(self, request: AgentDecideRequest):
        if not self._is_project_count(request.message):
            return None
        table = self._domain_table(request.semantic_catalog, "projects")
        if table != "projects":
            log.info("agent_decision route=unsupported intent=project_count selected_table=%s operation=count reason=missing_authoritative_project_table", table or "none")
            return None
        return {
            "type": "tool_calls",
            "intent": "project_count",
            "reason": "deterministic_domain_entity_guard",
            "tool_calls": [
                {
                    "id": "db_1",
                    "tool": "database_query",
                    "plan": {"operation": "count", "table": table, "filters": [], "limit": min(request.rules.max_rows, 20)},
                }
            ],
            "local_rag_results": [],
            "final_answer_instruction": self._instruction(prefer_arabic(request.message, request.locale)),
        }

    def _is_project_count(self, message: str) -> bool:
        text = self._normalize(message)
        return any(term in text for term in PROJECT_TERMS) and any(term in text for term in COUNT_TERMS)

    def _domain_table(self, catalog: dict, entity: str) -> str | None:
        for item in catalog.get("domain_entities", []):
            if item.get("entity") == entity and item.get("count_operation") == "count":
                return item.get("table")
        return None

    def _normalize(self, value: str) -> str:
        text = value.lower()
        text = text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ة", "ه")
        return re.sub(r"[^\w\s]", " ", text)

    def _instruction(self, arabic: bool) -> str:
        return "Answer in Arabic using database results and local RAG results." if arabic else "Answer using database results and local RAG results."

    def _rag_answer(self, chunks, arabic: bool) -> str:
        if arabic:
            return "حسب المستندات المتاحة: " + chunks[0].text
        return "Based on the available documents: " + chunks[0].text
