package com.construction.rag.gateway;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.time.LocalDate;
import java.util.List;
import java.util.Map;
import javax.sql.DataSource;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

class SafeDatabaseQueryServiceTest {
  @Test
  void logicalUsersTableCanMapToOrganizationEmployees() throws Exception {
    ClientDataSourceManager manager = mock(ClientDataSourceManager.class);
    DataSource dataSource = mock(DataSource.class);
    Connection connection = mock(Connection.class);
    DatabaseMetaData metaData = mock(DatabaseMetaData.class);
    ResultSet tables = mock(ResultSet.class);
    ResultSet columns = mock(ResultSet.class);
    PreparedStatement statement = mock(PreparedStatement.class);
    ResultSet queryResult = mock(ResultSet.class);
    SemanticCatalogService catalogs = mock(SemanticCatalogService.class);
    RagClient orbit = new RagClient(7, "orbit", "mysql", "db", 3306, "testorbit", "user", "encrypted", "active");

    when(manager.dataSource(orbit)).thenReturn(dataSource);
    when(dataSource.getConnection()).thenReturn(connection);
    when(connection.getCatalog()).thenReturn("testorbit");
    when(connection.getMetaData()).thenReturn(metaData);
    when(metaData.getTables(eq("testorbit"), any(), eq("organization_employees"), any())).thenReturn(tables);
    when(tables.next()).thenReturn(true);
    when(metaData.getColumns("testorbit", null, "organization_employees", "name")).thenReturn(columns);
    when(columns.next()).thenReturn(true);
    when(connection.prepareStatement("select name as name from organization_employees limit 20")).thenReturn(statement);
    when(statement.executeQuery()).thenReturn(queryResult);
    when(queryResult.next()).thenReturn(true, false);
    when(queryResult.getObject("name")).thenReturn("Orbit User");
    when(catalogs.catalog(orbit)).thenReturn(new SemanticCatalog("orbit", 9, "now", "hash", true, List.of(new CatalogTable(
      "users", "organization_employees", "user", List.of("مستخدم", "مستخدمين"), List.of("users", "user", "organization_employees"),
      List.of(new CatalogColumn("name", "name", "string", true, List.of("filter", "sort", "group"), List.of(), false, true)),
      List.of("count", "list", "select"), true, 86
    ))));

    SafeDatabaseQueryService service = new SafeDatabaseQueryService(manager, catalogs);
    Map<String, Object> result = service.execute(orbit, Map.of(
      "plan", Map.of(
        "operation", "list",
        "table", "users",
        "columns", List.of("name"),
        "limit", 20
      )
    )).block();

    assertThat(result).containsEntry("table", "users");
    assertThat(((List<?>) result.get("rows"))).hasSize(1);
    verify(connection).prepareStatement("select name as name from organization_employees limit 20");
  }

