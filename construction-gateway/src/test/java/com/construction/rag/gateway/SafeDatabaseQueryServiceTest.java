package com.construction.rag.gateway;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.util.List;
import java.util.Map;
import javax.sql.DataSource;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

class SafeDatabaseQueryServiceTest {
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

    SafeDatabaseQueryService service = new SafeDatabaseQueryService(manager);
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
}
