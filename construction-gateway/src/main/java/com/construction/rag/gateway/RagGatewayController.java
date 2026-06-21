package com.construction.rag.gateway;

import jakarta.validation.Valid;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@RestController
@Validated
class RagGatewayController {
  private static final Set<String> FORBIDDEN_PUBLIC_CONTEXT_KEYS = Set.of(
    "user_context", "userContext", "tenant_id", "tenantId", "project_id", "projectId", "project_ids", "projectIds",
    "roles", "permissions", "admin", "isAdmin", "allowed_schema", "allowedSchema", "database_scope", "databaseScope"
  );

  private final AiModuleClient ai;
  RagGatewayController(AiModuleClient ai) { this.ai = ai; }

  @GetMapping("/health/live") Map<String, String> live() { return Map.of("status", "ok"); }
  @GetMapping("/health/ready") Mono<Object> ready() { return ai.get("/health/ready"); }

  @PostMapping("/api/agent/decide")
  Mono<Object> decide(@Valid @RequestBody Map<String, Object> request, ServerWebExchange exchange) {
    rejectSql(request);
    rejectClientContext(request);
    Map<String, Object> normalized = mutableCopy(request);
    normalized.put("user_context", identity(exchange).userContext());
    normalized.putIfAbsent("allowed_schema", Map.of("tables", List.of()));
    return ai.post("/api/agent/decide", normalized);
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

  @ExceptionHandler(IllegalArgumentException.class)
  ResponseEntity<Map<String, String>> badRequest(IllegalArgumentException ex) { return ResponseEntity.badRequest().body(Map.of("error", ex.getMessage())); }

  private TrustedIdentity identity(ServerWebExchange exchange) {
    TrustedIdentity identity = exchange.getAttribute(BearerTokenFilter.IDENTITY_ATTR);
    if (identity == null) throw new IllegalArgumentException("trusted identity is required");
    return identity;
  }

  private void requirePermission(TrustedIdentity identity, String permission) {
    if (!identity.permissions().contains(permission)) throw new IllegalArgumentException("required permission missing: " + permission);
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