  @Test
  void userDetailsUsesExactLogicalUsersTableBeforePhysicalMapping() throws Exception {
    ClientDataSourceManager manager = mock(ClientDataSourceManager.class);
    DataSource dataSource = mock(DataSource.class);
    Connection connection = mock(Connection.class);
    DatabaseMetaData metaData = mock(DatabaseMetaData.class);
    ResultSet tables = mock(ResultSet.class);
    PreparedStatement statement = mock(PreparedStatement.class);
    ResultSet queryResult = mock(ResultSet.class);
    SemanticCatalogService catalogs = mock(SemanticCatalogService.class);
    RagClient orbit = new RagClient(7, "orbit", "mysql", "db", 3306, "testorbit", "user", "encrypted", "active");

    when(manager.dataSource(orbit)).thenReturn(dataSource);
    when(dataSource.getConnection()).thenReturn(connection);
    when(connection.getCatalog()).thenReturn("testorbit");
    when(connection.getMetaData()).thenReturn(metaData);
    when(metaData.getTables(eq("testorbit"), any(), eq("organization_employees"), any())).thenReturn(tables);
    when(tables.next()).thenReturn(true);
    when(metaData.getColumns(eq("testorbit"), any(), eq("organization_employees"), any())).thenAnswer(invocation -> {
      ResultSet rs = mock(ResultSet.class);
      when(rs.next()).thenReturn(true);
      return rs;
    });
    String sql = "select name as name, type as type from organization_employees where name like ? limit 1";
    when(connection.prepareStatement(sql)).thenReturn(statement);
    when(statement.executeQuery()).thenReturn(queryResult);
    when(queryResult.next()).thenReturn(true, false);
    when(queryResult.getObject("name")).thenReturn("Ayman Ibrahim El Sayed");
    when(queryResult.getObject("type")).thenReturn(2);
    when(catalogs.catalog(orbit)).thenReturn(new SemanticCatalog("orbit", 9, "now", "hash", true, List.of(new CatalogTable(
      "users", "organization_employees", "user", List.of("مستخدم", "مستخدمين", "حساب"), List.of("users", "user", "account", "organization_employees"),
      List.of(
        new CatalogColumn("name", "name", "string", true, List.of("filter", "sort", "group"), List.of(), false, true),
        new CatalogColumn("type", "type", "number", true, List.of("filter", "sort", "group"), List.of(), false, true)
      ),
      List.of("count", "list", "select"), true, 86
    ))));

    SafeDatabaseQueryService service = new SafeDatabaseQueryService(manager, catalogs);
    Map<String, Object> result = service.execute(orbit, Map.of(
      "plan", Map.of(
        "operation", "select",
        "table", "users",
        "columns", List.of("name", "type"),
        "filters", List.of(Map.of("column", "name", "operator", "contains", "value", "Ayman Ibrahim El Sayed")),
        "limit", 1
      )
    )).block();

    assertThat(result).containsEntry("table", "users");
    assertThat(((List<?>) result.get("rows"))).hasSize(1);
    verify(statement).setObject(eq(1), eq("%Ayman Ibrahim El Sayed%"));
    verify(connection).prepareStatement(sql);
  }

  @Test
  void nonSchemaUserAliasIsRejectedBeforeExecution() {
    ClientDataSourceManager manager = mock(ClientDataSourceManager.class);
    SemanticCatalogService catalogs = mock(SemanticCatalogService.class);
    RagClient orbit = new RagClient(7, "orbit", "mysql", "db", 3306, "testorbit", "user", "encrypted", "active");
    when(catalogs.catalog(orbit)).thenReturn(new SemanticCatalog("orbit", 9, "now", "hash", true, List.of(new CatalogTable(
      "users", "organization_employees", "user", List.of("مستخدم", "مستخدمين"), List.of("users", "organization_employees"),
      List.of(new CatalogColumn("name", "name", "string", true, List.of("filter", "sort", "group"), List.of(), false, true)),
      List.of("count", "list", "select"), true, 86
    ))));

    SafeDatabaseQueryService service = new SafeDatabaseQueryService(manager, catalogs);

    assertThatThrownBy(() -> service.execute(orbit, Map.of(
      "plan", Map.of(
        "operation", "list",
        "table", "user",
        "columns", List.of("name"),
        "limit", 20
      )
    )).block())
      .isInstanceOf(IllegalArgumentException.class)
      .hasMessageContaining("requested_table=user")
      .hasMessageContaining("allowed_tables=[users]");
  }

