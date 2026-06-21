package com.construction.rag.gateway;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import javax.sql.DataSource;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@Component
class SafeDatabaseQueryService {
  private static final Map<String, TableAllowlist> GLOBAL_ALLOWLIST = Map.of(
    "projects", new TableAllowlist(List.of("id", "name", "status"), List.of("count"))
  );

  private final ClientDataSourceManager dataSources;

  SafeDatabaseQueryService(ClientDataSourceManager dataSources) {
    this.dataSources = dataSources;
  }

  Mono<Map<String, Object>> execute(RagClient client, Map<?, ?> toolCall) {
    return Mono.fromCallable(() -> executeBlocking(client, toolCall)).subscribeOn(Schedulers.boundedElastic());
  }

  private Map<String, Object> executeBlocking(RagClient client, Map<?, ?> toolCall) throws Exception {
    Map<?, ?> plan = requireMap(toolCall.get("plan"), "plan");
    String operation = string(plan.get("operation"));
    String table = identifier(plan.get("table"));
    TableAllowlist allowlist = GLOBAL_ALLOWLIST.get(table);
    if (allowlist == null) throw new IllegalArgumentException("table is not allowlisted");
    if (!allowlist.operations().contains(operation)) throw new IllegalArgumentException("operation is not allowlisted");
    if (!"count".equals(operation)) throw new IllegalArgumentException("unsupported operation");

    List<?> filters = plan.get("filters") instanceof List<?> list ? list : List.of();
    List<Object> params = new ArrayList<>();
    String where = buildWhere(filters, allowlist, params);
    String sql = "select count(*) as count from " + table + where;
    DataSource dataSource = dataSources.dataSource(client);
    try (Connection connection = dataSource.getConnection()) {
      connection.setReadOnly(true);
      validateActualSchema(connection, table, filters);
      try (PreparedStatement statement = connection.prepareStatement(sql)) {
        statement.setQueryTimeout(10);
        for (int i = 0; i < params.size(); i++) statement.setObject(i + 1, params.get(i));
        try (ResultSet rs = statement.executeQuery()) {
          rs.next();
          return Map.of("count", rs.getLong(1));
        }
      }
    }
  }

  private void validateActualSchema(Connection connection, String table, List<?> filters) throws Exception {
    try (ResultSet tables = connection.getMetaData().getTables(connection.getCatalog(), null, table, new String[]{"TABLE"})) {
      if (!tables.next()) throw new IllegalArgumentException("client database table missing: " + table);
    }
    for (Object item : filters) {
      Map<?, ?> filter = requireMap(item, "filter");
      String column = identifier(filter.get("column"));
      try (ResultSet columns = connection.getMetaData().getColumns(connection.getCatalog(), null, table, column)) {
        if (!columns.next()) throw new IllegalArgumentException("client database column missing: " + table + "." + column);
      }
    }
  }

  private String buildWhere(List<?> filters, TableAllowlist allowlist, List<Object> params) {
    if (filters.isEmpty()) return "";
    List<String> clauses = new ArrayList<>();
    for (Object item : filters) {
      Map<?, ?> filter = requireMap(item, "filter");
      String column = identifier(filter.get("column"));
      if (!allowlist.columns().contains(column)) throw new IllegalArgumentException("filter column is not allowlisted");
      String operator = string(filter.get("operator"));
      if (!"eq".equals(operator)) throw new IllegalArgumentException("filter operator is not allowlisted");
      clauses.add(column + " = ?");
      params.add(filter.get("value"));
    }
    return " where " + String.join(" and ", clauses);
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
