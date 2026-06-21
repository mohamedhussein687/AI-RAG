package com.construction.rag.gateway;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import java.util.Map;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;
import reactor.core.publisher.Mono;

@RestController
@Validated
class RagGatewayController {
  private final AiModuleClient ai;
  RagGatewayController(AiModuleClient ai) { this.ai = ai; }

  @GetMapping("/health/live") Map<String, String> live() { return Map.of("status", "ok"); }
  @GetMapping("/health/ready") Mono<Object> ready() { return ai.get("/health/ready"); }

  @PostMapping("/api/agent/decide")
  Mono<Object> decide(@Valid @RequestBody Map<String, Object> request) {
    rejectSql(request);
    return ai.post("/api/agent/decide", withServerContext(request));
  }

  @PostMapping("/api/agent/final")
  Mono<Object> finalAnswer(@Valid @RequestBody Map<String, Object> request) {
    rejectSql(request);
    return ai.post("/api/agent/final", request);
  }

  @PostMapping("/api/rag/documents")
  Mono<Object> indexDocument(@Valid @RequestBody Map<String, Object> request) { return ai.post("/api/rag/documents", request); }

  @PostMapping("/api/rag/search")
  Mono<Object> search(@Valid @RequestBody Map<String, Object> request) {
    rejectSql(request);
    return ai.post("/api/rag/search", withServerContext(request));
  }

  @ExceptionHandler(IllegalArgumentException.class)
  ResponseEntity<Map<String, String>> badRequest(IllegalArgumentException ex) { return ResponseEntity.badRequest().body(Map.of("error", ex.getMessage())); }

  private Map<String, Object> withServerContext(Map<String, Object> request) {
    // Production integration point: derive tenant/project/permissions from authenticated application context.
    return request;
  }

  private void rejectSql(Object value) {
    String s = String.valueOf(value).toLowerCase();
    if (s.contains("raw_sql") || s.matches("(?s).*(select|insert|update|delete|drop|alter)\\s+.*")) {
      throw new IllegalArgumentException("raw SQL is not accepted by the gateway");
    }
  }
}