  @Test
  void unknownSchemaBackedColumnIsRejectedBeforeExecution() {
    ClientDataSourceManager manager = mock(ClientDataSourceManager.class);
    SemanticCatalogService catalogs = mock(SemanticCatalogService.class);
    RagClient orbit = new RagClient(7, "orbit", "mysql", "db", 3306, "testorbit", "user", "encrypted", "active");
    when(catalogs.catalog(orbit)).thenReturn(new SemanticCatalog("orbit", 10, "now", "hash", true, List.of(new CatalogTable(
      "users", "users", "user", List.of("مستخدم", "مستخدمين"), List.of("users", "user"),
      List.of(new CatalogColumn("name", "name", "string", true, List.of("filter", "sort", "group"), List.of(), false, true)),
      List.of("count", "list", "select"), true, 2
    ))));

    SafeDatabaseQueryService service = new SafeDatabaseQueryService(manager, catalogs);

    assertThatThrownBy(() -> service.execute(orbit, Map.of(
      "plan", Map.of(
        "operation", "list",
        "table", "users",
        "columns", List.of("name", "password"),
        "limit", 20
      )
    )).block())
      .isInstanceOf(IllegalArgumentException.class)
      .hasMessageContaining("columns is not allowlisted");
  }

  @Test
  void orbitMapsLogicalStatusToPhysicalProjectStatus() throws Exception {
    ClientDataSourceManager manager = mock(ClientDataSourceManager.class);
    DataSource dataSource = mock(DataSource.class);
    Connection connection = mock(Connection.class);
    DatabaseMetaData metaData = mock(DatabaseMetaData.class);
    ResultSet tables = mock(ResultSet.class);
    ResultSet columns = mock(ResultSet.class);
    PreparedStatement statement = mock(PreparedStatement.class);
    ResultSet queryResult = mock(ResultSet.class);
    SemanticCatalogService catalogs = mock(SemanticCatalogService.class);
    RagClient orbit = new RagClient(7, "orbit", "mysql", "db", 3306, "orbit", "user", "encrypted", "active");

    when(manager.dataSource(orbit)).thenReturn(dataSource);
    when(dataSource.getConnection()).thenReturn(connection);
    when(connection.getCatalog()).thenReturn("testorbit");
    when(connection.getMetaData()).thenReturn(metaData);
    when(metaData.getTables(eq("testorbit"), any(), eq("projects"), any())).thenReturn(tables);
    when(tables.next()).thenReturn(true);
    when(metaData.getColumns("testorbit", null, "projects", "project_status")).thenReturn(columns);
    when(columns.next()).thenReturn(true);
    when(connection.prepareStatement("select count(*) as count from projects where project_status = ?")).thenReturn(statement);
    when(statement.executeQuery()).thenReturn(queryResult);
    when(queryResult.next()).thenReturn(true);
    when(queryResult.getLong(1)).thenReturn(0L);
    when(catalogs.catalog(orbit)).thenReturn(new SemanticCatalog("orbit", 1, "now", "hash", true, List.of(new CatalogTable(
      "projects", "projects", "project", List.of("مشروع", "مشاريع"), List.of("projects", "project"),
      List.of(new CatalogColumn("status", "project_status", "string", true, List.of("filter", "group"), List.of("waiting"), false, true)),
      List.of("count", "group_count"), true, 0
    ))));

    SafeDatabaseQueryService service = new SafeDatabaseQueryService(manager, catalogs);
    Map<String, Object> result = service.execute(orbit, Map.of(
      "plan", Map.of(
        "operation", "count",
        "table", "projects",
        "filters", List.of(Map.of("column", "status", "operator", "eq", "value", "waiting"))
      )
    )).block();

    assertThat(result).containsEntry("count", 0L);
    ArgumentCaptor<Object> value = ArgumentCaptor.forClass(Object.class);
    verify(statement).setObject(eq(1), value.capture());
    assertThat(value.getValue()).isEqualTo("waiting");
  }

