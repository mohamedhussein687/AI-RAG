package com.construction.rag.gateway;

import java.nio.charset.StandardCharsets;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@Component
@Order(-110)
class ApiKeyClientFilter implements WebFilter {
  static final String RAG_CLIENT_ATTR = "ragClient";
  private final RagClientRegistry registry;

  ApiKeyClientFilter(RagClientRegistry registry) {
    this.registry = registry;
  }

  @Override
  public Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain) {
    String apiKey = exchange.getRequest().getHeaders().getFirst("X-API-Key");
    if (apiKey == null || apiKey.isBlank()) return chain.filter(exchange);
    if (!exchange.getRequest().getPath().value().equals("/api/chat")) {
      return reject(exchange, HttpStatus.UNAUTHORIZED, "api_key_not_allowed_for_endpoint");
    }
    return Mono.fromCallable(() -> registry.findByApiKey(apiKey))
      .flatMap(client -> {
        if (client.isEmpty() || !client.get().active()) return reject(exchange, HttpStatus.UNAUTHORIZED, "invalid_api_key");
        exchange.getAttributes().put(RAG_CLIENT_ATTR, client.get());
        return chain.filter(exchange);
      });
  }

  private Mono<Void> reject(ServerWebExchange exchange, HttpStatus status, String code) {
    exchange.getResponse().setStatusCode(status);
    byte[] bytes = ("{\"error\":\"" + code + "\"}").getBytes(StandardCharsets.UTF_8);
    return exchange.getResponse().writeWith(Mono.just(exchange.getResponse().bufferFactory().wrap(bytes)));
  }
}
