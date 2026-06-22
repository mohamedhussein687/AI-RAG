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
from .normalization import ArabicNormalizer
from .prompt_builder import prefer_arabic
from .routing import MessageRouter
from .schema_planner import SchemaAwarePlanner
from app.rag.retrieval_service import RetrievalService
from app.schemas import RagSearchRequest, RagFilters
from app.clients.llm_client import LlmClient
import json
import logging
from pydantic import ValidationError

SENSITIVE = ("password", "باسورد", "كلمة السر", "secret", "credential", "token")
DOC_TERMS = ("إزاي", "how to", "policy", "سياسة", "procedure", "إجراء", "manual", "دليل", "contract", "عقد", "مستخلص")
DELAY_TERMS = ("متأخر", "delayed", "delay")
log = logging.getLogger(__name__)


class DecisionService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.retrieval = RetrievalService(settings)
        self.llm = LlmClient(settings)
        self.router = MessageRouter()
        self.schema_planner = SchemaAwarePlanner()

    async def decide(self, request: AgentDecideRequest):
        try:
            return await self._decide_core(request)
        except Exception as exc:
            return self._safe_decision_fallback(request, exc)

    async def _decide_core(self, request: AgentDecideRequest):
        text = request.message.lower()
        arabic = prefer_arabic(request.message, request.locale)
        if any(term in text for term in SENSITIVE):
            log.info("agent_decision route=forbidden intent=sensitive_data selected_table=none operation=none normalized_message=%s reason=sensitive_term", self._normalize(request.message)[:300])
            return validate_decision(ForbiddenDecision(type="forbidden").model_dump())
        route = self.router.route(request.message, self._has_database_catalog(request))
        if route.route == "conversational":
            log.info(
                "agent_decision route=conversational intent=%s selected_table=none operation=none normalized_message=%s reason=message_router",
                route.intent,
                self._normalize(request.message)[:300],
            )
            return validate_decision(FinalAnswerDecision(type="final_answer", answer=route.answer, display=Display(type="text", data={"conversation_type": route.intent}), sources=[]).model_dump())
        if route.route == "unsupported":
            log.info(
                "agent_decision route=unsupported intent=%s selected_table=none operation=none normalized_message=%s reason=message_router",
                route.intent,
                self._normalize(request.message)[:300],
            )
            return validate_decision(UnsupportedDecision(type="unsupported", answer=route.answer).model_dump())
        if route.route == "clarification":
            log.info(
                "agent_decision route=clarification intent=%s selected_table=none operation=none normalized_message=%s reason=message_router",
                route.intent,
                self._normalize(request.message)[:300],
            )
            return validate_decision(ClarificationDecision(type="clarification", question=route.answer).model_dump())
        if route.route == "rag_search":
            normalized = self._normalize(request.message)
            if any(term in normalized for term in ("متاخر", "تاخير", "delayed")) and ("سياسه" in normalized or "policy" in normalized):
                log.info("agent_decision route=unsupported intent=mixed_policy_and_live_data selected_table=none operation=none normalized_message=%s reason=mixed_route_requires_separate_flow", normalized[:300])
                return validate_decision(UnsupportedDecision(type="unsupported").model_dump())
            return await self._rag_decision(request, arabic)
        if self._has_database_catalog(request):
            guarded = self._schema_database_plan(request)
            if guarded:
                if guarded.get("type") == "tool_calls":
                    plan = guarded["tool_calls"][0]["plan"]
                    log.info(
                        "agent_decision route=database_query intent=%s selected_table=%s operation=%s reason=%s",
                        guarded.get("intent"),
                        plan.get("table"),
                        plan.get("operation"),
                        guarded.get("reason"),
                    )
                else:
                    log.info(
                        "agent_decision route=%s intent=%s selected_table=none operation=none reason=%s",
                        guarded.get("type"),
                        guarded.get("intent", "guarded_non_tool"),
                        guarded.get("reason", "deterministic_domain_entity_guard"),
                    )
                guarded.pop("intent", None)
                guarded.pop("reason", None)
                return validate_decision(guarded)
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

    async def _rag_decision(self, request: AgentDecideRequest, arabic: bool):
        search = RagSearchRequest(query=request.message, user_context=request.user_context, top_k=self.settings.max_retrieved_chunks, filters=RagFilters())
        local_results = (await self.retrieval.search(search)).results
        if not local_results:
            answer = "لم أجد مستندات ذات صلة متاحة لك." if arabic else "No relevant authorized documents were found."
            log.info("agent_decision route=rag_search intent=document_or_policy selected_table=none operation=none result=no_authorized_chunks")
            return validate_decision(FinalAnswerDecision(type="final_answer", answer=answer, display=Display(type="answer_with_sources"), sources=[], route="rag_search", requires_rag=True).model_dump())
        answer = self._rag_answer(local_results, arabic)
        log.info("agent_decision route=rag_search intent=document_or_policy selected_table=none operation=none result=chunks chunks=%s", len(local_results))
        return validate_decision(FinalAnswerDecision(type="final_answer", answer=answer, display=Display(type="answer_with_sources", data={"chunks": len(local_results)}), sources=[c.source() for c in local_results], route="rag_search", requires_rag=True).model_dump())

    def _safe_decision_fallback(self, request: AgentDecideRequest, exc: Exception):
        normalized = self._normalize(request.message)
        log.exception(
            "agent_decision route=unsupported intent=decision_pipeline_error selected_table=none operation=none normalized_message=%s error_class=%s",
            normalized[:300],
            exc.__class__.__name__,
        )
        answer = "لا أستطيع تنفيذ هذا الطلب من البيانات المتاحة."
        return validate_decision(UnsupportedDecision(type="unsupported", answer=answer).model_dump())

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
                if isinstance(plan.get("order_by"), list):
                    order_by = plan.get("order_by")
                    plan["order_by"] = order_by[0] if order_by else None
                if isinstance(plan.get("order_by"), dict) and "field" in plan["order_by"] and "column" not in plan["order_by"]:
                    plan["order_by"]["column"] = plan["order_by"].pop("field")
                limit_value = plan.get("limit") or request.rules.max_rows
                plan["limit"] = min(int(limit_value), 20)
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
        except (ValidationError, TypeError, ValueError, AttributeError) as exc:
            reason = exc.errors()[0].get("type") if isinstance(exc, ValidationError) and exc.errors() else exc.__class__.__name__
            log.exception("agent_decision route=unsupported intent=invalid_structured_plan selected_table=none operation=none reason=%s", reason)
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

    def _schema_database_plan(self, request: AgentDecideRequest):
        planned = self.schema_planner.plan(request.message, request.semantic_catalog, request.rules.max_rows)
        if not planned:
            return None
        if planned.get("type") == "tool_calls":
            planned["final_answer_instruction"] = self._instruction(prefer_arabic(request.message, request.locale))
        return planned

    def _normalize(self, value: str) -> str:
        return ArabicNormalizer.normalize(value)

    def _instruction(self, arabic: bool) -> str:
        return "Answer in Arabic using database results and local RAG results." if arabic else "Answer using database results and local RAG results."

    def _rag_answer(self, chunks, arabic: bool) -> str:
        if arabic:
            return "حسب المستندات المتاحة: " + chunks[0].text
        return "Based on the available documents: " + chunks[0].text