  @Test
  void delayedProjectsReportUsesProjectsDeadlineAndCompletionFields() throws Exception {
    ClientDataSourceManager manager = mock(ClientDataSourceManager.class);
    DataSource dataSource = mock(DataSource.class);
    Connection connection = mock(Connection.class);
    DatabaseMetaData metaData = mock(DatabaseMetaData.class);
    ResultSet tables = mock(ResultSet.class);
    PreparedStatement statement = mock(PreparedStatement.class);
    ResultSet queryResult = mock(ResultSet.class);
    SemanticCatalogService catalogs = mock(SemanticCatalogService.class);
    RagClient orbit = new RagClient(7, "orbit", "mysql", "db", 3306, "orbit", "user", "encrypted", "active");

    when(manager.dataSource(orbit)).thenReturn(dataSource);
    when(dataSource.getConnection()).thenReturn(connection);
    when(connection.getCatalog()).thenReturn("testorbit");
    when(connection.getMetaData()).thenReturn(metaData);
    when(metaData.getTables(eq("testorbit"), any(), eq("projects"), any())).thenReturn(tables);
    when(tables.next()).thenReturn(true);
    when(metaData.getColumns(eq("testorbit"), any(), eq("projects"), any())).thenAnswer(invocation -> {
      ResultSet rs = mock(ResultSet.class);
      when(rs.next()).thenReturn(true);
      return rs;
    });
    when(connection.prepareStatement("select title as title, project_status as status, last_plan_finish_date as planned_delivery_date, actual_date as actual_delivery_date, is_finished as is_finished, updated_at as updated_at from projects where last_plan_finish_date < ? and is_finished = ? order by updated_at desc limit 4")).thenReturn(statement);
    when(statement.executeQuery()).thenReturn(queryResult);
    when(queryResult.next()).thenReturn(false);
    when(catalogs.catalog(orbit)).thenReturn(new SemanticCatalog("orbit", 4, "now", "hash", true, List.of(new CatalogTable(
      "projects", "projects", "project", List.of("مشروع", "مشاريع"), List.of("projects", "project"),
      List.of(
        new CatalogColumn("title", "title", "string", true, List.of("filter", "sort", "group"), List.of(), false, true),
        new CatalogColumn("status", "project_status", "number", true, List.of("filter", "sort", "group"), List.of(), false, true),
        new CatalogColumn("planned_delivery_date", "last_plan_finish_date", "date", true, List.of("filter", "sort", "group"), List.of(), false, true),
        new CatalogColumn("actual_delivery_date", "actual_date", "string", true, List.of("filter", "sort", "group"), List.of(), false, true),
        new CatalogColumn("is_finished", "is_finished", "number", true, List.of("filter", "sort", "group"), List.of("0", "1"), false, true),
        new CatalogColumn("updated_at", "updated_at", "date", true, List.of("filter", "sort", "group"), List.of(), false, true)
      ),
      List.of("count", "list", "select", "group_count"), true, 0
    ))));

    SafeDatabaseQueryService service = new SafeDatabaseQueryService(manager, catalogs);
    Map<String, Object> result = service.execute(orbit, Map.of(
      "plan", Map.of(
        "intent", "delayed_projects_report",
        "operation", "select",
        "table", "projects",
        "columns", List.of("title", "status", "planned_delivery_date", "actual_delivery_date", "is_finished", "updated_at"),
        "filters", List.of(
          Map.of("column", "planned_delivery_date", "operator", "lt", "value", "today"),
          Map.of("column", "is_finished", "operator", "not_completed", "value", false)
        ),
        "order_by", Map.of("column", "updated_at", "direction", "desc"),
        "limit", 4
      )
    )).block();

    assertThat(result).containsEntry("intent", "delayed_projects_report");
    assertThat(result).containsEntry("table", "projects");
    verify(statement).setObject(eq(1), org.mockito.ArgumentMatchers.isA(LocalDate.class));
    verify(statement).setObject(eq(2), eq(0));
  }

