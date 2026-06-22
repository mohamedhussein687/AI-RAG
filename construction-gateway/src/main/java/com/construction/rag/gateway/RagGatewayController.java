package com.construction.rag.gateway;

import jakarta.validation.Valid;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.server.ServerWebExchange;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import reactor.core.publisher.Mono;

@RestController
@Validated
class RagGatewayController {
  private static final Logger log = LoggerFactory.getLogger(RagGatewayController.class);
  private static final Set<String> FORBIDDEN_PUBLIC_CONTEXT_KEYS = Set.of(
    "user_context", "userContext", "tenant_id", "tenantId", "project_id", "projectId", "project_ids", "projectIds",
    "roles", "permissions", "admin", "isAdmin", "allowed_schema", "allowedSchema", "database_scope", "databaseScope"
    , "semantic_catalog", "semanticCatalog"
  );

  private final AiModuleClient ai;
  private final SafeDatabaseQueryService databaseQueries;
  private final SemanticCatalogService catalogs;
  private final RagClientRegistry clients;

  RagGatewayController(AiModuleClient ai, SafeDatabaseQueryService databaseQueries, SemanticCatalogService catalogs, RagClientRegistry clients) {
    this.ai = ai;
    this.databaseQueries = databaseQueries;
    this.catalogs = catalogs;
    this.clients = clients;
  }

  @GetMapping("/health/live") Map<String, String> live() { return Map.of("status", "ok"); }
  @GetMapping("/health/ready") Mono<Object> ready() { return ai.get("/health/ready"); }

  @PostMapping("/api/agent/decide")
  Mono<Object> decide(@Valid @RequestBody Map<String, Object> request, ServerWebExchange exchange) {
    rejectSql(request);
    rejectClientContext(request);
    return ai.post("/api/agent/decide", agentRequest(request, exchange));
  }

  @PostMapping("/api/agent/final")
  Mono<Object> finalAnswer(@Valid @RequestBody Map<String, Object> request, ServerWebExchange exchange) {
    rejectSql(request);
    rejectClientContext(request);
    identity(exchange);
    return ai.post("/api/agent/final", request);
  }

  @PostMapping("/api/rag/documents")
  Mono<Object> indexDocument(@Valid @RequestBody Map<String, Object> request, ServerWebExchange exchange) {
    rejectSql(request);
    rejectClientContext(request);
    TrustedIdentity identity = identity(exchange);
    requirePermission(identity, "docs.admin");
    Map<String, Object> normalized = mutableCopy(request);
    normalized.put("tenant_id", identity.tenantId());
    if (!identity.projectIds().isEmpty()) normalized.put("project_id", identity.projectIds().getFirst());
    normalized.put("access_policy", Map.of("permissions", identity.permissions()));
    return ai.post("/api/rag/documents", normalized);
  }

  @PostMapping("/api/rag/search")
  Mono<Object> search(@Valid @RequestBody Map<String, Object> request, ServerWebExchange exchange) {
    rejectSql(request);
    rejectClientContext(request);
    Map<String, Object> normalized = mutableCopy(request);
    normalized.put("user_context", identity(exchange).userContext());
    return ai.post("/api/rag/search", normalized);
  }

  @PostMapping("/api/chat")
  Mono<Object> chat(@Valid @RequestBody Map<String, Object> request, ServerWebExchange exchange) {
    rejectSql(request);
    rejectClientContext(request);
    RagClient client = exchange.getAttribute(ApiKeyClientFilter.RAG_CLIENT_ATTR);
    if (client != null) return apiKeyChat(client, request);
    Map<String, Object> normalized = agentRequest(request, exchange);
    return ai.post("/api/agent/decide", normalized)
      .flatMap(decision -> finishDecision(decision, normalized));
  }

  @GetMapping("/internal/admin/schema")
  Map<String, Object> adminSchema(@RequestParam(name = "client", defaultValue = "orbit") String client, ServerWebExchange exchange) {
    requireAdmin(identity(exchange));
    return catalogs.adminSchema(clientByName(client));
  }

  @PostMapping("/internal/admin/schema/refresh")
  Map<String, Object> refreshAdminSchema(@RequestParam(name = "client", defaultValue = "orbit") String client, ServerWebExchange exchange) {
    requireAdmin(identity(exchange));
    return catalogs.refreshAdminSchema(clientByName(client));
  }

