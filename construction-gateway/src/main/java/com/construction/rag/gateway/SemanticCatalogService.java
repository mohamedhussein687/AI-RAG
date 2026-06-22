package com.construction.rag.gateway;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.security.MessageDigest;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.Statement;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import javax.sql.DataSource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

@Component
class SemanticCatalogService {
  private static final int MAX_TABLES_INDEX_IN_PROMPT = 80;
  private static final int MAX_DETAILED_TABLES_IN_PROMPT = 10;
  private static final int MAX_COLUMNS_IN_PROMPT = 12;
  private static final int CATALOG_VERSION = 3;
  private static final Set<String> CMS_TABLE_NAMES = Set.of(
    "about_us", "pages", "settings", "banners", "sliders", "menus", "menu_items", "cms_pages", "cms_blocks"
  );
  private static final Set<String> SENSITIVE_TOKENS = Set.of(
    "password", "passwd", "remember_token", "api_token", "token", "secret", "private_key",
    "reset_token", "key", "credential", "authorization"
  );

  private final JdbcTemplate jdbc;
  private final ClientDataSourceManager dataSources;
  private final ObjectMapper mapper;
  private final Map<Long, SemanticCatalog> cache = new HashMap<>();

  SemanticCatalogService(JdbcTemplate jdbc, ClientDataSourceManager dataSources, ObjectMapper mapper) {
    this.jdbc = jdbc;
    this.dataSources = dataSources;
    this.mapper = mapper;
    ensureTable();
  }

  synchronized SemanticCatalog catalog(RagClient client) {
    SemanticCatalog cached = cache.get(client.id());
    String schemaHash = currentSchemaHash(client);
    if (cached != null && cached.schemaHash().equals(schemaHash)) return cached;
    SemanticCatalog stored = load(client, schemaHash);
    if (stored != null) {
      cache.put(client.id(), stored);
      return stored;
    }
    SemanticCatalog generated = discover(client, schemaHash);
    persist(client, generated);
    cache.put(client.id(), generated);
    return generated;
  }

  Map<String, Object> promptSummary(SemanticCatalog catalog) {
    List<CatalogTable> candidates = catalog.tables().stream()
      .filter(CatalogTable::enabled)
      .sorted(Comparator.comparing(CatalogTable::logicalName))
      .limit(MAX_TABLES_INDEX_IN_PROMPT)
      .toList();
    List<Map<String, Object>> tableIndex = new ArrayList<>();
    List<Map<String, Object>> tables = new ArrayList<>();
    for (CatalogTable table : candidates) {
      if (!table.enabled()) continue;
      tableIndex.add(Map.of(
        "name", table.logicalName(),
        "allowed_operations", table.allowedOperations()
      ));
    }
    for (CatalogTable table : candidates.stream().limit(MAX_DETAILED_TABLES_IN_PROMPT).toList()) {
      List<Map<String, Object>> columns = new ArrayList<>();
      for (CatalogColumn column : table.columns()) {
        if (!column.enabled()) continue;
        columns.add(Map.of(
          "name", column.logicalName(),
          "type", column.fieldType(),
          "operations", column.allowedOperations(),
          "enum_values", column.enumValues()
        ));
        if (columns.size() >= MAX_COLUMNS_IN_PROMPT) break;
      }
      tables.add(Map.of(
        "name", table.logicalName(),
        "columns", columns,
        "allowed_operations", table.allowedOperations()
      ));
    }
    return Map.of(
      "catalog_version", catalog.version(),
      "schema_hash", catalog.schemaHash(),
      "domain_entities", domainEntities(catalog),
      "tables_index", tableIndex,
      "tables", tables
    );
  }

  Map<String, Object> allowedSchema(SemanticCatalog catalog) {
    List<Map<String, Object>> tables = new ArrayList<>();
    for (CatalogTable table : catalog.tables()) {
      if (!table.enabled()) continue;
      List<String> columns = table.columns().stream().filter(CatalogColumn::enabled).map(CatalogColumn::logicalName).distinct().toList();
      tables.add(Map.of("name", table.logicalName(), "columns", columns, "allowed_operations", table.allowedOperations()));
    }
    return Map.of("tables", tables);
  }

  private void ensureTable() {
    jdbc.execute("""
      create table if not exists rag_client_catalogs (
        id bigserial primary key,
        client_name varchar(120) not null unique,
        catalog_version integer not null,
        generated_at timestamptz not null,
        schema_hash varchar(128) not null,
        enabled boolean not null,
        catalog_json jsonb not null,
        created_at timestamptz not null default now(),
        updated_at timestamptz not null default now()
      )
      """);
  }

