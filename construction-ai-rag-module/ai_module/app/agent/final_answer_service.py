from app.schemas import AgentFinalRequest, AgentFinalResponse, Display
from .prompt_builder import prefer_arabic


class FinalAnswerService:
    async def final(self, request: AgentFinalRequest) -> AgentFinalResponse:
        arabic = prefer_arabic(request.message, request.locale)
        sources = [chunk.source() for chunk in request.local_rag_results]
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
            answer = "النتيجة تعتمد على بيانات النظام والمستندات المتاحة." if arabic else "The answer uses system data and available documents."
        elif has_rag:
            answer = ("حسب المستندات المتاحة: " if arabic else "Based on the available documents: ") + request.local_rag_results[0].text
        elif has_db:
            answer = self._summarize_tool_results(request, arabic)
        else:
            answer = "لا توجد نتائج كافية للإجابة." if arabic else "There is not enough evidence to answer."
        return AgentFinalResponse(answer=answer, display=Display(type=display_type, data={"tool_results": [r.result for r in request.tool_results]}), sources=sources)

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
