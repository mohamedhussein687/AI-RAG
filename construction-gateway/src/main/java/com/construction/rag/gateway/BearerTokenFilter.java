package com.construction.rag.gateway;

import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@Component
@Order(-100)
class BearerTokenFilter implements WebFilter {
  private static final Logger log = LoggerFactory.getLogger(BearerTokenFilter.class);
  static final String IDENTITY_ATTR = "trustedIdentity";
  private final GatewayProperties props;
  private final ReactiveJwtDecoder decoder;

  BearerTokenFilter(GatewayProperties props) {
    this.props = props;
    this.decoder = configured(props) ? NimbusReactiveJwtDecoder.withJwkSetUri(props.jwtJwkSetUri()).build() : null;
  }

  BearerTokenFilter(GatewayProperties props, ReactiveJwtDecoder decoder) {
    this.props = props;
    this.decoder = decoder;
  }

  @Override
  public Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain) {
    String path = exchange.getRequest().getPath().value();
    if (path.startsWith("/health/") || path.equals("/actuator/health") || path.equals("/actuator/health/liveness") || path.equals("/actuator/health/readiness")) return chain.filter(exchange);
    if (decoder == null) return reject(exchange, HttpStatus.SERVICE_UNAVAILABLE, "identity_provider_not_configured");
    String header = exchange.getRequest().getHeaders().getFirst(HttpHeaders.AUTHORIZATION);
    if (header == null || !header.startsWith("Bearer ")) return reject(exchange, HttpStatus.UNAUTHORIZED, "missing_bearer_token");
    return decoder.decode(header.substring(7)).onErrorMap(InvalidBearerToken::new)
      .flatMap(jwt -> validate(jwt, exchange, chain))
      .onErrorResume(InvalidBearerToken.class, ex -> reject(exchange, HttpStatus.UNAUTHORIZED, "invalid_bearer_token"));
  }

  private Mono<Void> validate(Jwt jwt, ServerWebExchange exchange, WebFilterChain chain) {
    if (!Objects.equals(jwt.getIssuer() == null ? null : jwt.getIssuer().toString(), props.jwtIssuer())) return reject(exchange, HttpStatus.UNAUTHORIZED, "wrong_issuer");
    if (jwt.getExpiresAt() == null || jwt.getExpiresAt().isBefore(Instant.now())) return reject(exchange, HttpStatus.UNAUTHORIZED, "expired_token");
    if (props.jwtAudience() != null && !props.jwtAudience().isBlank() && !jwt.getAudience().contains(props.jwtAudience())) return reject(exchange, HttpStatus.UNAUTHORIZED, "wrong_audience");
    String tenantId = stringClaim(jwt, "tenant_id");
    if (tenantId == null || tenantId.isBlank()) return reject(exchange, HttpStatus.FORBIDDEN, "tenant_membership_required");
    TrustedIdentity identity = new TrustedIdentity(
      jwt.getSubject(),
      tenantId,
      listClaim(jwt, "project_ids"),
      listClaim(jwt, "roles"),
      listClaim(jwt, "permissions")
    );
    exchange.getAttributes().put(IDENTITY_ATTR, identity);
    return chain.filter(exchange);
  }

  private static boolean configured(GatewayProperties props) {
    return props.jwtIssuer() != null && !props.jwtIssuer().isBlank()
      && props.jwtJwkSetUri() != null && !props.jwtJwkSetUri().isBlank();
  }

  private static String stringClaim(Jwt jwt, String name) {
    Object value = jwt.getClaims().get(name);
    return value == null ? null : String.valueOf(value);
  }

  private static List<String> listClaim(Jwt jwt, String name) {
    Object value = jwt.getClaims().get(name);
    if (value instanceof List<?> list) {
      List<String> out = new ArrayList<>();
      for (Object item : list) out.add(String.valueOf(item));
      return List.copyOf(out);
    }
    if (value instanceof String s && !s.isBlank()) return List.of(s.split(","));
    return List.of();
  }

  private Mono<Void> reject(ServerWebExchange exchange, HttpStatus status, String code) {
    exchange.getResponse().setStatusCode(status);
    byte[] bytes = ("{\"error\":\"" + code + "\"}").getBytes(StandardCharsets.UTF_8);
    return exchange.getResponse().writeWith(Mono.just(exchange.getResponse().bufferFactory().wrap(bytes)));
  }

  private static class InvalidBearerToken extends RuntimeException {
    InvalidBearerToken(Throwable cause) {
      super(cause);
      log.warn("JWT decode failed: {}", cause.toString());
    }
  }
}
