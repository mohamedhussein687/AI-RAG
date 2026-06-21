package com.construction.rag.gateway;

import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import javax.sql.DataSource;
import org.springframework.stereotype.Component;

@Component
class ClientDataSourceManager {
  private final ClientSecretCrypto crypto;
  private final Map<Long, HikariDataSource> cache = new ConcurrentHashMap<>();

  ClientDataSourceManager(ClientSecretCrypto crypto) {
    this.crypto = crypto;
  }

  DataSource dataSource(RagClient client) {
    return cache.computeIfAbsent(client.id(), ignored -> create(client));
  }

  private HikariDataSource create(RagClient client) {
    HikariConfig config = new HikariConfig();
    config.setJdbcUrl(jdbcUrl(client));
    config.setUsername(client.dbUsername());
    config.setPassword(crypto.decrypt(client.dbPasswordEncrypted()));
    config.setMaximumPoolSize(3);
    config.setMinimumIdle(0);
    config.setConnectionTimeout(5000);
    config.setValidationTimeout(3000);
    config.setIdleTimeout(30000);
    config.setMaxLifetime(300000);
    config.setReadOnly(true);
    config.setPoolName("rag-client-" + client.clientName());
    return new HikariDataSource(config);
  }

  private String jdbcUrl(RagClient client) {
    return switch (client.dbType().toLowerCase()) {
      case "postgres", "postgresql" -> "jdbc:postgresql://" + client.dbHost() + ":" + client.dbPort() + "/" + client.dbName();
      case "mysql", "mariadb" -> "jdbc:mysql://" + client.dbHost() + ":" + client.dbPort() + "/" + client.dbName()
        + "?useSSL=true&allowPublicKeyRetrieval=false&serverTimezone=UTC";
      default -> throw new IllegalArgumentException("unsupported client database type");
    };
  }
}
