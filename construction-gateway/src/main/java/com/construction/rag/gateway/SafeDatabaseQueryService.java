package com.construction.rag.gateway;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import javax.sql.DataSource;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@Component
class SafeDatabaseQueryService {
  private static final int DEFAULT_MAX_LIMIT = 20;

  private final ClientDataSourceManager dataSources;
  private final SemanticCatalogService catalogs;

  SafeDatabaseQueryService(ClientDataSourceManager dataSources, SemanticCatalogService catalogs) {
    this.dataSources = dataSources;
    this.catalogs = catalogs;
  }

  Mono<Map<String, Object>> execute(RagClient client, Map<?, ?> toolCall) {
    return Mono.fromCallable(() -> executeBlocking(client, toolCall)).subscribeOn(Schedulers.boundedElastic());
  }

  private Map<String, Object> executeBlocking(RagClient client, Map<?, ?> toolCall) throws Exception {
    SemanticCatalog catalog = catalogs.catalog(client);
    Map<?, ?> plan = requireMap(toolCall.get("plan"), "plan");
    String operation = string(plan.get("operation"));
    String table = identifier(plan.get("table"));
    CatalogTable catalogTable = catalog.table(table);
    if (catalogTable == null) throw new IllegalArgumentException("table is not allowlisted");
    if (!catalogTable.allowedOperations().contains(operation)) throw new IllegalArgumentException("operation is not allowlisted");

    List<?> filters = plan.get("filters") instanceof List<?> list ? list : List.of();
    List<Object> params = new ArrayList<>();
    String where = buildWhere(filters, catalogTable, params);
    int limit = limit(plan.get("limit"));
    String sql = buildSql(operation, plan, catalogTable, where, limit);
    DataSource dataSource = dataSources.dataSource(client);
    try (Connection connection = dataSource.getConnection()) {
      connection.setReadOnly(true);
      validateActualSchema(connection, catalogTable, plan, filters);
      try (PreparedStatement statement = connection.prepareStatement(sql)) {
        statement.setQueryTimeout(10);
        for (int i = 0; i < params.size(); i++) statement.setObject(i + 1, params.get(i));
        try (ResultSet rs = statement.executeQuery()) {
          return readResult(operation, plan, catalogTable, rs);
        }
      }
    }
  }

  private String buildSql(String operation, Map<?, ?> plan, CatalogTable table, String where, int limit) {
    String physicalTable = table.physicalName();
    return switch (operation) {
      case "count" -> "select count(*) as count from " + physicalTable + where;
      case "group_count" -> {
        CatalogColumn groupBy = requiredColumn(table, plan.get("group_by"), "group_by");
        if (!groupBy.allowedOperations().contains("group")) throw new IllegalArgumentException("group_by column is not allowlisted");
        yield "select " + groupBy.physicalName() + " as value, count(*) as count from " + physicalTable + where
          + " group by " + groupBy.physicalName() + " order by count desc limit " + limit;
      }
      case "sum", "avg", "min", "max" -> {
        CatalogColumn column = requiredColumn(table, plan.get("column"), "column");
        if (!column.allowedOperations().contains(operation)) throw new IllegalArgumentException("aggregate column is not allowlisted");
        yield "select " + operation + "(" + column.physicalName() + ") as " + operation + " from " + physicalTable + where;
      }
      case "list" -> {
        List<CatalogColumn> columns = selectedColumns(table, plan.get("columns"));
        String order = "";
        if (plan.get("order_by") instanceof Map<?, ?> orderBy) {
          CatalogColumn column = requiredColumn(table, orderBy.get("column"), "order_by.column");
          if (!column.allowedOperations().contains("sort")) throw new IllegalArgumentException("sort column is not allowlisted");
          String direction = "desc".equalsIgnoreCase(String.valueOf(orderBy.get("direction"))) ? "desc" : "asc";
          order = " order by " + column.physicalName() + " " + direction;
        }
        yield "select " + String.join(", ", columns.stream().map(c -> c.physicalName() + " as " + c.logicalName()).toList())
          + " from " + physicalTable + where + order + " limit " + limit;
      }
      default -> throw new IllegalArgumentException("unsupported operation");
    };
  }

  private Map<String, Object> readResult(String operation, Map<?, ?> plan, CatalogTable table, ResultSet rs) throws Exception {
    return switch (operation) {
      case "count" -> {
        rs.next();
        yield Map.of("operation", operation, "table", table.logicalName(), "count", rs.getLong(1));
      }
      case "sum", "avg", "min", "max" -> {
        rs.next();
        yield Map.of("operation", operation, "table", table.logicalName(), operation, rs.getObject(1) == null ? 0 : rs.getObject(1), "column", String.valueOf(plan.get("column")));
      }
      case "group_count" -> {
        List<Map<String, Object>> rows = new ArrayList<>();
        while (rs.next()) rows.add(Map.of("value", String.valueOf(rs.getObject("value")), "count", rs.getLong("count")));
        yield Map.of("operation", operation, "table", table.logicalName(), "group_by", String.valueOf(plan.get("group_by")), "rows", rows);
      }
      case "list" -> {
        List<Map<String, Object>> rows = new ArrayList<>();
        while (rs.next()) {
          Map<String, Object> row = new LinkedHashMap<>();
          for (CatalogColumn column : selectedColumns(table, plan.get("columns"))) row.put(column.logicalName(), rs.getObject(column.logicalName()));
          rows.add(row);
        }
        yield Map.of("operation", operation, "table", table.logicalName(), "rows", rows);
      }
      default -> throw new IllegalArgumentException("unsupported operation");
    };
  }

