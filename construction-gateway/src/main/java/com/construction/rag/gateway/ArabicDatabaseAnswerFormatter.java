package com.construction.rag.gateway;

import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Component;

@Component
class ArabicDatabaseAnswerFormatter {
  Map<String, Object> answer(String message, Map<?, ?> toolCall, Map<String, Object> result) {
    Map<?, ?> plan = (Map<?, ?>) toolCall.get("plan");
    String operation = String.valueOf(plan.get("operation"));
    String table = String.valueOf(plan.get("table"));
    String entity = arabicEntity(table);
    String answer = switch (operation) {
      case "count" -> countAnswer(entity, plan, result);
      case "group_count" -> "هذه هي أعداد " + entity + " حسب الحالة.";
      case "sum" -> "إجمالي " + entity + " هو " + result.getOrDefault("sum", 0) + ".";
      case "avg" -> "متوسط " + entity + " هو " + result.getOrDefault("avg", 0) + ".";
      case "list" -> "هذه آخر النتائج المتاحة من " + entity + ".";
      default -> "تم استخراج النتيجة من بيانات ORBIT.";
    };
    String displayType = result.containsKey("rows") ? "table" : "metric";
    return Map.of("answer", answer, "display", Map.of("type", displayType, "data", Map.of("tool_results", List.of(result), "citations_valid", true)), "sources", List.of());
  }

  Map<String, Object> identity() {
    return Map.of(
      "answer", "أنا مساعد ORBIT AI، شغال على مشروع ORBIT، وأقدر أساعدك في قراءة وتحليل بيانات المشروع حسب الصلاحيات المتاحة.",
      "display", Map.of("type", "text", "data", Map.of()),
      "sources", List.of()
    );
  }

  Map<String, Object> unsupported(String reason) {
    return Map.of(
      "answer", "لا أستطيع الإجابة عن هذا السؤال حاليًا لأن " + reason + " غير معروف أو غير مسموح في خريطة البيانات.",
      "display", Map.of("type", "text", "data", Map.of("reason", reason)),
      "sources", List.of()
    );
  }

  private String countAnswer(String entity, Map<?, ?> plan, Map<String, Object> result) {
    String status = null;
    Object filters = plan.get("filters");
    if (filters instanceof List<?> list) {
      for (Object item : list) {
        if (item instanceof Map<?, ?> filter && "status".equals(String.valueOf(filter.get("column")))) {
          status = String.valueOf(filter.get("value"));
        }
      }
    }
    Object count = result.getOrDefault("count", 0);
    if (status != null) return "عدد " + entity + " بحالة " + status + " هو " + count + ".";
    return "عدد " + entity + " هو " + count + ".";
  }

  private String arabicEntity(String table) {
    return switch (table) {
      case "projects" -> "المشاريع";
      case "clients", "customers" -> "العملاء";
      case "users" -> "المستخدمين";
      case "invoices" -> "الفواتير";
      case "payments" -> "المدفوعات";
      default -> "السجلات";
    };
  }
}