  @Test
  void projectDetailsUsesExactThenFuzzyLookupOnAllowlistedFields() throws Exception {
    ClientDataSourceManager manager = mock(ClientDataSourceManager.class);
    DataSource dataSource = mock(DataSource.class);
    Connection connection = mock(Connection.class);
    DatabaseMetaData metaData = mock(DatabaseMetaData.class);
    ResultSet tables = mock(ResultSet.class);
    PreparedStatement exact = mock(PreparedStatement.class);
    PreparedStatement fuzzy = mock(PreparedStatement.class);
    ResultSet exactResult = mock(ResultSet.class);
    ResultSet fuzzyResult = mock(ResultSet.class);
    SemanticCatalogService catalogs = mock(SemanticCatalogService.class);
    RagClient orbit = new RagClient(7, "orbit", "mysql", "db", 3306, "orbit", "user", "encrypted", "active");

    when(manager.dataSource(orbit)).thenReturn(dataSource);
    when(dataSource.getConnection()).thenReturn(connection);
    when(connection.getCatalog()).thenReturn("testorbit");
    when(connection.getMetaData()).thenReturn(metaData);
    when(metaData.getTables(eq("testorbit"), any(), eq("projects"), any())).thenReturn(tables);
    when(tables.next()).thenReturn(true);
    when(metaData.getColumns(eq("testorbit"), any(), eq("projects"), any())).thenAnswer(invocation -> {
      ResultSet rs = mock(ResultSet.class);
      when(rs.next()).thenReturn(true);
      return rs;
    });
    String exactSql = "select title as title, project_code as project_code, project_serial as project_serial, project_status as status, updated_at as updated_at from projects where title = ? or project_code = ? or project_serial = ? limit 1";
    String fuzzySql = "select title as title, project_code as project_code, project_serial as project_serial, project_status as status, updated_at as updated_at from projects where title like ? or project_code like ? or project_serial like ? order by updated_at desc limit 1";
    when(connection.prepareStatement(exactSql)).thenReturn(exact);
    when(connection.prepareStatement(fuzzySql)).thenReturn(fuzzy);
    when(exact.executeQuery()).thenReturn(exactResult);
    when(exactResult.next()).thenReturn(false);
    when(fuzzy.executeQuery()).thenReturn(fuzzyResult);
    when(fuzzyResult.next()).thenReturn(true, false);
    when(fuzzyResult.getObject("title")).thenReturn("test60");
    when(fuzzyResult.getObject("project_code")).thenReturn("T60");
    when(fuzzyResult.getObject("project_serial")).thenReturn("60");
    when(fuzzyResult.getObject("status")).thenReturn("waiting");
    when(fuzzyResult.getObject("updated_at")).thenReturn(null);
    when(catalogs.catalog(orbit)).thenReturn(new SemanticCatalog("orbit", 5, "now", "hash", true, List.of(new CatalogTable(
      "projects", "projects", "project", List.of("مشروع", "مشاريع"), List.of("projects", "project"),
      List.of(
        new CatalogColumn("title", "title", "string", true, List.of("filter", "sort", "group"), List.of(), false, true),
        new CatalogColumn("project_code", "project_code", "string", true, List.of("filter", "sort", "group"), List.of(), false, true),
        new CatalogColumn("project_serial", "project_serial", "string", true, List.of("filter", "sort", "group"), List.of(), false, true),
        new CatalogColumn("status", "project_status", "string", true, List.of("filter", "sort", "group"), List.of(), false, true),
        new CatalogColumn("updated_at", "updated_at", "date", true, List.of("filter", "sort", "group"), List.of(), false, true)
      ),
      List.of("count", "list", "select", "details", "group_count"), true, 0
    ))));

    SafeDatabaseQueryService service = new SafeDatabaseQueryService(manager, catalogs);
    Map<String, Object> result = service.execute(orbit, Map.of(
      "plan", Map.of(
        "intent", "project_details",
        "operation", "details",
        "table", "projects",
        "lookup_value", "test60",
        "lookup_fields", List.of("title", "project_code", "project_serial"),
        "columns", List.of("title", "project_code", "project_serial", "status", "updated_at"),
        "limit", 1
      )
    )).block();

    assertThat(result).containsEntry("intent", "project_details");
    assertThat(result).containsEntry("table", "projects");
    assertThat(((List<?>) result.get("rows"))).hasSize(1);
    verify(exact).setObject(eq(1), eq("test60"));
    verify(fuzzy).setObject(eq(1), eq("%test60%"));
  }