  private void validateActualSchema(Connection connection, CatalogTable table, Map<?, ?> plan, List<?> filters) throws Exception {
    try (ResultSet tables = connection.getMetaData().getTables(connection.getCatalog(), null, table.physicalName(), new String[]{"TABLE"})) {
      if (!tables.next()) throw new IllegalArgumentException("client database table missing: " + table.physicalName());
    }
    for (Object item : filters) {
      Map<?, ?> filter = requireMap(item, "filter");
      validateColumnExists(connection, table, requiredColumn(table, filter.get("column"), "filter.column"));
    }
    if (plan.get("column") != null) validateColumnExists(connection, table, requiredColumn(table, plan.get("column"), "column"));
    if (plan.get("group_by") != null) validateColumnExists(connection, table, requiredColumn(table, plan.get("group_by"), "group_by"));
    if (plan.get("order_by") instanceof Map<?, ?> orderBy) validateColumnExists(connection, table, requiredColumn(table, orderBy.get("column"), "order_by.column"));
    for (CatalogColumn column : selectedColumns(table, plan.get("columns"))) validateColumnExists(connection, table, column);
  }

  private void validateColumnExists(Connection connection, CatalogTable table, CatalogColumn column) throws Exception {
    try (ResultSet columns = connection.getMetaData().getColumns(connection.getCatalog(), null, table.physicalName(), column.physicalName())) {
      if (!columns.next()) throw new IllegalArgumentException("client database column missing: " + table.logicalName() + "." + column.logicalName() + " mapped to " + table.physicalName() + "." + column.physicalName());
    }
  }

  private String buildWhere(List<?> filters, CatalogTable table, List<Object> params) {
    if (filters.isEmpty()) return "";
    List<String> clauses = new ArrayList<>();
    for (Object item : filters) {
      Map<?, ?> filter = requireMap(item, "filter");
      CatalogColumn column = requiredColumn(table, filter.get("column"), "filter.column");
      if (!column.allowedOperations().contains("filter")) throw new IllegalArgumentException("filter column is not allowlisted");
      String operator = string(filter.get("operator"));
      Object value = filter.get("value");
      switch (operator) {
        case "eq" -> {
          clauses.add(column.physicalName() + " = ?");
          params.add(value);
        }
        case "ne" -> {
          clauses.add(column.physicalName() + " <> ?");
          params.add(value);
        }
        case "gt", "gte", "lt", "lte" -> {
          if (!column.fieldType().equals("number") && !column.fieldType().equals("date")) throw new IllegalArgumentException("range filter is not allowed for this column");
          clauses.add(column.physicalName() + " " + rangeOperator(operator) + " ?");
          params.add(value);
        }
        case "contains" -> {
          if (!column.fieldType().equals("string")) throw new IllegalArgumentException("contains filter is not allowed for this column");
          clauses.add(column.physicalName() + " like ?");
          params.add("%" + value + "%");
        }
        default -> throw new IllegalArgumentException("filter operator is not allowlisted");
      }
    }
    return " where " + String.join(" and ", clauses);
  }

  private String rangeOperator(String operator) {
    return switch (operator) {
      case "gt" -> ">";
      case "gte" -> ">=";
      case "lt" -> "<";
      case "lte" -> "<=";
      default -> throw new IllegalArgumentException("filter operator is not allowlisted");
    };
  }

  private CatalogColumn requiredColumn(CatalogTable table, Object value, String name) {
    String columnName = identifier(value);
    CatalogColumn column = table.column(columnName);
    if (column == null || column.sensitive() || !column.enabled()) throw new IllegalArgumentException(name + " is not allowlisted");
    return column;
  }

  private List<CatalogColumn> selectedColumns(CatalogTable table, Object value) {
    if (!(value instanceof List<?> requested) || requested.isEmpty()) {
      return table.columns().stream()
        .filter(c -> c.enabled() && !c.sensitive())
        .filter(c -> List.of("name", "title", "status", "type", "created_at", "updated_at").contains(c.logicalName()))
        .limit(6)
        .toList();
    }
    List<CatalogColumn> out = new ArrayList<>();
    for (Object item : requested) out.add(requiredColumn(table, item, "columns"));
    if (out.size() > 12) throw new IllegalArgumentException("too many selected columns");
    return List.copyOf(out);
  }

  private int limit(Object value) {
    if (value == null) return DEFAULT_MAX_LIMIT;
    int limit = value instanceof Number n ? n.intValue() : Integer.parseInt(String.valueOf(value));
    if (limit < 1) throw new IllegalArgumentException("limit must be positive");
    return Math.min(limit, DEFAULT_MAX_LIMIT);
  }

  private static Map<?, ?> requireMap(Object value, String name) {
    if (value instanceof Map<?, ?> map) return map;
    throw new IllegalArgumentException(name + " must be an object");
  }

  private static String string(Object value) {
    if (value == null) throw new IllegalArgumentException("required string missing");
    return String.valueOf(value);
  }

  private static String identifier(Object value) {
    String id = string(value).toLowerCase(Locale.ROOT);
    if (!id.matches("[a-z_][a-z0-9_]*")) throw new IllegalArgumentException("invalid identifier");
    return id;
  }

  private record TableAllowlist(List<String> columns, List<String> operations) {}
}
