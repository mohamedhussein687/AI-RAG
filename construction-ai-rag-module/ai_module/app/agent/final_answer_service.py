from app.schemas import AgentFinalRequest, AgentFinalResponse, Display
from .citation_validator import answer_with_citations, validate_answer
from .prompt_builder import prefer_arabic
from app.clients.llm_client import LlmClient
from app.config import Settings
from app.schema.schema_models import is_sensitive_field
import json


class FinalAnswerService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.llm = LlmClient(settings)

    async def final(self, request: AgentFinalRequest) -> AgentFinalResponse:
        arabic = prefer_arabic(request.message, request.locale)
        has_db = bool(request.tool_results)
        has_rag = bool(request.local_rag_results)
        if self._contains_sensitive_tool_result(request):
            answer = (
                "لا أستطيع عرض كلمات المرور أو الرموز أو المفاتيح أو أي بيانات حساسة."
                if arabic
                else "I cannot display passwords, tokens, keys, or other sensitive data."
            )
            return AgentFinalResponse(answer=answer, display=Display(type="text", data={"refusal": "sensitive_tool_result"}), sources=[])
        if has_db and has_rag:
            display_type = "mixed"
        elif has_rag:
            display_type = "answer_with_sources"
        elif self._has_metric(request):
            display_type = "metric"
        elif self._has_rows(request):
            display_type = "table"
        elif has_db:
            display_type = "metric"
        else:
            display_type = "text"

        if has_db and has_rag:
            base_answer = "النتيجة تعتمد على بيانات النظام والمستندات المتاحة." if arabic else "The answer uses system data and available documents."
            answer = answer_with_citations(base_answer, request.local_rag_results)
        elif has_rag:
            prefix = "حسب المستندات المتاحة:" if arabic else "Based on the available documents:"
            answer = answer_with_citations(prefix, request.local_rag_results)
        elif has_db:
            validation_error_answer = self._validation_error_answer(request, arabic)
            if validation_error_answer:
                answer = validation_error_answer
            else:
                no_rows_answer = self._empty_delayed_report_answer(request, arabic)
                if not no_rows_answer:
                    no_rows_answer = self._empty_project_details_answer(request, arabic)
                if no_rows_answer:
                    answer = no_rows_answer
                else:
                    empty_search_answer = self._empty_database_search_answer(request, arabic)
                    if empty_search_answer:
                        answer = empty_search_answer
                    elif self.settings.fake_llm:
                        answer = self._deterministic_database_answer(request, arabic) or await self._qwen_database_answer(request, arabic)
                    else:
                        answer = await self._qwen_database_answer(request, arabic) or self._deterministic_database_answer(request, arabic)
        else:
            answer = "لا توجد نتائج كافية للإجابة." if arabic else "There is not enough evidence to answer."

        validation = validate_answer(answer, request.local_rag_results)
        if has_rag and not validation.sources:
            safe_answer = "لا توجد أدلة موثقة كافية للإجابة." if arabic else "There is not enough validated evidence to answer."
            return AgentFinalResponse(answer=safe_answer, display=Display(type="text", data={"validation": "no_valid_citations"}), sources=[])
        return AgentFinalResponse(answer=validation.answer, display=Display(type=display_type, data={"tool_results": [r.result for r in request.tool_results], "citations_valid": validation.valid}), sources=validation.sources)

    def _has_rows(self, request: AgentFinalRequest) -> bool:
        for result in request.tool_results:
            if isinstance(result.result, dict) and isinstance(result.result.get("rows"), list):
                return True
        return False

    def _has_metric(self, request: AgentFinalRequest) -> bool:
        for result in request.tool_results:
            if isinstance(result.result, dict) and (result.result.get("operation") == "count" or "count" in result.result):
                return True
        return False

    def _contains_sensitive_tool_result(self, request: AgentFinalRequest) -> bool:
        for item in request.tool_results:
            if self._contains_sensitive_value(item.result):
                return True
        return False

    def _contains_sensitive_value(self, value) -> bool:
        if isinstance(value, dict):
            for key, nested in value.items():
                if is_sensitive_field(str(key)):
                    return True
                if self._contains_sensitive_value(nested):
                    return True
        if isinstance(value, list):
            return any(self._contains_sensitive_value(item) for item in value)
        return False

    def _summarize_tool_results(self, request: AgentFinalRequest, arabic: bool) -> str:
        result = request.tool_results[0].result if request.tool_results else {}
        if isinstance(result, dict):
            for key in ("count", "sum", "value"):
                if key in result:
                    return (f"القيمة هي {result[key]}." if arabic else f"The value is {result[key]}.")
        return "تم استلام نتائج البيانات من النظام." if arabic else "Received data results from the system."

    async def _qwen_database_answer(self, request: AgentFinalRequest, arabic: bool) -> str:
        if self.settings.fake_llm:
            return self._summarize_tool_results(request, arabic)
        messages = [
            {
                "role": "system",
                "content": (
                    "You write the final user-facing answer from trusted database query results. "
                    "Do not invent numbers, do not mention SQL, do not reveal internal tokens or credentials, and do not add unsupported facts. "
                    "Answer naturally in Arabic when the user asks in Arabic. Return exactly one JSON object with key answer."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "question": request.message,
                        "locale": request.locale,
                        "query_results": [r.result for r in request.tool_results],
                        "instruction": request.final_answer_instruction,
                        "style": (
                            "natural conversational Arabic; include thousands separators for large numbers when useful. "
                            "For delayed_projects_report, format as a short Arabic report with title, total results, and for each project: name, status, planned delivery date, delay days if present, and last update if present."
                        ),
                    },
                    ensure_ascii=False,
                ),
            },
        ]
        data = await self.llm.chat_json(messages)
        answer = data.get("answer") if isinstance(data, dict) else None
        if isinstance(answer, str) and answer.strip():
            return answer.strip()
        return self._summarize_tool_results(request, arabic)

    def _empty_delayed_report_answer(self, request: AgentFinalRequest, arabic: bool) -> str | None:
        for result in request.tool_results:
            payload = result.result
            if isinstance(payload, dict) and payload.get("intent") == "delayed_projects_report" and payload.get("rows") == []:
                return "لا توجد مشاريع متأخرة في التسليم حسب البيانات الحالية." if arabic else "There are no delayed projects based on the current data."
        return None

    def _validation_error_answer(self, request: AgentFinalRequest, arabic: bool) -> str | None:
        for result in request.tool_results:
            payload = result.result
            if not isinstance(payload, dict) or payload.get("operation") != "validation_error":
                continue
            requested_table = payload.get("requested_table") or "المطلوب"
            if arabic:
                return f"لا أستطيع تنفيذ هذا الاستعلام لأن الجدول أو الحقول المطلوبة غير موجودة أو غير مسموحة لهذا المشروع: {requested_table}."
            return f"I cannot run this query because the requested table or fields are missing or not allowed for this project: {requested_table}."
        return None

    def _empty_project_details_answer(self, request: AgentFinalRequest, arabic: bool) -> str | None:
        for result in request.tool_results:
            payload = result.result
            if isinstance(payload, dict) and payload.get("intent") == "project_details" and payload.get("rows") == []:
                lookup = payload.get("lookup_value") or "المطلوب"
                if payload.get("lookup_type") == "project_code":
                    return f"لم أجد مشروعًا بالكود {lookup} في البيانات الحالية." if arabic else f"No project with code {lookup} was found in the current data."
                return f"لم أجد مشروعًا باسم أو كود {lookup} في البيانات الحالية." if arabic else f"No project named or coded {lookup} was found in the current data."
        return None

    def _empty_database_search_answer(self, request: AgentFinalRequest, arabic: bool) -> str | None:
        for result in request.tool_results:
            payload = result.result
            if not isinstance(payload, dict):
                continue
            if payload.get("operation") not in {"select", "details"} or payload.get("rows") != []:
                continue
            filters = []
            summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
            for item in summary.get("filters", []) if isinstance(summary, dict) else []:
                if isinstance(item, dict) and item.get("value") not in (None, ""):
                    filters.append((item.get("column"), item.get("value")))
            if not filters:
                return None
            columns = ", ".join(str(column) for column, _value in filters if column)
            values = "، ".join(f'"{value}"' for _column, value in filters)
            if arabic:
                return f"لم أجد نتائج مطابقة للبحث عن {values} في الأعمدة المتاحة: {columns}."
            return f"No matching rows were found for {values} in the available columns: {columns}."
        return None

    def _deterministic_database_answer(self, request: AgentFinalRequest, arabic: bool) -> str | None:
        if not arabic:
            return None
        for result in request.tool_results:
            payload = result.result
            if not isinstance(payload, dict):
                continue
            if payload.get("operation") == "count" and "count" in payload:
                table = payload.get("table") or "السجلات"
                return f"العدد الحالي في {table} هو {payload.get('count')}."
            rows = payload.get("rows")
            if not isinstance(rows, list) or not rows:
                return None
            if payload.get("operation") in {"list", "select"} and payload.get("intent") not in {"latest_project", "project_details"}:
                return self._rows_answer(payload, arabic)
            if payload.get("intent") != "latest_project" and (payload.get("intent") != "project_details" or payload.get("lookup_type") != "project_code"):
                continue
            row = rows[0] if isinstance(rows[0], dict) else {}
            if payload.get("intent") == "latest_project":
                title = row.get("title") or "بدون اسم"
                parts = [f"آخر مشروع تم إضافته هو: {title}"]
            else:
                title = row.get("title") or "بدون اسم"
                parts = [f"بيانات المشروع: {title}"]
            if row.get("project_code"):
                parts.append(f"الكود: {row.get('project_code')}")
            if row.get("status") is not None:
                parts.append(f"الحالة: {row.get('status')}")
            if row.get("client") is not None:
                parts.append(f"العميل: {row.get('client')}")
            elif row.get("client_id") is not None:
                parts.append(f"العميل: {row.get('client_id')}")
            if row.get("start_date"):
                parts.append(f"تاريخ البداية: {row.get('start_date')}")
            if row.get("planned_delivery_date"):
                parts.append(f"تاريخ التسليم/النهاية: {row.get('planned_delivery_date')}")
            elif row.get("end_date"):
                parts.append(f"تاريخ التسليم/النهاية: {row.get('end_date')}")
            for progress_key in ("progress_percentage", "progress", "percentage"):
                if row.get(progress_key) is not None:
                    parts.append(f"نسبة الإنجاز: {row.get(progress_key)}")
                    break
            if row.get("created_at"):
                parts.append(f"تاريخ الإضافة: {row.get('created_at')}")
            if row.get("updated_at"):
                parts.append(f"آخر تحديث: {row.get('updated_at')}")
            return "، ".join(parts) + "."
        return None

    def _rows_answer(self, payload: dict, arabic: bool) -> str | None:
        rows = payload.get("rows")
        if not isinstance(rows, list) or not rows or not all(isinstance(row, dict) for row in rows):
            return None
        table = str(payload.get("table") or "records")
        visible_rows = rows[:10]
        if not arabic:
            return f"Found {len(rows)} row(s) in {table}: " + "; ".join(", ".join(f"{k}: {v}" for k, v in row.items()) for row in visible_rows)
        names = []
        for row in visible_rows:
            if len(row) == 1:
                names.append(str(next(iter(row.values()))))
            else:
                names.append("، ".join(f"{key}: {value}" for key, value in row.items()))
        prefix = f"وجدت {len(rows)} نتيجة في {table}: "
        return prefix + "؛ ".join(names) + "."