  @Test
  void projectDetailsByCodeUsesNormalizedParameterizedLookup() throws Exception {
    ClientDataSourceManager manager = mock(ClientDataSourceManager.class);
    DataSource dataSource = mock(DataSource.class);
    Connection connection = mock(Connection.class);
    DatabaseMetaData metaData = mock(DatabaseMetaData.class);
    ResultSet tables = mock(ResultSet.class);
    PreparedStatement statement = mock(PreparedStatement.class);
    ResultSet queryResult = mock(ResultSet.class);
    SemanticCatalogService catalogs = mock(SemanticCatalogService.class);
    RagClient orbit = new RagClient(7, "orbit", "mysql", "db", 3306, "orbit", "user", "encrypted", "active");

    when(manager.dataSource(orbit)).thenReturn(dataSource);
    when(dataSource.getConnection()).thenReturn(connection);
    when(connection.getCatalog()).thenReturn("testorbit");
    when(connection.getMetaData()).thenReturn(metaData);
    when(metaData.getTables(eq("testorbit"), any(), eq("projects"), any())).thenReturn(tables);
    when(tables.next()).thenReturn(true);
    when(metaData.getColumns(eq("testorbit"), any(), eq("projects"), any())).thenAnswer(invocation -> {
      ResultSet rs = mock(ResultSet.class);
      when(rs.next()).thenReturn(true);
      return rs;
    });
    String sql = "select title as title, project_code as project_code, project_status as status, updated_at as updated_at from projects where project_code = ? or lower(trim(project_code)) = lower(?) or replace(replace(replace(lower(project_code), ' ', ''), '–', '-'), '—', '-') = ? limit 1";
    when(connection.prepareStatement(sql)).thenReturn(statement);
    when(statement.executeQuery()).thenReturn(queryResult);
    when(queryResult.next()).thenReturn(false);
    when(catalogs.catalog(orbit)).thenReturn(new SemanticCatalog("orbit", 7, "now", "hash", true, List.of(new CatalogTable(
      "projects", "projects", "project", List.of("مشروع", "مشاريع"), List.of("projects", "project"),
      List.of(
        new CatalogColumn("title", "title", "string", true, List.of("filter", "sort", "group"), List.of(), false, true),
        new CatalogColumn("project_code", "project_code", "string", true, List.of("filter", "sort", "group"), List.of(), false, true),
        new CatalogColumn("status", "project_status", "string", true, List.of("filter", "sort", "group"), List.of(), false, true),
        new CatalogColumn("updated_at", "updated_at", "date", true, List.of("filter", "sort", "group"), List.of(), false, true)
      ),
      List.of("count", "list", "select", "details", "group_count"), true, 0
    ))));

    SafeDatabaseQueryService service = new SafeDatabaseQueryService(manager, catalogs);
    Map<String, Object> result = service.execute(orbit, Map.of(
      "plan", Map.of(
        "intent", "project_details",
        "operation", "details",
        "table", "projects",
        "columns", List.of("title", "project_code", "status", "updated_at"),
        "filters", List.of(Map.of("column", "project_code", "operator", "code_equals_normalized", "value", "c832-p2-06-2026")),
        "limit", 1
      )
    )).block();

    assertThat(result).containsEntry("lookup_type", "project_code");
    assertThat(result).containsEntry("lookup_value", "c832-p2-06-2026");
    verify(statement).setObject(eq(1), eq("c832-p2-06-2026"));
    verify(statement).setObject(eq(2), eq("c832-p2-06-2026"));
    verify(statement).setObject(eq(3), eq("c832-p2-06-2026"));
  }
}
