package com.construction.rag.gateway;

record RagClient(
  long id,
  String clientName,
  String dbType,
  String dbHost,
  int dbPort,
  String dbName,
  String dbUsername,
  String dbPasswordEncrypted,
  String status
) {
  boolean active() {
    return "active".equalsIgnoreCase(status);
  }
}
