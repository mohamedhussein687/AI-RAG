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
from pydantic import ValidationError

SENSITIVE = ("password", "باسورد", "كلمة السر", "secret", "credential", "token")
DOC_TERMS = ("إزاي", "how to", "policy", "سياسة", "procedure", "إجراء", "manual", "دليل", "contract", "عقد", "مستخلص")
DELAY_TERMS = ("متأخر", "delayed", "delay")
PROJECT_TERMS = ("مشروع", "مشاريع", "المشاريع", "project", "projects")
COUNT_TERMS = ("كم", "عدد", "count", "how many", "total")
DELAY_REPORT_TERMS = ("متاخر", "متاخرين", "متاخره", "تأخير", "تاخير", "delayed", "late")
DELIVERY_TERMS = ("تسليم", "delivery", "deadline", "end date")
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
        route = await self._qwen_route_decision(request, arabic)
        if route is not None:
            return route
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
        try:
            return validate_decision(decision)
        except ValidationError as exc:
            reason = exc.errors()[0].get("type") if exc.errors() else "validation_error"
            log.info("agent_decision route=unsupported intent=invalid_structured_plan selected_table=none operation=none reason=%s", reason)
            return validate_decision(UnsupportedDecision(type="unsupported").model_dump())

    async def _qwen_route_decision(self, request: AgentDecideRequest, arabic: bool):
        messages = [
            {
                "role": "system",
                "content": (
                    "Classify the user's message before database planning. Return exactly one JSON object. "
                    "Use route=conversational for greetings, wellbeing questions, thanks, identity/name/project-introduction, or small-talk. "
                    "Use route=database_query only when the user asks for operational business data represented in the semantic catalog. "
                    "Use route=unsupported when the user asks for business data whose entity or relationship is not present in the catalog. "
                    "Never return SQL or credentials. For conversational route include a natural Arabic answer."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "question": request.message,
                        "locale": request.locale,
                        "semantic_catalog": request.semantic_catalog,
                        "required_shape": {"route": "conversational|database_query|unsupported", "answer": "optional"},
                    },
                    ensure_ascii=False,
                ),
            },
        ]
        route = await self.llm.chat_json(messages)
        if not isinstance(route, dict) or "route" not in route:
            return None
        value = str(route.get("route"))
        if value == "database_query":
            log.info("agent_decision route=database_query intent=llm_routed_database selected_table=pending operation=pending reason=qwen_route")
            return None
        if value == "conversational":
            answer = route.get("answer") if isinstance(route.get("answer"), str) and route.get("answer").strip() else (
                "أنا بخير، وجاهز أساعدك في بيانات مشروع ORBIT." if arabic else "I'm doing well and ready to help with ORBIT data."
            )
            log.info("agent_decision route=conversational intent=small_talk selected_table=none operation=none reason=qwen_route")
            return validate_decision(FinalAnswerDecision(type="final_answer", answer=answer, display=Display(type="text"), sources=[]).model_dump())
        answer = route.get("answer") if isinstance(route.get("answer"), str) and route.get("answer").strip() else "لا أستطيع تنفيذ هذا الطلب من البيانات المتاحة."
        log.info("agent_decision route=unsupported intent=unsupported_business_question selected_table=none operation=none reason=qwen_route")
        return validate_decision(UnsupportedDecision(type="unsupported", answer=answer).model_dump())

    def _deterministic_database_guard(self, request: AgentDecideRequest):
        delayed = self._delayed_projects_report_guard(request)
        if delayed:
            return delayed
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

    def _delayed_projects_report_guard(self, request: AgentDecideRequest):
        if not self._is_delayed_projects_report(request.message):
            return None
        report = self._domain_report(request.semantic_catalog, "projects", "delayed_projects_report")
        if not report or not report.get("enabled"):
            missing = ", ".join(report.get("missing_fields", [])) if isinstance(report, dict) else "delayed_projects_report"
            log.info("agent_decision route=unsupported intent=delayed_projects_report selected_table=projects operation=select reason=missing_report_mapping missing=%s", missing)
            return {
                "type": "unsupported",
                "answer": f"لا أستطيع إعداد تقرير المشاريع المتأخرة لأن إعدادات خريطة البيانات ناقصة: {missing}.",
            }
        table = report.get("table")
        deadline = report.get("deadline_field")
        completion = report.get("completion_field")
        order_field = report.get("order_field")
        title = report.get("title_field")
        status = report.get("status_field")
        if not all([table, deadline, completion, order_field, title]):
            return {"type": "unsupported", "answer": "لا أستطيع إعداد تقرير المشاريع المتأخرة لأن حقول التقرير المطلوبة غير مكتملة في خريطة البيانات."}
        columns = [title, status, deadline, completion, "actual_delivery_date", order_field]
        columns = list(dict.fromkeys([c for c in columns if c]))
        return {
            "type": "tool_calls",
            "intent": "delayed_projects_report",
            "reason": "deterministic_domain_entity_guard",
            "tool_calls": [
                {
                    "id": "db_1",
                    "tool": "database_query",
                    "plan": {
                        "intent": "delayed_projects_report",
                        "operation": "select",
                        "table": table,
                        "columns": columns,
                        "filters": [
                            {"column": deadline, "operator": "lt", "value": "today"},
                            {"column": completion, "operator": "not_completed", "value": False},
                        ],
                        "order_by": {"column": order_field, "direction": "desc"},
                        "limit": self._requested_limit(request.message, int(report.get("default_limit", 4))),
                    },
                }
            ],
            "local_rag_results": [],
            "final_answer_instruction": self._instruction(prefer_arabic(request.message, request.locale)),
        }

    def _is_project_count(self, message: str) -> bool:
        text = self._normalize(message)
        return any(term in text for term in PROJECT_TERMS) and any(term in text for term in COUNT_TERMS)

    def _is_delayed_projects_report(self, message: str) -> bool:
        text = self._normalize(message)
        return any(term in text for term in PROJECT_TERMS) and any(term in text for term in DELAY_REPORT_TERMS) and (
            any(term in text for term in DELIVERY_TERMS) or "اخر" in text or "آخر" in message
        )

    def _domain_table(self, catalog: dict, entity: str) -> str | None:
        for item in catalog.get("domain_entities", []):
            if item.get("entity") == entity and item.get("count_operation") == "count":
                return item.get("table")
        return None

    def _domain_report(self, catalog: dict, entity: str, report_name: str) -> dict | None:
        for item in catalog.get("domain_entities", []):
            if item.get("entity") == entity:
                report = item.get(report_name)
                return report if isinstance(report, dict) else None
        return None

    def _requested_limit(self, message: str, default: int) -> int:
        text = self._normalize(message)
        match = re.search(r"\b([1-9][0-9]?)\b", text)
        if match:
            return min(max(int(match.group(1)), 1), 20)
        if "اربع" in text or "اربعه" in text:
            return 4
        return min(max(default, 1), 20)

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