  private Mono<Object> apiKeyChat(RagClient client, Map<String, Object> request) {
    String message = String.valueOf(request.getOrDefault("message", ""));
    SemanticCatalog catalog = catalogs.catalog(client);
    Map<String, Object> schema = new LinkedHashMap<>(catalogs.adminSchema(client));
    String schemaHash = String.valueOf(schema.getOrDefault("schema_hash", catalog.schemaHash()));
    schema.put("tenant_id", client.clientName());
    schema.put("project_id", client.clientName());
    schema.put("client_name", client.clientName());
    Map<String, Object> normalized = mutableCopy(request);
    normalized.putIfAbsent("conversation_id", "laravel-" + client.clientName());
    normalized.putIfAbsent("locale", "ar");
    normalized.putIfAbsent("conversation_history", List.of());
    normalized.putIfAbsent("tool_results", List.of());
    normalized.put("user_context", Map.of(
      "id", "api-key:" + client.clientName(),
      "tenant_id", client.clientName(),
      "project_ids", List.of(client.clientName()),
      "roles", List.of("laravel-client"),
      "permissions", List.of("live-data.read")
    ));
    normalized.put("allowed_schema", Map.of("tables", List.of()));
    normalized.put("semantic_catalog", Map.of("client_name", client.clientName(), "schema_hash", schemaHash));
    normalized.put("external_tools", List.of(Map.of("name", "database_query")));
    normalized.put("local_tools", List.of());
    normalized.put("rules", Map.of("return_sql", false, "max_tool_calls", 1, "max_rows", 20, "joins_allowed", false));
    return ai.post("/api/schema/ingest", schema)
      .then(ai.post("/api/agent/decide", normalized))
      .flatMap(decision -> finishApiKeyDecision(client, decision, normalized));
  }

  @ExceptionHandler(IllegalArgumentException.class)
  ResponseEntity<Map<String, String>> badRequest(IllegalArgumentException ex) { return ResponseEntity.badRequest().body(Map.of("error", ex.getMessage())); }

  @ExceptionHandler(ResponseStatusException.class)
  ResponseEntity<Map<String, Object>> downstream(ResponseStatusException ex, ServerWebExchange exchange) {
    HttpStatus status = HttpStatus.resolve(ex.getStatusCode().value());
    String requestId = exchange.getRequest().getId();
    String reason = safeDiagnostic(ex.getReason());
    log.warn("gateway_downstream_error request_id={} status={} diagnostic={}", requestId, ex.getStatusCode().value(), reason);
    return ResponseEntity.status(status == null ? HttpStatus.BAD_GATEWAY : status)
      .body(Map.of("error", "ai_module_request_failed", "request_id", requestId, "diagnostic", reason));
  }

  private Map<String, Object> agentRequest(Map<String, Object> request, ServerWebExchange exchange) {
    Map<String, Object> normalized = mutableCopy(request);
    normalized.put("user_context", identity(exchange).userContext());
    normalized.putIfAbsent("conversation_id", "public-chat");
    normalized.putIfAbsent("locale", "ar");
    normalized.putIfAbsent("conversation_history", List.of());
    normalized.putIfAbsent("tool_results", List.of());
    normalized.putIfAbsent("allowed_schema", Map.of("tables", List.of()));
    normalized.putIfAbsent("semantic_catalog", Map.of("client_name", identity(exchange).tenantId(), "schema_hash", "not-ingested"));
    normalized.putIfAbsent("external_tools", List.of(Map.of("name", "database_query")));
    normalized.putIfAbsent("local_tools", List.of(Map.of("name", "knowledge_search")));
    normalized.putIfAbsent("rules", Map.of("return_sql", false, "max_tool_calls", 3, "max_rows", 100, "joins_allowed", false));
    return normalized;
  }

  private Mono<Object> finishDecision(Object decision, Map<String, Object> normalized) {
    if (!(decision instanceof Map<?, ?> map)) return Mono.just(decision);
    Object type = map.get("type");
    if ("tool_calls".equals(type)) {
      Map<String, Object> finalRequest = new LinkedHashMap<>();
      finalRequest.put("conversation_id", normalized.get("conversation_id"));
      finalRequest.put("message", normalized.get("message"));
      finalRequest.put("locale", normalized.get("locale"));
      finalRequest.put("conversation_history", normalized.get("conversation_history"));
      finalRequest.put("tool_results", List.of());
      Object localRagResults = map.containsKey("local_rag_results") ? map.get("local_rag_results") : List.of();
      finalRequest.put("local_rag_results", localRagResults);
      finalRequest.put("final_answer_instruction", map.get("final_answer_instruction"));
      return ai.post("/api/agent/final", finalRequest);
    }
    return Mono.just(decision);
  }

  private Mono<Object> finishApiKeyDecision(RagClient client, Object decision, Map<String, Object> normalized) {
    if (!(decision instanceof Map<?, ?> map)) return Mono.just(decision);
    Object type = map.get("type");
    if (!"tool_calls".equals(type)) {
      log.info("api_key_chat route={} intent=ai_non_database selected_table=none operation=none reason=ai_decision_type client={}", type, client.clientName());
      return Mono.just(decision);
    }
    Object callsObject = map.get("tool_calls");
    if (!(callsObject instanceof List<?> calls) || calls.isEmpty()) throw new IllegalArgumentException("AI tool call is missing");
    Object first = calls.getFirst();
    if (!(first instanceof Map<?, ?> toolCall)) throw new IllegalArgumentException("AI tool call is malformed");
    if (!"database_query".equals(String.valueOf(toolCall.get("tool")))) throw new IllegalArgumentException("AI requested a non-allowlisted tool");
    Map<?, ?> plan = toolCall.get("plan") instanceof Map<?, ?> p ? p : Map.of();
    log.info("api_key_chat route=database_query intent=ai_structured selected_table={} operation={} reason=validated_tool_plan client={}",
      plan.get("table"), plan.get("operation"), client.clientName());
    return databaseQueries.execute(client, toolCall)
      .flatMap(result -> {
        Object toolCallId = toolCall.get("id");
        Map<String, Object> finalRequest = new LinkedHashMap<>();
        finalRequest.put("conversation_id", normalized.get("conversation_id"));
        finalRequest.put("message", normalized.get("message"));
        finalRequest.put("locale", normalized.get("locale"));
        finalRequest.put("conversation_history", normalized.get("conversation_history"));
        finalRequest.put("tool_results", List.of(Map.of(
          "tool_call_id", toolCallId == null ? "db_1" : String.valueOf(toolCallId),
          "tool", "database_query",
          "result", result
        )));
        finalRequest.put("local_rag_results", List.of());
        finalRequest.put("final_answer_instruction", map.get("final_answer_instruction"));
        return ai.post("/api/agent/final", finalRequest);
      })
      .onErrorResume(IllegalArgumentException.class, ex -> finalizeValidationError(normalized, map, toolCall, ex));
  }