  private SemanticCatalog load(RagClient client, String schemaHash) {
    return jdbc.query("""
        select catalog_json::text from rag_client_catalogs
        where client_name = ? and schema_hash = ? and catalog_version = ? and enabled = true
        """,
      (rs, rowNum) -> fromJson(rs.getString(1)),
      client.clientName(), schemaHash, CATALOG_VERSION
    ).stream().findFirst().orElse(null);
  }

  private SemanticCatalog fromJson(String json) {
    try {
      Map<String, Object> root = mapper.readValue(json, new TypeReference<Map<String, Object>>() {});
      List<CatalogTable> tables = new ArrayList<>();
      List<?> tableValues = (List<?>) root.getOrDefault("tables", List.of());
      for (Object item : tableValues) {
        Map<?, ?> t = (Map<?, ?>) item;
        List<CatalogColumn> columns = new ArrayList<>();
        Object columnValues = t.get("columns");
        for (Object colItem : columnValues instanceof List<?> list ? list : List.of()) {
          Map<?, ?> c = (Map<?, ?>) colItem;
          columns.add(new CatalogColumn(
            string(c.get("logical_name")), string(c.get("physical_name")), string(c.get("field_type")),
            bool(c.get("nullable")), list(c.get("allowed_operations")), list(c.get("enum_values")),
            bool(c.get("sensitive")), bool(c.get("enabled"))
          ));
        }
        tables.add(new CatalogTable(
          string(t.get("logical_name")), string(t.get("physical_name")), string(t.get("entity_name")),
          list(t.get("arabic_synonyms")), list(t.get("english_synonyms")), columns,
          list(t.get("allowed_operations")), bool(t.get("enabled")), longValue(t.get("approx_rows"))
        ));
      }
      return new SemanticCatalog(string(root.get("client_name")), intValue(root.get("catalog_version")), string(root.get("generated_at")), string(root.get("schema_hash")), bool(root.get("enabled")), tables);
    } catch (Exception ex) {
      throw new IllegalStateException("stored semantic catalog is invalid", ex);
    }
  }

  private void persist(RagClient client, SemanticCatalog catalog) {
    try {
      String json = mapper.writeValueAsString(catalog.toMap());
      jdbc.update("""
        insert into rag_client_catalogs(client_name, catalog_version, generated_at, schema_hash, enabled, catalog_json)
        values (?, ?, now(), ?, true, ?::jsonb)
        on conflict (client_name) do update set
          catalog_version = excluded.catalog_version,
          generated_at = excluded.generated_at,
          schema_hash = excluded.schema_hash,
          enabled = excluded.enabled,
          catalog_json = excluded.catalog_json,
          updated_at = now()
        """, client.clientName(), catalog.version(), catalog.schemaHash(), json);
    } catch (Exception ex) {
      throw new IllegalStateException("failed to persist semantic catalog", ex);
    }
  }

