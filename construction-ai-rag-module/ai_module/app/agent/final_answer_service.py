from app.schemas import AgentFinalRequest, AgentFinalResponse, Display
from .citation_validator import answer_with_citations, validate_answer
from .prompt_builder import prefer_arabic
from app.clients.llm_client import LlmClient
from app.config import Settings
import json


class FinalAnswerService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.llm = LlmClient(settings)

    async def final(self, request: AgentFinalRequest) -> AgentFinalResponse:
        arabic = prefer_arabic(request.message, request.locale)
        has_db = bool(request.tool_results)
        has_rag = bool(request.local_rag_results)
        if has_db and has_rag:
            display_type = "mixed"
        elif has_rag:
            display_type = "answer_with_sources"
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
            no_rows_answer = self._empty_delayed_report_answer(request, arabic)
            if no_rows_answer:
                answer = no_rows_answer
            else:
                answer = await self._qwen_database_answer(request, arabic)
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