  private Mono<Object> finalizeValidationError(Map<String, Object> normalized, Map<?, ?> decision, Map<?, ?> toolCall, IllegalArgumentException ex) {
    Object toolCallId = toolCall.get("id");
    Map<String, Object> validation = new LinkedHashMap<>();
    validation.put("operation", "validation_error");
    validation.put("error_code", "validation_error");
    validation.put("message", ex.getMessage());
    Object plan = toolCall.get("plan");
    if (plan instanceof Map<?, ?> planMap) {
      Object requestedTable = planMap.containsKey("table") ? planMap.get("table") : "";
      Object requestedOperation = planMap.containsKey("operation") ? planMap.get("operation") : "";
      validation.put("requested_table", String.valueOf(requestedTable));
      validation.put("operation_requested", String.valueOf(requestedOperation));
    }
    Map<String, Object> finalRequest = new LinkedHashMap<>();
    finalRequest.put("conversation_id", normalized.get("conversation_id"));
    finalRequest.put("message", normalized.get("message"));
    finalRequest.put("locale", normalized.get("locale"));
    finalRequest.put("conversation_history", normalized.get("conversation_history"));
    finalRequest.put("tool_results", List.of(Map.of(
      "tool_call_id", toolCallId == null ? "db_1" : String.valueOf(toolCallId),
      "tool", "database_query",
      "result", validation
    )));
    finalRequest.put("local_rag_results", List.of());
    finalRequest.put("final_answer_instruction", decision.get("final_answer_instruction"));
    log.info("api_key_chat route=database_query validation_error={} reason=returning_error_to_ai", ex.getMessage());
    return ai.post("/api/agent/final", finalRequest);
  }

  private TrustedIdentity identity(ServerWebExchange exchange) {
    TrustedIdentity identity = exchange.getAttribute(BearerTokenFilter.IDENTITY_ATTR);
    if (identity == null) throw new IllegalArgumentException("trusted identity is required");
    return identity;
  }

  private void requirePermission(TrustedIdentity identity, String permission) {
    if (!identity.permissions().contains(permission)) throw new IllegalArgumentException("required permission missing: " + permission);
  }

  private void requireAdmin(TrustedIdentity identity) {
    if (!identity.roles().contains("rag-admin") && !identity.permissions().contains("docs.admin")) {
      throw new IllegalArgumentException("admin role required");
    }
  }

  private RagClient clientByName(String clientName) {
    if (clients == null) throw new IllegalStateException("client registry is unavailable");
    return clients.findByClientName(clientName).filter(RagClient::active).orElseThrow(() -> new IllegalArgumentException("rag client not found"));
  }

  private String safeDiagnostic(String value) {
    if (value == null) return "";
    String safe = value
      .replaceAll("(?i)(bearer\\s+)[A-Za-z0-9._-]+", "$1[REDACTED]")
      .replaceAll("(?i)(token|password|secret|api_key|authorization)(\"?\\s*[:=]\\s*\"?)[^\"\\s,}]+", "$1$2[REDACTED]");
    return safe.length() > 500 ? safe.substring(0, 500) : safe;
  }

  private Map<String, Object> mutableCopy(Map<String, Object> request) {
    return new LinkedHashMap<>(request);
  }

  private void rejectClientContext(Object value) {
    if (value instanceof Map<?, ?> map) {
      for (Object key : map.keySet()) {
        if (FORBIDDEN_PUBLIC_CONTEXT_KEYS.contains(String.valueOf(key))) throw new IllegalArgumentException("client-supplied authorization context is not accepted");
      }
      for (Object child : map.values()) rejectClientContext(child);
    } else if (value instanceof List<?> list) {
      for (Object child : list) rejectClientContext(child);
    }
  }

  private void rejectSql(Object value) {
    String s = String.valueOf(value).toLowerCase();
    if (s.contains("raw_sql") || s.matches("(?s).*(select|insert|update|delete|drop|alter)\\s+.*")) {
      throw new IllegalArgumentException("raw SQL is not accepted by the gateway");
    }
  }
}
