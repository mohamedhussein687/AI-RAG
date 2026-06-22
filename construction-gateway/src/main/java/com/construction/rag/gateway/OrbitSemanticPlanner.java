package com.construction.rag.gateway;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.springframework.stereotype.Component;

@Component
class OrbitSemanticPlanner {
  private static final Pattern LIMIT = Pattern.compile("(?:آخر|اخر|last)\\s+(\\d{1,3})");

  boolean identityQuestion(String message) {
    String text = normalize(message);
    return text.contains("انت مين") || text.contains("مين انت") || text.contains("ما اسمك") || text.contains("اسمك ايه")
      || text.contains("انت شغال على مشروع ايه") || text.contains("شغال على مشروع ايه");
  }

  Optional<Map<String, Object>> plan(String message, SemanticCatalog catalog) {
    String text = normalize(message);
    CatalogTable table = chooseTable(text, catalog);
    if (table == null) return Optional.empty();

    if (text.contains("حالات") || text.contains("حسب الحالة") || text.contains("by status")) {
      CatalogColumn status = preferredColumn(table, "status", "project_status", "invoice_status");
      if (status == null) return Optional.empty();
      return Optional.of(tool("group_count", table.logicalName(), null, List.of(), status.logicalName(), null, 20));
    }

    if (text.contains("اعرض") || text.contains("اخر") || text.contains("آخر") || text.contains("مين آخر") || text.contains("last")) {
      CatalogColumn createdAt = preferredColumn(table, "created_at", "date");
      Map<String, Object> orderBy = createdAt == null ? null : Map.of("column", createdAt.logicalName(), "direction", "desc");
      return Optional.of(tool("list", table.logicalName(), null, List.of(), null, orderBy, requestedLimit(text)));
    }

    if (text.contains("اجمالي") || text.contains("إجمالي") || text.contains("total") || text.contains("مجموع")) {
      CatalogColumn amount = preferredColumn(table, "amount", "total", "price", "value", "payment_amount", "paid_amount");
      if (amount == null) return Optional.empty();
      List<Map<String, Object>> filters = monthFilterIfRequested(text, table);
      return Optional.of(tool("sum", table.logicalName(), amount.logicalName(), filters, null, null, 20));
    }

    if (text.contains("كم") || text.contains("عدد") || text.contains("count")) {
      List<Map<String, Object>> filters = new ArrayList<>();
      CatalogColumn status = preferredColumn(table, "status", "project_status", "invoice_status");
      String statusValue = statusValue(text, status);
      if (mentionsStatusLabel(text) && statusValue == null) return Optional.empty();
      if (statusValue != null && status != null) filters.add(filter(status.logicalName(), "eq", statusValue));
      filters.addAll(monthFilterIfRequested(text, table));
      return Optional.of(tool("count", table.logicalName(), null, filters, null, null, 20));
    }

    return Optional.empty();
  }

  private CatalogTable chooseTable(String text, SemanticCatalog catalog) {
    if (text.contains("مشروع") || text.contains("مشاريع") || text.contains("المشاريع") || text.contains("project")) return table(catalog, "projects");
    if (text.contains("عميل") || text.contains("عملاء") || text.contains("customer") || text.contains("client")) {
      CatalogTable clients = table(catalog, "clients");
      return clients != null ? clients : table(catalog, "customers");
    }
    if (text.contains("مستخدم") || text.contains("user")) return table(catalog, "users");
    if (text.contains("فاتور") || text.contains("invoice")) return table(catalog, "invoices");
    if (text.contains("مدفوع") || text.contains("payment")) return table(catalog, "payments");
    return null;
  }

  private CatalogTable table(SemanticCatalog catalog, String name) {
    return catalog.table(name);
  }

  private CatalogColumn preferredColumn(CatalogTable table, String... names) {
    for (String name : names) {
      CatalogColumn column = table.column(name);
      if (column != null) return column;
    }
    return null;
  }

  private String statusValue(String text, CatalogColumn status) {
    if (status == null) return null;
    for (String value : status.enumValues()) {
      String normalized = normalize(value);
      if (!normalized.isBlank() && text.contains(normalized)) return value;
    }
    if (text.contains("waiting")) return "waiting";
    if (text.contains("active")) return "active";
    if (text.contains("غير مدفوعة") || text.contains("غير مدفوع") || text.contains("unpaid")) return "unpaid";
    if (text.contains("paid") || text.contains("مدفوعة") || text.contains("مدفوع")) return "paid";
    return null;
  }

  private boolean mentionsStatusLabel(String text) {
    return text.contains("waiting") || text.contains("active") || text.contains("unpaid") || text.contains("paid")
      || text.contains("غير مدفوعة") || text.contains("غير مدفوع") || text.contains("مدفوعة") || text.contains("مدفوع");
  }

  private List<Map<String, Object>> monthFilterIfRequested(String text, CatalogTable table) {
    if (!(text.contains("الشهر ده") || text.contains("هذا الشهر") || text.contains("this month"))) return List.of();
    CatalogColumn createdAt = preferredColumn(table, "created_at", "date", "payment_date", "invoice_date");
    if (createdAt == null) return List.of();
    return List.of(filter(createdAt.logicalName(), "gte", LocalDate.now().withDayOfMonth(1).toString()));
  }

  private int requestedLimit(String text) {
    Matcher matcher = LIMIT.matcher(text);
    if (matcher.find()) return Math.min(Integer.parseInt(matcher.group(1)), 20);
    return 10;
  }

  private Map<String, Object> tool(String operation, String table, String column, List<Map<String, Object>> filters, String groupBy, Map<String, Object> orderBy, int limit) {
    java.util.LinkedHashMap<String, Object> plan = new java.util.LinkedHashMap<>();
    plan.put("operation", operation);
    plan.put("table", table);
    if (column != null) plan.put("column", column);
    plan.put("filters", filters);
    if (groupBy != null) plan.put("group_by", groupBy);
    if (orderBy != null) plan.put("order_by", orderBy);
    plan.put("limit", limit);
    return Map.of("id", "db_1", "tool", "database_query", "plan", plan);
  }

  private Map<String, Object> filter(String column, String operator, Object value) {
    return Map.of("column", column, "operator", operator, "value", value);
  }

  private String normalize(String value) {
    return value == null ? "" : value.toLowerCase(Locale.ROOT).replace('أ', 'ا').replace('إ', 'ا').replace('آ', 'ا').replace('؟', ' ').trim();
  }
}
