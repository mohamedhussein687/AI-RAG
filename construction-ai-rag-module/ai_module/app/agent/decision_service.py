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
import re
from pydantic import ValidationError

SENSITIVE = ("password", "باسورد", "كلمة السر", "secret", "credential", "token")
DOC_TERMS = ("إزاي", "how to", "policy", "سياسة", "procedure", "إجراء", "manual", "دليل", "contract", "عقد", "مستخلص")
DELAY_TERMS = ("متأخر", "delayed", "delay")
ROUTE_ONLY = "__route_only__"
FOLLOW_UP_TERMS = ("اريد عرضهم جميعا", "كلهم", "نعم", "اعرضهم", "هاتهم", "show them", "all of them")
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
        understanding_message = self._message_for_understanding(request)
        if any(term in text for term in SENSITIVE):
            log.info("agent_decision route=forbidden intent=sensitive_data selected_table=none operation=none normalized_message=%s reason=sensitive_term", self._normalize(request.message)[:300])
            return validate_decision(ForbiddenDecision(type="forbidden").model_dump())
        resolved_value_followup = self._resolve_value_followup(request)
        if resolved_value_followup:
            return self._followup_value_decision(request, resolved_value_followup, arabic)
        route = self.router.route(request.message, self._has_database_catalog(request))
        if route.route == "conversational":
            log.info(
                "agent_decision route=conversational intent=%s selected_table=none operation=none normalized_message=%s reason=message_router",
                route.intent,
                self._normalize(request.message)[:300],
            )
            return validate_decision(FinalAnswerDecision(type="final_answer", answer=route.answer, display=Display(type="text", data={"conversation_type": route.intent}), sources=[]).model_dump())

        qwen_decision = await self._qwen_primary_decision(request, arabic, understanding_message)
        if qwen_decision is not None:
            if isinstance(qwen_decision, dict) and qwen_decision.get(ROUTE_ONLY) in {"rag_search", "hybrid"}:
                return await self._rag_decision(request, arabic, route=str(qwen_decision[ROUTE_ONLY]))
            return qwen_decision

        if self._has_database_catalog(request):
            guarded = self._schema_database_plan(request, understanding_message)
            if guarded:
                return self._validated_guarded_decision(guarded)

        is_doc = any(term.lower() in text for term in DOC_TERMS)
        is_mixed = (any(t in text for t in DELAY_TERMS) and ("سياسة" in text or "policy" in text))

        local_results = []
        if is_doc or is_mixed:
            search = RagSearchRequest(query=request.message, user_context=request.user_context, top_k=self.settings.max_retrieved_chunks, filters=RagFilters())
            local_results = (await self.retrieval.search(search)).results

        if is_mixed:
            return await self._rag_decision(request, arabic, route="hybrid")

        if is_doc:
            if not local_results:
                return await self._qwen_empty_context_answer(request, arabic, route="rag_search")
            answer = self._rag_answer(local_results, arabic)
            return validate_decision(FinalAnswerDecision(type="final_answer", answer=answer, display=Display(type="answer_with_sources", data={"chunks": len(local_results)}), sources=[c.source() for c in local_results]).model_dump())

        question = "هل يمكنك توضيح البيانات أو المستندات المطلوبة؟" if arabic else "Can you clarify what data or documents you need?"
        return validate_decision(ClarificationDecision(type="clarification", question=question).model_dump())

    async def _rag_decision(self, request: AgentDecideRequest, arabic: bool, route: str = "rag_search"):
        search = RagSearchRequest(query=request.message, user_context=request.user_context, top_k=self.settings.max_retrieved_chunks, filters=RagFilters())
        local_results = (await self.retrieval.search(search)).results
        if not local_results:
            log.info("agent_decision route=%s intent=document_or_policy selected_table=none operation=none result=no_authorized_chunks reason=qwen_empty_context_fallback", route)
            return await self._qwen_empty_context_answer(request, arabic, route=route)
        answer = self._rag_answer(local_results, arabic)
        log.info("agent_decision route=%s intent=document_or_policy selected_table=none operation=none result=chunks chunks=%s", route, len(local_results))
        return validate_decision(FinalAnswerDecision(type="final_answer", answer=answer, display=Display(type="answer_with_sources", data={"chunks": len(local_results)}), sources=[c.source() for c in local_results], route=route, requires_rag=True).model_dump())

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

    async def _qwen_primary_decision(self, request: AgentDecideRequest, arabic: bool, understanding_message: str):
        messages = [
            {
                "role": "system",
                "content": (
                    "You are Qwen, the primary intent understanding engine for an Arabic-first RAG and database assistant. "
                    "Classify every normal user message before any unsupported fallback. Return exactly one strict JSON object and nothing else. "
                    "Use resolved_question_for_intent for intent classification and database planning when it differs from question; it may include prior conversation context for vague follow-ups. "
                    "Use question for final wording and user-facing tone. "
                    "Valid routes are conversational, rag_search, database_query, hybrid, direct_answer, clarification_needed, unsupported. "
                    "Use unsupported only for unsafe, impossible, or clearly out-of-scope requests after considering whether a direct answer, clarification, RAG search, or database query is possible. "
                    "Do not mark a question unsupported merely because wording is unfamiliar or because retrieved documents may be empty. "
                    "For greetings, small-talk, wellbeing questions, thanks, and conversational messages, return final_answer with route=conversational and a natural Arabic answer. "
                    "For general explanation questions that do not require private project facts, return final_answer with route=direct_answer and answer normally in Arabic. "
                    "For questions about indexed knowledge or documents, return {\"route\":\"rag_search\"}. "
                    "For questions that need both database facts and documents, return {\"route\":\"hybrid\"}. "
                    "For ambiguous but answerable questions, return clarification with a helpful Arabic question. "
                    "For operational counts, statistics, details, latest records, filters, grouping, sorting, or aggregation, return a database_query tool-call plan. "
                    "Never output SQL, SELECT, FROM, executable query text, markdown, explanations, tables not in catalog, columns not in catalog, values not supported by catalog, joins, or credentials. "
                    "Use only the semantic catalog for database plans. Spring validates and executes plans; you only describe structured intent. "
                    "For identity questions such as who are you, your name, or what project you work on, do not call tools. Return exactly "
                    '{"type":"final_answer","route":"conversational","answer":"أنا مساعد ORBIT AI، شغال على مشروع ORBIT، وأقدر أساعدك في قراءة وتحليل بيانات المشروع حسب الصلاحيات المتاحة.","display":{"type":"text","data":{}},"sources":[]}. '
                    "The domain_entities section contains authoritative business mappings. Operational project questions in Arabic or English must use domain entity projects and table projects. "
                    "Never use CMS/content/website tables such as about_us, pages, settings, banners, sliders, or web_* for operational business questions unless the user explicitly asks about website content. "
                    "The catalog has tables_index for choosing entities and allowed table operations. Detailed tables include columns for filters, grouping, sorting, lists, and aggregates. "
                    "For simple count questions you may use a table from tables_index when count is allowed, even if that table is not in detailed tables. "
                    "For filters, grouping, sorting, listing, or aggregates, use only columns present in detailed tables. "
                    "For a count, output this exact shape with the chosen table: "
                    '{"type":"tool_calls","tool_calls":[{"id":"db_1","tool":"database_query","plan":{"operation":"count","table":"logical_table","filters":[],"limit":20}}],"local_rag_results":[],"final_answer_instruction":"Answer in Arabic."}. '
                    "For list/group/aggregate, use the same top-level shape and only add allowed plan fields from this set: column, filters, group_by, order_by, limit. "
                    'If truly unsupported, output exactly {"type":"unsupported","route":"unsupported","answer":"لا أستطيع تنفيذ هذا الطلب من البيانات المتاحة."}. '
                    "Equivalent natural-language phrasings must produce the same plan."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "question": request.message,
                        "resolved_question_for_intent": understanding_message,
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
            log.info("agent_decision route=clarification intent=unknown selected_table=none operation=none reason=empty_llm_response")
            return None
        if isinstance(decision, dict) and decision.get("route") in {"rag_search", "hybrid"} and "type" not in decision:
            log.info("agent_decision route=%s intent=llm_route_only selected_table=none operation=none reason=qwen_primary_decision", decision.get("route"))
            return {ROUTE_ONLY: decision.get("route")}
        if isinstance(decision, dict) and decision.get("route") == "direct_answer" and "type" not in decision:
            answer = decision.get("answer") if isinstance(decision.get("answer"), str) and decision.get("answer").strip() else None
            if not answer:
                return await self._qwen_direct_answer(request, arabic)
            decision = {"type": "final_answer", "route": "direct_answer", "answer": answer, "display": {"type": "text", "data": {}}, "sources": []}
        if isinstance(decision, dict) and decision.get("route") == "clarification_needed" and "type" not in decision:
            question = decision.get("question") or decision.get("answer") or ("هل يمكنك توضيح المطلوب أكثر؟" if arabic else "Can you clarify what you need?")
            decision = {"type": "clarification", "route": "clarification_needed", "question": str(question)}
        if decision.get("type") == "tool_calls":
            decision["local_rag_results"] = []
            decision["final_answer_instruction"] = self._instruction(arabic)
            decision["route"] = decision.get("route") or "database_query"
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
                self._normalize_structured_plan(plan, understanding_message)
                log.info(
                    "agent_decision route=database_query intent=llm_structured selected_table=%s operation=%s reason=qwen_plan",
                    plan.get("table"),
                    plan.get("operation"),
                )
        elif decision.get("type") == "final_answer":
            decision["route"] = decision.get("route") or "direct_answer"
            if decision.get("route") == "conversational" and self._looks_like_database_request(understanding_message):
                log.warning("agent_decision route=database_query intent=misrouted_conversation selected_table=none operation=none reason=qwen_conversational_for_database_request")
                return None
            log.info("agent_decision route=%s intent=llm_final_answer selected_table=none operation=none reason=qwen_primary_decision", decision.get("route"))
        elif decision.get("type") == "clarification":
            decision["route"] = decision.get("route") or "clarification_needed"
            log.info("agent_decision route=%s intent=llm_clarification selected_table=none operation=none reason=qwen_primary_decision", decision.get("route"))
        elif decision.get("type") == "unsupported":
            decision["route"] = "unsupported"
            if self._looks_like_database_request(understanding_message):
                log.info("agent_decision route=database_query intent=unsupported_database_request selected_table=none operation=none reason=qwen_unsupported_but_schema_may_plan")
                return None
            log.info("agent_decision route=unsupported intent=llm_unsupported selected_table=none operation=none reason=qwen_primary_decision")
        else:
            log.info("agent_decision route=%s intent=llm_non_tool selected_table=none operation=none reason=qwen_decision", decision.get("type"))
        try:
            return validate_decision(decision)
        except (ValidationError, TypeError, ValueError, AttributeError) as exc:
            reason = exc.errors()[0].get("type") if isinstance(exc, ValidationError) and exc.errors() else exc.__class__.__name__
            log.exception("agent_decision route=unsupported intent=invalid_structured_plan selected_table=none operation=none reason=%s", reason)
            return validate_decision(UnsupportedDecision(type="unsupported").model_dump())

    async def _qwen_direct_answer(self, request: AgentDecideRequest, arabic: bool):
        messages = [
            {
                "role": "system",
                "content": (
                    "Answer the user's general question directly in Arabic when possible. "
                    "Do not invent private project-specific facts. If project-specific data is required, ask a short Arabic clarification. "
                    "Return exactly one JSON object with either {\"answer\":\"...\"} or {\"question\":\"...\"}."
                ),
            },
            {
                "role": "user",
                "content": json.dumps({"question": request.message, "locale": request.locale}, ensure_ascii=False),
            },
        ]
        data = await self.llm.chat_json(messages)
        if isinstance(data, dict) and isinstance(data.get("answer"), str) and data["answer"].strip():
            return validate_decision(FinalAnswerDecision(type="final_answer", route="direct_answer", answer=data["answer"].strip(), display=Display(type="text"), sources=[]).model_dump())
        question = data.get("question") if isinstance(data, dict) and isinstance(data.get("question"), str) else ("هل يمكنك توضيح المطلوب أكثر؟" if arabic else "Can you clarify what you need?")
        return validate_decision(ClarificationDecision(type="clarification", route="clarification_needed", question=question).model_dump())

    async def _qwen_empty_context_answer(self, request: AgentDecideRequest, arabic: bool, route: str):
        messages = [
            {
                "role": "system",
                "content": (
                    "The RAG search returned no authorized documents. Do not automatically say unavailable. "
                    "Answer generally if the question is general. If it asks for project-specific facts that require unavailable documents or database data, ask a helpful Arabic clarification or explain that specific evidence is missing. "
                    "Do not invent project-specific facts. Return exactly one JSON object with answer or question."
                ),
            },
            {
                "role": "user",
                "content": json.dumps({"question": request.message, "locale": request.locale, "retrieved_context": []}, ensure_ascii=False),
            },
        ]
        try:
            data = await self.llm.chat_json(messages)
        except Exception:
            data = {}
        if isinstance(data, dict) and isinstance(data.get("answer"), str) and data["answer"].strip():
            return validate_decision(FinalAnswerDecision(type="final_answer", route=route, answer=data["answer"].strip(), display=Display(type="answer_with_sources"), sources=[], requires_rag=True).model_dump())
        question = data.get("question") if isinstance(data, dict) and isinstance(data.get("question"), str) else ("هل تقصد سؤالًا عامًا أم تريد إجابة من مستندات مشروع محدد؟" if arabic else "Do you mean a general question or an answer from a specific project's documents?")
        return validate_decision(ClarificationDecision(type="clarification", route="clarification_needed", question=question).model_dump())

    def _validated_guarded_decision(self, guarded: dict):
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
                guarded.get("reason", "schema_fallback_after_qwen"),
            )
        guarded.pop("intent", None)
        guarded.pop("reason", None)
        return validate_decision(guarded)

    def _schema_database_plan(self, request: AgentDecideRequest, message: str | None = None):
        planned = self.schema_planner.plan(message or request.message, request.semantic_catalog, request.rules.max_rows)
        if not planned:
            return None
        if planned.get("type") == "tool_calls":
            planned["final_answer_instruction"] = self._instruction(prefer_arabic(request.message, request.locale))
        return planned

    def _normalize_structured_plan(self, plan: dict, message: str) -> None:
        table = str(plan.get("table") or "")
        operation = str(plan.get("operation") or "")
        columns = [str(column) for column in plan.get("columns") or [] if column]
        self._normalize_plan_filters(plan)
        if columns and not plan.get("fields"):
            plan["fields"] = columns

        if table == "clients":
            plan.setdefault("entities", ["clients"])
            if operation == "count":
                plan.setdefault("intent", "count_clients")
            elif operation in {"list", "select"}:
                if self._client_name_request(message) and not columns:
                    plan["columns"] = ["name"]
                    plan["fields"] = ["name"]
                plan.setdefault("intent", "list_clients")
        elif table == "users":
            plan.setdefault("entities", ["users"])
            if operation == "count":
                plan.setdefault("intent", "count_users")
            elif operation in {"list", "select"}:
                if self._user_name_request(message) and not columns:
                    plan["columns"] = ["name"]
                    plan["fields"] = ["name"]
                plan.setdefault("intent", "list_users")

    def _client_name_request(self, message: str) -> bool:
        text = self._normalize(message)
        return any(ArabicNormalizer.contains_term(text, term) for term in ("اسم", "اسماء", "الاسماء", "name", "names"))

    def _user_name_request(self, message: str) -> bool:
        text = self._normalize(message)
        return any(ArabicNormalizer.contains_term(text, term) for term in ("اسم", "اسماء", "الاسماء", "name", "names"))

    @staticmethod
    def _normalize_plan_filters(plan: dict) -> None:
        operator_aliases = {
            "=": "eq",
            "==": "eq",
            "!=": "ne",
            "<>": "ne",
            ">": "gt",
            ">=": "gte",
            "<": "lt",
            "<=": "lte",
        }
        filters = plan.get("filters")
        if not isinstance(filters, list):
            return
        for item in filters:
            if not isinstance(item, dict):
                continue
            if "field" in item and "column" not in item:
                item["column"] = item.pop("field")
            operator = item.get("operator")
            if isinstance(operator, str):
                item["operator"] = operator_aliases.get(operator.strip(), operator)

    def _message_for_understanding(self, request: AgentDecideRequest) -> str:
        if not self._is_vague_follow_up(request.message):
            return request.message
        previous = self._last_database_intent_message(request)
        if not previous:
            return request.message
        resolved = f"{previous}. المتابعة الحالية: {request.message}"
        log.info(
            "agent_decision route=database_query intent=follow_up_resolution selected_table=pending operation=pending normalized_message=%s previous_intent=%s",
            self._normalize(request.message)[:200],
            self._normalize(previous)[:200],
        )
        return resolved

    def _last_database_intent_message(self, request: AgentDecideRequest) -> str | None:
        for item in reversed(request.conversation_history):
            if item.role != "user":
                continue
            if self._looks_like_database_request(item.content):
                return item.content
        return None

    def _is_vague_follow_up(self, message: str) -> bool:
        text = self._normalize(message)
        return any(ArabicNormalizer.contains_term(text, term) for term in FOLLOW_UP_TERMS)

    def _looks_like_database_request(self, message: str) -> bool:
        text = self._normalize(message)
        if self.router.looks_like_database_request(text):
            return True
        if self._is_vague_follow_up(text):
            return True
        return False

    def _resolve_value_followup(self, request: AgentDecideRequest) -> dict | None:
        text = self._normalize(request.message)
        if not self._looks_like_value_meaning_question(text):
            return None
        rows_context = self._previous_result_rows(request)
        if not rows_context:
            return None
        value = self._referenced_value(request.message)
        field_hint = self._referenced_field(text)
        for result in rows_context:
            table = str(result.get("table") or "").strip()
            if not table:
                continue
            for row in result.get("rows") or []:
                if not isinstance(row, dict):
                    continue
                matched_field, matched_value = self._match_row_field_value(row, field_hint, value)
                if matched_field is None:
                    continue
                entity = self._row_entity_label(row)
                context = {
                    "source_table": table,
                    "source_field": matched_field,
                    "source_value": matched_value,
                    "source_entity": entity,
                }
                log.info(
                    "agent_decision route=hybrid intent=value_followup_resolution selected_table=%s operation=meaning_lookup source_field=%s normalized_message=%s",
                    table,
                    matched_field,
                    text[:300],
                )
                return context
        return None

    def _followup_value_decision(self, request: AgentDecideRequest, context: dict, arabic: bool):
        meaning = self._known_value_meaning(request.semantic_catalog, context["source_table"], context["source_field"], context["source_value"])
        if meaning:
            answer = (
                f"القيمة {context['source_field']}={context['source_value']} الخاصة بـ {context['source_entity']} تعني: {meaning}."
                if arabic
                else f"The value {context['source_field']}={context['source_value']} for {context['source_entity']} means: {meaning}."
            )
        else:
            answer = (
                f"القيمة {context['source_field']}={context['source_value']} موجودة في جدول {context['source_table']}"
                f" للكيان {context['source_entity']}، لكن لا يوجد في البيانات الحالية تعريف واضح لمعنى هذا النوع. "
                "نحتاج جدول مرجعي أو mapping يوضح أنواع الحسابات."
                if arabic
                else (
                    f"The value {context['source_field']}={context['source_value']} exists in table {context['source_table']} "
                    f"for {context['source_entity']}, but the current data does not include a clear mapping for this value."
                )
            )
        return validate_decision(
            FinalAnswerDecision(
                type="final_answer",
                route="hybrid",
                answer=answer,
                display=Display(type="text", data={"followup_context": context}),
                sources=[],
                requires_database=True,
                requires_rag=True,
                requires_context=True,
                resolved_followup=True,
                followup_context=context,
            ).model_dump()
        )

    def _looks_like_value_meaning_question(self, text: str) -> bool:
        meaning_terms = ("يعني", "معني", "معنى", "اشرح", "تفسير", "meaning", "what does", "ده معناه", "معناه ايه")
        value_terms = ("نوع", "type", "الحاله", "الحالة", "status", "الرقم", "number", "value", "القيمه", "القيمة")
        return any(term in text for term in meaning_terms) and any(term in text for term in value_terms)

    def _previous_result_rows(self, request: AgentDecideRequest) -> list[dict]:
        results: list[dict] = []
        for item in request.tool_results:
            if not isinstance(item, dict):
                continue
            result = item.get("result") if isinstance(item.get("result"), dict) else item
            rows = result.get("rows") if isinstance(result, dict) else None
            if isinstance(rows, list):
                results.append(result)
        return results

    def _referenced_field(self, text: str) -> str | None:
        if any(term in text for term in ("نوع الحساب", "النوع", "نوع", "type")):
            return "type"
        if any(term in text for term in ("الحاله", "الحالة", "status")):
            return "status"
        return None

    def _referenced_value(self, message: str) -> str | int | float | None:
        match = re.search(r"(?<![\w.-])([0-9]+(?:\.[0-9]+)?)(?![\w.-])", message)
        if not match:
            return None
        raw = match.group(1)
        if "." in raw:
            return float(raw)
        return int(raw)

    def _match_row_field_value(self, row: dict, field_hint: str | None, value: str | int | float | None) -> tuple[str | None, object | None]:
        if field_hint and field_hint in row:
            row_value = row.get(field_hint)
            if value is None or self._same_value(row_value, value):
                return field_hint, row_value
        if value is not None:
            candidates = []
            for field, row_value in row.items():
                if str(field).lower() in {"id", "created_at", "updated_at", "deleted_at"}:
                    continue
                if self._same_value(row_value, value):
                    candidates.append((str(field), row_value))
            if len(candidates) == 1:
                return candidates[0]
            if field_hint:
                for field, row_value in candidates:
                    if field == field_hint:
                        return field, row_value
        if field_hint:
            return None, None
        numeric = [
            (str(field), row_value)
            for field, row_value in row.items()
            if str(field).lower() not in {"id", "created_at", "updated_at", "deleted_at"} and isinstance(row_value, int | float)
        ]
        if len(numeric) == 1:
            return numeric[0]
        return None, None

    @staticmethod
    def _same_value(left: object, right: object) -> bool:
        return str(left).strip().lower() == str(right).strip().lower()

    @staticmethod
    def _row_entity_label(row: dict) -> str:
        for field in ("name", "full_name", "title", "username", "email", "code", "project_code"):
            value = row.get(field)
            if value not in (None, ""):
                return str(value)
        return "السجل السابق"

    @staticmethod
    def _known_value_meaning(catalog: dict, table: str, field: str, value: object) -> str | None:
        for table_item in catalog.get("tables", []):
            if table_item.get("name") != table:
                continue
            for column in table_item.get("columns", []):
                if not isinstance(column, dict) or column.get("name") != field:
                    continue
                enum_values = column.get("enum_values") or []
                for enum_item in enum_values:
                    if isinstance(enum_item, dict) and str(enum_item.get("value")).strip().lower() == str(value).strip().lower():
                        label = enum_item.get("label") or enum_item.get("name") or enum_item.get("meaning")
                        return str(label) if label else None
                    if isinstance(enum_item, str) and ":" in enum_item:
                        raw_value, label = enum_item.split(":", 1)
                        if raw_value.strip().lower() == str(value).strip().lower():
                            return label.strip()
        return None

    def _normalize(self, value: str) -> str:
        return ArabicNormalizer.normalize(value)

    def _instruction(self, arabic: bool) -> str:
        return "Answer in Arabic using database results and local RAG results." if arabic else "Answer using database results and local RAG results."

    def _rag_answer(self, chunks, arabic: bool) -> str:
        if arabic:
            return "حسب المستندات المتاحة: " + chunks[0].text
        return "Based on the available documents: " + chunks[0].text
