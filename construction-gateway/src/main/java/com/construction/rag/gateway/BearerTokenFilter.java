package com.construction.rag.gateway;

import java.nio.charset.StandardCharsets;
import java.util.Objects;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@Component
@Order(-100)
class BearerTokenFilter implements WebFilter {
  private final GatewayProperties props;
  BearerTokenFilter(GatewayProperties props) { this.props = props; }

  @Override
  public Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain) {
    String path = exchange.getRequest().getPath().value();
    if (path.startsWith("/health/") || path.startsWith("/actuator/health")) return chain.filter(exchange);
    String configured = props.publicToken();
    String header = exchange.getRequest().getHeaders().getFirst(HttpHeaders.AUTHORIZATION);
    boolean ok = configured != null && !configured.isBlank() && header != null && header.startsWith("Bearer ") && Objects.equals(header.substring(7), configured);
    if (ok) return chain.filter(exchange);
    exchange.getResponse().setStatusCode(HttpStatus.UNAUTHORIZED);
    byte[] bytes = "{\"error\":\"unauthorized\"}".getBytes(StandardCharsets.UTF_8);
    return exchange.getResponse().writeWith(Mono.just(exchange.getResponse().bufferFactory().wrap(bytes)));
  }
}