  private String currentSchemaHash(RagClient client) {
    try {
      List<String> parts = new ArrayList<>();
      DataSource ds = dataSources.dataSource(client);
      try (Connection c = ds.getConnection();
           PreparedStatement ps = c.prepareStatement("""
             select table_name, column_name, data_type, is_nullable, ordinal_position
             from information_schema.columns
             where table_schema = database()
             order by table_name, ordinal_position
             """);
           ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
          parts.add(rs.getString(1) + "." + rs.getString(2) + ":" + rs.getString(3) + ":" + rs.getString(4));
        }
      }
      MessageDigest digest = MessageDigest.getInstance("SHA-256");
      byte[] hash = digest.digest(String.join("|", parts).getBytes(java.nio.charset.StandardCharsets.UTF_8));
      StringBuilder out = new StringBuilder();
      for (byte b : hash) out.append(String.format("%02x", b));
      return out.toString();
    } catch (Exception ex) {
      throw new IllegalStateException("failed to hash client schema", ex);
    }
  }

  private SemanticCatalog discover(RagClient client, String schemaHash) {
    List<CatalogTable> tables = new ArrayList<>();
    try {
      DataSource ds = dataSources.dataSource(client);
      try (Connection c = ds.getConnection()) {
        Map<String, List<ColumnSource>> columnsByTable = new LinkedHashMap<>();
        try (PreparedStatement ps = c.prepareStatement("""
             select table_name, column_name, data_type, is_nullable, column_key, ordinal_position
             from information_schema.columns
             where table_schema = database()
             order by table_name, ordinal_position
             """);
             ResultSet rs = ps.executeQuery()) {
          while (rs.next()) {
            columnsByTable.computeIfAbsent(rs.getString("table_name"), ignored -> new ArrayList<>()).add(new ColumnSource(
              rs.getString("column_name"), rs.getString("data_type"), "YES".equalsIgnoreCase(rs.getString("is_nullable")), rs.getString("column_key")
            ));
          }
        }
        for (Map.Entry<String, List<ColumnSource>> entry : columnsByTable.entrySet()) {
          String table = entry.getKey();
          if (!safeIdentifier(table)) continue;
          List<CatalogColumn> columns = new ArrayList<>();
          Set<String> usedLogical = new LinkedHashSet<>();
          for (ColumnSource source : entry.getValue()) {
            if (!safeIdentifier(source.name())) continue;
            boolean sensitive = sensitive(source.name());
            String logical = logicalColumn(table, source.name(), usedLogical);
            usedLogical.add(logical);
            columns.add(new CatalogColumn(logical, source.name(), fieldType(source.type()), source.nullable(), operations(source.type(), sensitive), enumValues(c, table, source), sensitive, !sensitive));
          }
          boolean enabled = !cmsContentTable(table) && columns.stream().anyMatch(CatalogColumn::enabled);
          tables.add(new CatalogTable(table, table, entityName(table), arabicSynonyms(table), englishSynonyms(table), columns, tableOperations(columns), enabled, approximateRows(c, table)));
        }
      }
    } catch (Exception ex) {
      throw new IllegalStateException("failed to discover client schema", ex);
    }
    tables.sort(Comparator.comparing(CatalogTable::logicalName));
    return new SemanticCatalog(client.clientName(), CATALOG_VERSION, Instant.now().toString(), schemaHash, true, tables);
  }

  private static boolean sensitive(String name) {
    String n = name.toLowerCase(Locale.ROOT);
    return SENSITIVE_TOKENS.stream().anyMatch(n::contains);
  }

  private static boolean cmsContentTable(String table) {
    String t = table.toLowerCase(Locale.ROOT);
    return CMS_TABLE_NAMES.contains(t)
      || t.startsWith("web_")
      || t.startsWith("cms_")
      || t.contains("banner")
      || t.contains("slider")
      || t.contains("page")
      || t.contains("content");
  }

  private static List<Map<String, Object>> domainEntities(SemanticCatalog catalog) {
    List<Map<String, Object>> entities = new ArrayList<>();
    CatalogTable projects = catalog.table("projects");
    if (projects != null) {
      entities.add(Map.of(
        "entity", "projects",
        "table", projects.logicalName(),
        "purpose", "operational construction projects",
        "count_operation", "count",
        "reason", "real Laravel operational project table"
      ));
    }
    return List.copyOf(entities);
  }

  private static String logicalColumn(String table, String column, Set<String> used) {
    String singular = singular(table);
    if (column.equals(singular + "_status")) return unused("status", used);
    if (column.equals(singular + "_type")) return unused("type", used);
    return unused(column, used);
  }

  private static String unused(String base, Set<String> used) {
    if (!used.contains(base)) return base;
    int i = 2;
    while (used.contains(base + "_" + i)) i++;
    return base + "_" + i;
  }

  private static String singular(String table) {
    if (table.endsWith("ies")) return table.substring(0, table.length() - 3) + "y";
    if (table.endsWith("s") && table.length() > 1) return table.substring(0, table.length() - 1);
    return table;
  }

  private static String fieldType(String dbType) {
    String t = dbType.toLowerCase(Locale.ROOT);
    if (t.contains("int") || t.contains("decimal") || t.contains("double") || t.contains("float")) return "number";
    if (t.contains("date") || t.contains("time")) return "date";
    if (t.contains("bool")) return "boolean";
    return "string";
  }

  private static List<String> operations(String dbType, boolean sensitive) {
    if (sensitive) return List.of();
    String type = fieldType(dbType);
    if ("number".equals(type)) return List.of("filter", "sort", "group", "sum", "avg", "min", "max");
    if ("date".equals(type)) return List.of("filter", "sort", "group");
    return List.of("filter", "sort", "group");
  }

  private static List<String> tableOperations(List<CatalogColumn> columns) {
    List<String> ops = new ArrayList<>(List.of("count", "list"));
    if (columns.stream().anyMatch(c -> c.enabled() && c.allowedOperations().contains("group"))) ops.add("group_count");
    if (columns.stream().anyMatch(c -> c.enabled() && c.allowedOperations().contains("sum"))) ops.add("sum");
    if (columns.stream().anyMatch(c -> c.enabled() && c.allowedOperations().contains("avg"))) ops.add("avg");
    return List.copyOf(ops);
  }

  private static List<String> enumValues(Connection c, String table, ColumnSource column) {
    if (!safeIdentifier(table) || !safeIdentifier(column.name())) return List.of();
    String fieldType = fieldType(column.type());
    if (sensitive(column.name())) return List.of();
    if (!"string".equals(fieldType) && !("number".equals(fieldType) && (column.name().contains("status") || column.name().contains("type")))) return List.of();
    try (Statement s = c.createStatement();
         ResultSet rs = s.executeQuery("select count(distinct " + column.name() + ") from " + table + " where " + column.name() + " is not null")) {
      if (!rs.next() || rs.getLong(1) > 30) return List.of();
    } catch (Exception ex) {
      return List.of();
    }
    List<String> values = new ArrayList<>();
    try (Statement s = c.createStatement();
         ResultSet rs = s.executeQuery("select distinct " + column.name() + " from " + table + " where " + column.name() + " is not null limit 20")) {
      while (rs.next()) values.add(String.valueOf(rs.getObject(1)));
    } catch (Exception ignored) {
      return List.of();
    }
    return List.copyOf(values);
  }

  private static long approximateRows(Connection c, String table) {
    try (PreparedStatement ps = c.prepareStatement("""
          select table_rows from information_schema.tables
          where table_schema = database() and table_name = ?
          """)) {
      ps.setString(1, table);
      try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) return Math.max(rs.getLong(1), 0L);
      }
    } catch (Exception ignored) {
    }
    return -1;
  }

  private static String entityName(String table) {
    return singular(table).replace('_', ' ');
  }

  private static List<String> arabicSynonyms(String table) {
    if (table.contains("project")) return List.of("مشروع", "مشاريع");
    if (table.contains("client") || table.contains("customer")) return List.of("عميل", "عملاء");
    if (table.contains("user")) return List.of("مستخدم", "مستخدمين");
    if (table.contains("invoice")) return List.of("فاتورة", "فواتير");
    if (table.contains("payment")) return List.of("مدفوعة", "مدفوعات");
    return List.of(table);
  }

  private static List<String> englishSynonyms(String table) {
    List<String> out = new ArrayList<>();
    out.add(table);
    out.add(singular(table));
    return List.copyOf(new LinkedHashSet<>(out));
  }

  private static String string(Object value) { return value == null ? "" : String.valueOf(value); }
  private static boolean safeIdentifier(String value) { return value != null && value.matches("[A-Za-z_][A-Za-z0-9_]*"); }
  private static boolean bool(Object value) { return value instanceof Boolean b ? b : Boolean.parseBoolean(string(value)); }
  private static int intValue(Object value) { return value instanceof Number n ? n.intValue() : Integer.parseInt(string(value)); }
  private static long longValue(Object value) { return value instanceof Number n ? n.longValue() : Long.parseLong(string(value)); }
  private static List<String> list(Object value) {
    if (!(value instanceof List<?> raw)) return List.of();
    List<String> out = new ArrayList<>();
    for (Object item : raw) out.add(string(item));
    return List.copyOf(out);
  }

  private record ColumnSource(String name, String type, boolean nullable, String key) {}
}

