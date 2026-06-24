package com.construction.rag.gateway;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.Date;
import java.sql.Timestamp;
import java.time.LocalDate;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import javax.sql.DataSource;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@Component
class SafeDatabaseQueryService {
  private static final Logger log = LoggerFactory.getLogger(SafeDatabaseQueryService.class);
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
    String requestedTable = string(plan.get("table"));
    String table = identifier(requestedTable);
    CatalogTable catalogTable = catalog.table(table);
    if (catalogTable == null) throw new IllegalArgumentException(tableValidationError(requestedTable, table, catalog));
    if (!catalogTable.allowedOperations().contains(operation)) throw new IllegalArgumentException("operation is not allowlisted");

    if ("details".equals(operation)) {
      return executeDetails(client, catalogTable, plan);
    }

    List<?> filters = plan.get("filters") instanceof List<?> list ? list : List.of();
    QueryContext context = queryContext(catalog, catalogTable, plan.get("joins"));
    List<Object> params = new ArrayList<>();
    String where = buildWhere(filters, context, params);
    int limit = limit(plan.get("limit"));
    String sql = buildSql(operation, plan, context, where, limit);
    log.info("safe_database_query operation={} db_name={} selected_table={} physical_table={} joins={} filters={} limit={} sql_template={} bound_params={} reason=validated_catalog_plan",
      operation, client.dbName(), table, catalogTable.physicalName(), context.joins().size(), filters.size(), limit, sql, safeParams(params));
    DataSource dataSource = dataSources.dataSource(client);
    try (Connection connection = dataSource.getConnection()) {
      connection.setReadOnly(true);
      validateActualSchema(connection, context, plan, filters);
      try (PreparedStatement statement = connection.prepareStatement(sql)) {
        statement.setQueryTimeout(10);
        for (int i = 0; i < params.size(); i++) statement.setObject(i + 1, params.get(i));
        try (ResultSet rs = statement.executeQuery()) {
          Map<String, Object> result = readResult(operation, plan, context, rs);
          log.info("safe_database_query_result operation={} db_name={} selected_table={} physical_table={} row_count={} reason=validated_catalog_plan",
            operation, client.dbName(), table, catalogTable.physicalName(), resultRowCount(result));
          return result;
        }
      }
    }
  }

  private QueryContext queryContext(SemanticCatalog catalog, CatalogTable baseTable, Object joinsValue) {
    List<?> requestedJoins = joinsValue instanceof List<?> list ? list : List.of();
    if (requestedJoins.size() > 6) throw new IllegalArgumentException("too many joins");
    List<QueryTable> tables = new ArrayList<>();
    QueryTable base = new QueryTable(baseTable, requestedJoins.isEmpty() ? "" : "t0");
    tables.add(base);
    List<QueryJoin> joins = new ArrayList<>();
    for (Object item : requestedJoins) {
        Map<?, ?> joinMap = requireMap(item, "join");
        CatalogTable rightTable = catalog.table(identifier(joinMap.get("table")));
        if (rightTable == null) throw new IllegalArgumentException("join table is not allowlisted");
        QueryTable right = new QueryTable(rightTable, "t" + tables.size());
        CatalogColumn leftColumn = columnRef(tables, joinMap.get("left_column"), "join.left_column").column();
        CatalogColumn rightColumn = requiredColumn(rightTable, unqualifiedIdentifier(joinMap.get("right_column")), "join.right_column");
        String rightRef = string(joinMap.get("right_column"));
        if (rightRef.contains(".") && !rightRef.split("\\.", 2)[0].equals(rightTable.logicalName())) throw new IllegalArgumentException("join.right_column must belong to joined table");
        String type = "left".equalsIgnoreCase(String.valueOf(joinMap.get("type"))) ? "left" : "inner";
        joins.add(new QueryJoin(right, leftColumn, rightColumn, type));
        tables.add(right);
    }
    return new QueryContext(base, List.copyOf(tables), List.copyOf(joins));
  }

  private String buildSql(String operation, Map<?, ?> plan, QueryContext context, String where, int limit) {
    String from = fromClause(context);
    return switch (operation) {
      case "count" -> "select count(*) as count " + from + where;
      case "group_count" -> {
        QueryColumn groupBy = requiredPlanColumn(context, plan.get("group_by"), "group_by");
        if (!groupBy.column().allowedOperations().contains("group")) throw new IllegalArgumentException("group_by column is not allowlisted");
        yield "select " + columnSql(groupBy) + " as value, count(*) as count " + from + where
          + " group by " + columnSql(groupBy) + " order by count desc limit " + limit;
      }
      case "sum", "avg", "min", "max" -> {
        QueryColumn column = requiredPlanColumn(context, plan.get("column"), "column");
        if (!column.column().allowedOperations().contains(operation)) throw new IllegalArgumentException("aggregate column is not allowlisted");
        yield "select " + operation + "(" + columnSql(column) + ") as " + operation + " " + from + where;
      }
      case "list", "select" -> {
        List<QueryColumn> columns = selectedPlanColumns(context, plan.get("columns"));
        String order = "";
        if (plan.get("order_by") instanceof Map<?, ?> orderBy) {
          QueryColumn column = requiredPlanColumn(context, orderBy.get("column"), "order_by.column");
          if (!column.column().allowedOperations().contains("sort")) throw new IllegalArgumentException("sort column is not allowlisted");
          String direction = "desc".equalsIgnoreCase(String.valueOf(orderBy.get("direction"))) ? "desc" : "asc";
          order = " order by " + columnSql(column) + " " + direction;
        }
        yield "select " + String.join(", ", columns.stream().map(c -> columnSql(c) + " as " + c.outputName()).toList())
          + " " + from + where + order + " limit " + limit;
      }
      case "details" -> throw new IllegalArgumentException("details operation requires lookup fields");
      default -> throw new IllegalArgumentException("unsupported operation");
    };
  }

  private String fromClause(QueryContext context) {
    if (context.joins().isEmpty()) return "from " + context.base().table().physicalName();
    StringBuilder sql = new StringBuilder("from " + context.base().table().physicalName() + " " + context.base().alias());
    for (QueryJoin join : context.joins()) {
      String joinType = "left".equals(join.type()) ? " left join " : " inner join ";
      QueryTable right = join.table();
      QueryTable leftTable = tableForColumn(context, join.leftColumn());
      sql.append(joinType)
        .append(right.table().physicalName()).append(" ").append(right.alias())
        .append(" on ").append(leftTable.alias()).append(".").append(join.leftColumn().physicalName())
        .append(" = ").append(right.alias()).append(".").append(join.rightColumn().physicalName());
    }
    return sql.toString();
  }

  private QueryTable tableForColumn(QueryContext context, CatalogColumn column) {
    for (QueryTable table : context.tables()) if (table.table().columns().contains(column)) return table;
    throw new IllegalArgumentException("join column table is not allowlisted");
  }

  private String columnSql(QueryColumn column) {
    return column.table().alias().isBlank() ? column.column().physicalName() : column.table().alias() + "." + column.column().physicalName();
  }

  private QueryColumn requiredPlanColumn(QueryContext context, Object value, String name) {
    return columnRef(context.tables(), value, name);
  }

  private QueryColumn columnRef(List<QueryTable> tables, Object value, String name) {
    String ref = string(value).toLowerCase(Locale.ROOT);
    if (ref.contains(".")) {
      String[] parts = ref.split("\\.", 2);
      String tableName = identifier(parts[0]);
      String columnName = identifier(parts[1]);
      for (QueryTable table : tables) {
        if (!table.table().logicalName().equals(tableName)) continue;
        CatalogColumn column = table.table().column(columnName);
        if (column == null || column.sensitive() || !column.enabled()) throw new IllegalArgumentException(name + " is not allowlisted");
        return new QueryColumn(table, column, outputName(table, column, tables.size() > 1));
      }
      throw new IllegalArgumentException(name + " table is not allowlisted");
    }
    String columnName = identifier(ref);
    QueryColumn found = null;
    for (QueryTable table : tables) {
      CatalogColumn column = table.table().column(columnName);
      if (column == null || column.sensitive() || !column.enabled()) continue;
      if (found != null) throw new IllegalArgumentException(name + " is ambiguous; qualify it with table.column");
      found = new QueryColumn(table, column, outputName(table, column, tables.size() > 1));
    }
    if (found == null) throw new IllegalArgumentException(name + " is not allowlisted");
    return found;
  }

  private String unqualifiedIdentifier(Object value) {
    String ref = string(value).toLowerCase(Locale.ROOT);
    return identifier(ref.contains(".") ? ref.split("\\.", 2)[1] : ref);
  }

  private String outputName(QueryTable table, CatalogColumn column, boolean joined) {
    return joined ? table.table().logicalName() + "__" + column.logicalName() : column.logicalName();
  }

  private List<QueryColumn> selectedPlanColumns(QueryContext context, Object value) {
    if (!(value instanceof List<?> requested) || requested.isEmpty()) {
      return context.base().table().columns().stream()
        .filter(c -> c.enabled() && !c.sensitive())
        .filter(c -> List.of("name", "title", "status", "type", "planned_delivery_date", "actual_delivery_date", "is_finished", "created_at", "updated_at").contains(c.logicalName()))
        .limit(6)
        .map(c -> new QueryColumn(context.base(), c, outputName(context.base(), c, context.tables().size() > 1)))
        .toList();
    }
    List<QueryColumn> out = new ArrayList<>();
    for (Object item : requested) out.add(requiredPlanColumn(context, item, "columns"));
    if (out.size() > 12) throw new IllegalArgumentException("too many selected columns");
    return List.copyOf(out);
  }

  private Map<String, Object> readResult(String operation, Map<?, ?> plan, QueryContext context, ResultSet rs) throws Exception {
    CatalogTable table = context.base().table();
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
      case "list", "select", "details" -> {
        List<QueryColumn> columns = selectedPlanColumns(context, plan.get("columns"));
        List<Map<String, Object>> rows = new ArrayList<>();
        while (rs.next()) {
          Map<String, Object> row = new LinkedHashMap<>();
          for (QueryColumn column : columns) row.put(column.outputName(), rs.getObject(column.outputName()));
          addDelayDays(row);
          rows.add(row);
        }
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("operation", operation);
        Object intent = plan.get("intent");
        result.put("intent", intent == null ? "" : String.valueOf(intent));
        result.put("table", table.logicalName());
        result.put("joins", context.joins().stream().map(j -> j.table().table().logicalName()).toList());
        result.put("rows", rows);
        yield result;
      }
      default -> throw new IllegalArgumentException("unsupported operation");
    };
  }

  private Map<String, Object> executeDetails(RagClient client, CatalogTable table, Map<?, ?> plan) throws Exception {
    CodeLookup codeLookup = codeLookup(table, plan.get("filters"));
    if (codeLookup != null) {
      return executeCodeDetails(client, table, plan, codeLookup);
    }
    String lookupValue = string(plan.get("lookup_value")).trim();
    if (lookupValue.isBlank()) throw new IllegalArgumentException("lookup_value is required for details");
    List<CatalogColumn> lookupColumns = lookupColumns(table, plan.get("lookup_fields"));
    List<CatalogColumn> columns = selectedColumns(table, plan.get("columns"));
    int limit = Math.min(limit(plan.get("limit")), 1);
    String select = String.join(", ", columns.stream().map(c -> c.physicalName() + " as " + c.logicalName()).toList());
    String exactWhere = String.join(" or ", lookupColumns.stream().map(c -> c.physicalName() + " = ?").toList());
    String fuzzyWhere = String.join(" or ", lookupColumns.stream().map(c -> c.physicalName() + " like ?").toList());
    String order = table.column("updated_at") == null ? "" : " order by " + table.column("updated_at").physicalName() + " desc";
    DataSource dataSource = dataSources.dataSource(client);
    try (Connection connection = dataSource.getConnection()) {
      connection.setReadOnly(true);
      validateActualSchema(connection, table, plan, List.of());
      for (CatalogColumn column : lookupColumns) validateColumnExists(connection, table, column);
      String exactSql = "select " + select + " from " + table.physicalName() + " where " + exactWhere + " limit " + limit;
      log.info("safe_database_query operation=details db_name={} selected_table={} physical_table={} filters=lookup_exact limit={} sql_template={} bound_params_count={} reason=validated_catalog_plan",
        client.dbName(), table.logicalName(), table.physicalName(), limit, exactSql, lookupColumns.size());
      List<Map<String, Object>> rows = queryRows(connection, exactSql, lookupColumns.stream().map(c -> (Object) lookupValue).toList(), columns);
      if (rows.isEmpty()) {
        String fuzzySql = "select " + select + " from " + table.physicalName() + " where " + fuzzyWhere + order + " limit " + limit;
        log.info("safe_database_query operation=details db_name={} selected_table={} physical_table={} filters=lookup_fuzzy limit={} sql_template={} bound_params_count={} reason=validated_catalog_plan",
          client.dbName(), table.logicalName(), table.physicalName(), limit, fuzzySql, lookupColumns.size());
        rows = queryRows(connection, fuzzySql, lookupColumns.stream().map(c -> (Object) ("%" + lookupValue + "%")).toList(), columns);
      }
      log.info("safe_database_query_result operation=details db_name={} selected_table={} physical_table={} row_count={} reason=validated_catalog_plan",
        client.dbName(), table.logicalName(), table.physicalName(), rows.size());
      Map<String, Object> result = new LinkedHashMap<>();
      result.put("operation", "details");
      Object intent = plan.get("intent");
      result.put("intent", intent == null ? "project_details" : String.valueOf(intent));
      result.put("table", table.logicalName());
      result.put("lookup_value", lookupValue);
      result.put("rows", rows);
      return result;
    }
  }

  private Map<String, Object> executeCodeDetails(RagClient client, CatalogTable table, Map<?, ?> plan, CodeLookup lookup) throws Exception {
    List<CatalogColumn> columns = selectedColumns(table, plan.get("columns"));
    int limit = Math.min(limit(plan.get("limit")), 1);
    String select = String.join(", ", columns.stream().map(c -> c.physicalName() + " as " + c.logicalName()).toList());
    String physical = lookup.column().physicalName();
    String normalizedColumn = "replace(replace(replace(lower(" + physical + "), ' ', ''), '–', '-'), '—', '-')";
    String sql = "select " + select + " from " + table.physicalName()
      + " where " + physical + " = ? or lower(trim(" + physical + ")) = lower(?) or " + normalizedColumn + " = ? limit " + limit;
    DataSource dataSource = dataSources.dataSource(client);
    try (Connection connection = dataSource.getConnection()) {
      connection.setReadOnly(true);
      validateActualSchema(connection, table, plan, List.of(Map.of("column", lookup.column().logicalName(), "operator", "code_equals_normalized", "value", lookup.normalized())));
      log.info("safe_database_query operation=details db_name={} selected_table={} physical_table={} code_field={} filters=code_equals_normalized limit={} sql_template={} bound_params_count=3 reason=validated_catalog_plan",
        client.dbName(), table.logicalName(), table.physicalName(), lookup.column().logicalName(), limit, sql);
      List<Map<String, Object>> rows = queryRows(connection, sql, List.of(lookup.raw(), lookup.normalized(), lookup.compact()), columns);
      log.info("safe_database_query_result operation=details db_name={} selected_table={} physical_table={} row_count={} reason=validated_catalog_plan",
        client.dbName(), table.logicalName(), table.physicalName(), rows.size());
      Map<String, Object> result = new LinkedHashMap<>();
      result.put("operation", "details");
      Object intent = plan.get("intent");
      result.put("intent", intent == null ? "project_details" : String.valueOf(intent));
      result.put("table", table.logicalName());
      result.put("lookup_value", lookup.normalized());
      result.put("lookup_type", "project_code");
      result.put("rows", rows);
      return result;
    }
  }

  private List<Map<String, Object>> queryRows(Connection connection, String sql, List<Object> params, List<CatalogColumn> columns) throws Exception {
    try (PreparedStatement statement = connection.prepareStatement(sql)) {
      statement.setQueryTimeout(10);
      for (int i = 0; i < params.size(); i++) statement.setObject(i + 1, params.get(i));
      try (ResultSet rs = statement.executeQuery()) {
        List<Map<String, Object>> rows = new ArrayList<>();
        while (rs.next()) {
          Map<String, Object> row = new LinkedHashMap<>();
          for (CatalogColumn column : columns) row.put(column.logicalName(), rs.getObject(column.logicalName()));
          addDelayDays(row);
          rows.add(row);
        }
        return rows;
      }
    }
  }

  private void validateActualSchema(Connection connection, CatalogTable table, Map<?, ?> plan, List<?> filters) throws Exception {
    QueryTable base = new QueryTable(table, "t0");
    validateActualSchema(connection, new QueryContext(base, List.of(base), List.of()), plan, filters);
  }

  private void validateActualSchema(Connection connection, QueryContext context, Map<?, ?> plan, List<?> filters) throws Exception {
    for (QueryTable table : context.tables()) {
      try (ResultSet tables = connection.getMetaData().getTables(connection.getCatalog(), null, table.table().physicalName(), new String[]{"TABLE"})) {
        if (!tables.next()) throw new IllegalArgumentException("client database table missing: " + table.table().physicalName());
      }
    }
    for (Object item : filters) {
      Map<?, ?> filter = requireMap(item, "filter");
      validateColumnExists(connection, requiredPlanColumn(context, filter.get("column"), "filter.column"));
    }
    if (plan.get("column") != null) validateColumnExists(connection, requiredPlanColumn(context, plan.get("column"), "column"));
    if (plan.get("group_by") != null) validateColumnExists(connection, requiredPlanColumn(context, plan.get("group_by"), "group_by"));
    if (plan.get("order_by") instanceof Map<?, ?> orderBy) validateColumnExists(connection, requiredPlanColumn(context, orderBy.get("column"), "order_by.column"));
    for (QueryJoin join : context.joins()) {
      validateColumnExists(connection, tableForColumn(context, join.leftColumn()), join.leftColumn());
      validateColumnExists(connection, join.table(), join.rightColumn());
    }
    for (QueryColumn column : selectedPlanColumns(context, plan.get("columns"))) validateColumnExists(connection, column);
  }

  private void validateColumnExists(Connection connection, QueryColumn column) throws Exception {
    validateColumnExists(connection, column.table(), column.column());
  }

  private void validateColumnExists(Connection connection, QueryTable table, CatalogColumn column) throws Exception {
    validateColumnExists(connection, table.table(), column);
  }

  private void validateColumnExists(Connection connection, CatalogTable table, CatalogColumn column) throws Exception {
    try (ResultSet columns = connection.getMetaData().getColumns(connection.getCatalog(), null, table.physicalName(), column.physicalName())) {
      if (!columns.next()) throw new IllegalArgumentException("client database column missing: " + table.logicalName() + "." + column.logicalName() + " mapped to " + table.physicalName() + "." + column.physicalName());
    }
  }

  private String buildWhere(List<?> filters, QueryContext context, List<Object> params) {
    if (filters.isEmpty()) return "";
    List<String> clauses = new ArrayList<>();
    for (Object item : filters) {
      Map<?, ?> filter = requireMap(item, "filter");
      QueryColumn queryColumn = requiredPlanColumn(context, filter.get("column"), "filter.column");
      CatalogColumn column = queryColumn.column();
      if (!column.allowedOperations().contains("filter")) throw new IllegalArgumentException("filter column is not allowlisted");
      String operator = string(filter.get("operator"));
      Object value = filter.get("value");
      String sqlColumn = columnSql(queryColumn);
      switch (operator) {
        case "eq" -> {
          validateValueType(column, value);
          clauses.add(sqlColumn + " = ?");
          params.add(parameterValue(column, value));
        }
        case "ne" -> {
          validateValueType(column, value);
          clauses.add(sqlColumn + " <> ?");
          params.add(parameterValue(column, value));
        }
        case "gt", "gte", "lt", "lte" -> {
          if (!column.fieldType().equals("number") && !column.fieldType().equals("date")) throw new IllegalArgumentException("range filter is not allowed for this column");
          validateValueType(column, value);
          clauses.add(sqlColumn + " " + rangeOperator(operator) + " ?");
          params.add(parameterValue(column, value));
        }
        case "contains" -> {
          if (!column.fieldType().equals("string")) throw new IllegalArgumentException("contains filter is not allowed for this column");
          clauses.add(sqlColumn + " like ?");
          params.add("%" + value + "%");
        }
        case "is_null" -> clauses.add(sqlColumn + " is null");
        case "not_completed" -> {
          if (!"is_finished".equals(column.logicalName()) && !"status".equals(column.logicalName())) throw new IllegalArgumentException("not_completed filter is not allowed for this column");
          clauses.add(sqlColumn + " = ?");
          params.add(0);
        }
        case "code_equals_normalized" -> throw new IllegalArgumentException("code filter is only allowed for details lookup");
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

  private void validateValueType(CatalogColumn column, Object value) {
    if ("date".equals(column.fieldType()) && "today".equalsIgnoreCase(String.valueOf(value))) return;
    if ("number".equals(column.fieldType()) && !(value instanceof Number)) {
      try {
        Double.parseDouble(String.valueOf(value));
      } catch (Exception ex) {
        throw new IllegalArgumentException("filter value is not compatible with numeric column: " + column.logicalName());
      }
    }
  }

  private Object parameterValue(CatalogColumn column, Object value) {
    if ("date".equals(column.fieldType()) && "today".equalsIgnoreCase(String.valueOf(value))) return LocalDate.now();
    return value;
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
        .filter(c -> List.of("name", "title", "status", "type", "planned_delivery_date", "actual_delivery_date", "is_finished", "created_at", "updated_at").contains(c.logicalName()))
        .limit(6)
        .toList();
    }
    List<CatalogColumn> out = new ArrayList<>();
    for (Object item : requested) out.add(requiredColumn(table, item, "columns"));
    if (out.size() > 12) throw new IllegalArgumentException("too many selected columns");
    return List.copyOf(out);
  }

  private List<CatalogColumn> lookupColumns(CatalogTable table, Object value) {
    if (!(value instanceof List<?> requested) || requested.isEmpty()) throw new IllegalArgumentException("lookup_fields are required");
    List<CatalogColumn> out = new ArrayList<>();
    for (Object item : requested) {
      CatalogColumn column = requiredColumn(table, item, "lookup_fields");
      if (!column.fieldType().equals("string") || !column.allowedOperations().contains("filter")) throw new IllegalArgumentException("lookup field is not allowlisted");
      out.add(column);
    }
    if (out.size() > 5) throw new IllegalArgumentException("too many lookup fields");
    return List.copyOf(out);
  }

  private CodeLookup codeLookup(CatalogTable table, Object filtersValue) {
    if (!(filtersValue instanceof List<?> filters)) return null;
    for (Object item : filters) {
      Map<?, ?> filter = requireMap(item, "filter");
      if (!"code_equals_normalized".equals(string(filter.get("operator")))) continue;
      CatalogColumn column = requiredColumn(table, filter.get("column"), "filter.column");
      if (!column.fieldType().equals("string") || !column.allowedOperations().contains("filter")) throw new IllegalArgumentException("project code field is not allowlisted");
      Object rawValue = filter.get("value");
      String raw;
      String normalized;
      String compact;
      if (rawValue instanceof Map<?, ?> valueMap) {
        Object rawObject = valueMap.containsKey("raw") ? valueMap.get("raw") : valueMap.get("normalized");
        raw = string(rawObject);
        Object normalizedObject = valueMap.containsKey("normalized") ? valueMap.get("normalized") : raw;
        normalized = normalizeProjectCode(string(normalizedObject));
        Object compactObject = valueMap.containsKey("compact") ? valueMap.get("compact") : normalized;
        compact = normalizeProjectCode(string(compactObject));
      } else {
        raw = string(rawValue);
        normalized = normalizeProjectCode(raw);
        compact = normalized.replace(" ", "");
      }
      return new CodeLookup(column, raw, normalized, compact);
    }
    return null;
  }

  private String normalizeProjectCode(String value) {
    String normalized = value == null ? "" : value.trim().toLowerCase(Locale.ROOT);
    normalized = normalized.replace('–', '-').replace('—', '-');
    normalized = normalized.replaceAll("\\s*-\\s*", "-").replaceAll("\\s+", " ");
    if (normalized.isBlank()) throw new IllegalArgumentException("project code value is required");
    return normalized;
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

  private String tableValidationError(String requestedTable, String normalizedTable, SemanticCatalog catalog) {
    List<String> allowed = catalog.tables().stream()
      .filter(CatalogTable::enabled)
      .map(CatalogTable::logicalName)
      .sorted()
      .toList();
    return "table is not allowlisted: requested_table=" + requestedTable
      + ", normalized_table=" + normalizedTable
      + ", allowed_tables=" + allowed;
  }

  private List<Object> safeParams(List<Object> params) {
    return params.stream().map(this::safeParam).toList();
  }

  private Object safeParam(Object value) {
    if (value == null) return null;
    String text = String.valueOf(value);
    String lower = text.toLowerCase(Locale.ROOT);
    if (lower.contains("password") || lower.contains("token") || lower.contains("secret") || lower.contains("key")) return "[REDACTED]";
    return text.length() > 80 ? text.substring(0, 80) + "..." : value;
  }

  private int resultRowCount(Map<String, Object> result) {
    Object rows = result.get("rows");
    if (rows instanceof List<?> list) return list.size();
    return result.containsKey("count") ? 1 : 0;
  }

  private void addDelayDays(Map<String, Object> row) {
    Object value = row.get("planned_delivery_date");
    LocalDate planned = toLocalDate(value);
    if (planned == null) return;
    long days = ChronoUnit.DAYS.between(planned, LocalDate.now());
    if (days > 0) row.put("days_delay", days);
  }

  private LocalDate toLocalDate(Object value) {
    if (value instanceof LocalDate d) return d;
    if (value instanceof Date d) return d.toLocalDate();
    if (value instanceof Timestamp t) return t.toLocalDateTime().toLocalDate();
    if (value instanceof java.util.Date d) return new java.sql.Date(d.getTime()).toLocalDate();
    try {
      return value == null ? null : LocalDate.parse(String.valueOf(value));
    } catch (Exception ignored) {
      return null;
    }
  }

  private record TableAllowlist(List<String> columns, List<String> operations) {}
  private record CodeLookup(CatalogColumn column, String raw, String normalized, String compact) {}
  private record QueryTable(CatalogTable table, String alias) {}
  private record QueryColumn(QueryTable table, CatalogColumn column, String outputName) {}
  private record QueryJoin(QueryTable table, CatalogColumn leftColumn, CatalogColumn rightColumn, String type) {}
  private record QueryContext(QueryTable base, List<QueryTable> tables, List<QueryJoin> joins) {}
}
