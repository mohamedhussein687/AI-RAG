package com.construction.rag.gateway;

import java.util.Optional;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

@Component
class RagClientRegistry implements ApplicationRunner {
  private final JdbcTemplate jdbc;
  private final ClientSecretCrypto crypto;
  private final GatewayProperties props;

  RagClientRegistry(JdbcTemplate jdbc, ClientSecretCrypto crypto, GatewayProperties props) {
    this.jdbc = jdbc;
    this.crypto = crypto;
    this.props = props;
  }

  @Override
  public void run(ApplicationArguments args) {
    ensureTable();
    seedOrbitIfConfigured();
  }

  Optional<RagClient> findByApiKey(String apiKey) {
    String hash = crypto.apiKeyHash(apiKey);
    return jdbc.query("""
        select id, client_name, db_type, db_host, db_port, db_name, db_username, db_password_encrypted, status
        from rag_clients
        where api_key_hash = ?
        """,
      (rs, rowNum) -> new RagClient(
        rs.getLong("id"),
        rs.getString("client_name"),
        rs.getString("db_type"),
        rs.getString("db_host"),
        rs.getInt("db_port"),
        rs.getString("db_name"),
        rs.getString("db_username"),
        rs.getString("db_password_encrypted"),
        rs.getString("status")
      ),
      hash
    ).stream().findFirst();
  }

  Optional<RagClient> findByClientName(String clientName) {
    return jdbc.query("""
        select id, client_name, db_type, db_host, db_port, db_name, db_username, db_password_encrypted, status
        from rag_clients
        where client_name = ?
        """,
      (rs, rowNum) -> new RagClient(
        rs.getLong("id"),
        rs.getString("client_name"),
        rs.getString("db_type"),
        rs.getString("db_host"),
        rs.getInt("db_port"),
        rs.getString("db_name"),
        rs.getString("db_username"),
        rs.getString("db_password_encrypted"),
        rs.getString("status")
      ),
      clientName
    ).stream().findFirst();
  }

  private void ensureTable() {
    jdbc.execute("""
      create table if not exists rag_clients (
        id bigserial primary key,
        api_key_hash varchar(128) not null unique,
        client_name varchar(120) not null unique,
        db_type varchar(32) not null,
        db_host varchar(255) not null,
        db_port integer not null,
        db_name varchar(120) not null,
        db_username varchar(120) not null,
        db_password_encrypted text not null,
        status varchar(32) not null,
        created_at timestamptz not null default now(),
        updated_at timestamptz not null default now()
      )
      """);
    jdbc.execute("create index if not exists idx_rag_clients_api_key_hash on rag_clients(api_key_hash)");
    jdbc.execute("create index if not exists idx_rag_clients_status on rag_clients(status)");
  }

  private void seedOrbitIfConfigured() {
    if (blank(props.orbitApiKey()) || blank(props.orbitDbHost()) || blank(props.orbitDbName())
      || blank(props.orbitDbUsername()) || blank(props.orbitDbPassword())) {
      return;
    }
    String dbType = blank(props.orbitDbType()) ? "mysql" : props.orbitDbType();
    int port = props.orbitDbPort() == null ? defaultPort(dbType) : props.orbitDbPort();
    String hash = crypto.apiKeyHash(props.orbitApiKey());
    String encryptedPassword = crypto.encrypt(props.orbitDbPassword());
    Integer count = jdbc.queryForObject("select count(*) from rag_clients where client_name = 'orbit'", Integer.class);
    if (count != null && count > 0) {
      jdbc.update("""
        update rag_clients
        set api_key_hash = ?, db_type = ?, db_host = ?, db_port = ?, db_name = ?, db_username = ?,
            db_password_encrypted = ?, status = 'active', updated_at = now()
        where client_name = 'orbit'
        """, hash, dbType, props.orbitDbHost(), port, props.orbitDbName(), props.orbitDbUsername(), encryptedPassword);
    } else {
      jdbc.update("""
        insert into rag_clients(api_key_hash, client_name, db_type, db_host, db_port, db_name, db_username, db_password_encrypted, status)
        values (?, 'orbit', ?, ?, ?, ?, ?, ?, 'active')
        """, hash, dbType, props.orbitDbHost(), port, props.orbitDbName(), props.orbitDbUsername(), encryptedPassword);
    }
  }

  private static int defaultPort(String dbType) {
    return "postgres".equalsIgnoreCase(dbType) || "postgresql".equalsIgnoreCase(dbType) ? 5432 : 3306;
  }

  private static boolean blank(String value) {
    return value == null || value.isBlank();
  }
}