record SemanticCatalog(String clientName, int version, String generatedAt, String schemaHash, boolean enabled, List<CatalogTable> tables) {
  CatalogTable table(String name) {
    return tables.stream().filter(t -> t.enabled() && t.logicalName().equals(name)).findFirst().orElse(null);
  }

  Map<String, Object> toMap() {
    return Map.of(
      "client_name", clientName,
      "catalog_version", version,
      "generated_at", generatedAt,
      "schema_hash", schemaHash,
      "enabled", enabled,
      "tables", tables.stream().map(CatalogTable::toMap).toList()
    );
  }
}

record CatalogTable(String logicalName, String physicalName, String entityName, List<String> arabicSynonyms, List<String> englishSynonyms, List<CatalogColumn> columns, List<String> allowedOperations, boolean enabled, long approximateRows) {
  CatalogColumn column(String name) {
    return columns.stream().filter(c -> c.enabled() && c.logicalName().equals(name)).findFirst().orElse(null);
  }

  Map<String, Object> toMap() {
    return Map.of(
      "logical_name", logicalName,
      "physical_name", physicalName,
      "entity_name", entityName,
      "arabic_synonyms", arabicSynonyms,
      "english_synonyms", englishSynonyms,
      "columns", columns.stream().map(CatalogColumn::toMap).toList(),
      "allowed_operations", allowedOperations,
      "enabled", enabled,
      "approx_rows", approximateRows
    );
  }
}

record CatalogColumn(String logicalName, String physicalName, String fieldType, boolean nullable, List<String> allowedOperations, List<String> enumValues, boolean sensitive, boolean enabled) {
  Map<String, Object> toMap() {
    return Map.of(
      "logical_name", logicalName,
      "physical_name", physicalName,
      "field_type", fieldType,
      "nullable", nullable,
      "allowed_operations", allowedOperations,
      "enum_values", enumValues,
      "sensitive", sensitive,
      "enabled", enabled
    );
  }
}
