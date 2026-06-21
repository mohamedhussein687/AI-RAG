package com.construction.rag.gateway;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.InetAddress;
import java.time.Instant;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

class GatewayAuthenticationTest {
  private static final ObjectMapper JSON = new ObjectMapper();
  private static final String ISSUER = "https://issuer.example.test/realms/techlab";
  private static final String AUDIENCE = "construction-rag-api";

  @Test
  void wrongAudienceIsRejectedBeforeController() {
    MockServerWebExchange exchange = exchangeWithBearer("token");
    BearerTokenFilter filter = filter(jwt(List.of("other-api"), ISSUER, "smoke-tenant"));

    filter.filter(exchange, e -> Mono.error(new AssertionError("controller should not run"))).block();

    assertThat(exchange.getResponse().getStatusCode()).isEqualTo(HttpStatus.UNAUTHORIZED);
  }

  @Test
  void wrongIssuerIsRejectedBeforeController() {
    MockServerWebExchange exchange = exchangeWithBearer("token");
    BearerTokenFilter filter = filter(jwt(List.of(AUDIENCE), "https://issuer.example.test/realms/other", "smoke-tenant"));

    filter.filter(exchange, e -> Mono.error(new AssertionError("controller should not run"))).block();

    assertThat(exchange.getResponse().getStatusCode()).isEqualTo(HttpStatus.UNAUTHORIZED);
  }

  @Test
  void missingTenantIsRejected() {
    MockServerWebExchange exchange = exchangeWithBearer("token");
    BearerTokenFilter filter = filter(jwt(List.of(AUDIENCE), ISSUER, ""));

    filter.filter(exchange, e -> Mono.error(new AssertionError("controller should not run"))).block();

    assertThat(exchange.getResponse().getStatusCode()).isEqualTo(HttpStatus.FORBIDDEN);
  }

  @Test
  void expiredTokenIsRejected() {
    MockServerWebExchange exchange = exchangeWithBearer("token");
    BearerTokenFilter filter = filter(jwt(validClaims(), Instant.now().minusSeconds(600), Instant.now().minusSeconds(60)));

    filter.filter(exchange, e -> Mono.error(new AssertionError("controller should not run"))).block();

    assertThat(exchange.getResponse().getStatusCode()).isEqualTo(HttpStatus.UNAUTHORIZED);
  }

  @Test
  void missingProjectMembershipIsRejected() {
    Map<String, Object> claims = validClaims();
    claims.remove("project_ids");
    MockServerWebExchange exchange = exchangeWithBearer("token");
    BearerTokenFilter filter = filter(jwt(claims));

    filter.filter(exchange, e -> Mono.error(new AssertionError("controller should not run"))).block();

    assertThat(exchange.getResponse().getStatusCode()).isEqualTo(HttpStatus.FORBIDDEN);
  }

  @Test
  void missingPermissionsAreRejected() {
    Map<String, Object> claims = validClaims();
    claims.remove("permissions");
    MockServerWebExchange exchange = exchangeWithBearer("token");
    BearerTokenFilter filter = filter(jwt(claims));

    filter.filter(exchange, e -> Mono.error(new AssertionError("controller should not run"))).block();

    assertThat(exchange.getResponse().getStatusCode()).isEqualTo(HttpStatus.FORBIDDEN);
  }

  @Test
  void validTokenStoresTrustedIdentity() {
    MockServerWebExchange exchange = exchangeWithBearer("token");
    BearerTokenFilter filter = filter(jwt(List.of(AUDIENCE), ISSUER, "smoke-tenant"));

    filter.filter(exchange, e -> {
      TrustedIdentity identity = e.getAttribute(BearerTokenFilter.IDENTITY_ATTR);
      assertThat(identity.tenantId()).isEqualTo("smoke-tenant");
      assertThat(identity.projectIds()).containsExactly("smoke-project");
      assertThat(identity.permissions()).contains("docs.view");
      return Mono.empty();
    }).block();

    assertThat(exchange.getResponse().getStatusCode()).isNull();
  }

  @Test
  void agentDecideUsesInternalAiTokenAndTrustedContext() throws Exception {
    try (MockWebServer ai = new MockWebServer()) {
      ai.enqueue(new MockResponse().setHeader("Content-Type", "application/json").setBody("{\"type\":\"clarification\",\"question\":\"هل يمكنك التوضيح؟\"}"));
      ai.start(InetAddress.getByName("127.0.0.1"), 0);
      GatewayProperties props = new GatewayProperties(ai.url("/").toString(), "internal-ai-token", "", 5000, ISSUER, "http://127.0.0.1/jwks", AUDIENCE);
      RagGatewayController controller = new RagGatewayController(new AiModuleClient(WebClient.builder(), props));
      ServerWebExchange exchange = MockServerWebExchange.from(MockServerHttpRequest.post("/api/agent/decide").build());
      exchange.getAttributes().put(BearerTokenFilter.IDENTITY_ATTR, identity());

      Object response = controller.decide(Map.of("conversation_id", "test", "message", "مرحبا"), exchange).block();
      RecordedRequest request = ai.takeRequest(2, TimeUnit.SECONDS);

      assertThat(response).isInstanceOf(Map.class);
      assertThat(request).isNotNull();
      assertThat(request.getPath()).isEqualTo("/api/agent/decide");
      assertThat(request.getHeader(HttpHeaders.AUTHORIZATION)).isEqualTo("Bearer internal-ai-token");
      JsonNode body = JSON.readTree(request.getBody().readUtf8());
      assertThat(body.get("user_context").get("tenant_id").asText()).isEqualTo("smoke-tenant");
      assertThat(body.has("external_tools")).isTrue();
      assertThat(body.has("local_tools")).isTrue();
    }
  }

  @Test
  void forgedRequestBodyContextIsRejectedByController() {
    RagGatewayController controller = new RagGatewayController(null);
    ServerWebExchange exchange = MockServerWebExchange.from(MockServerHttpRequest.post("/api/rag/search").build());
    exchange.getAttributes().put(BearerTokenFilter.IDENTITY_ATTR, identity());

    try {
      controller.search(Map.of("query", "السلامة", "tenant_id", "forged"), exchange);
    } catch (IllegalArgumentException ex) {
      assertThat(ex.getMessage()).isEqualTo("client-supplied authorization context is not accepted");
      return;
    }
    throw new AssertionError("forged context was accepted");
  }

  private static BearerTokenFilter filter(Jwt jwt) {
    GatewayProperties props = new GatewayProperties("http://ai", "internal", "", 1000, ISSUER, "http://jwks", AUDIENCE);
    ReactiveJwtDecoder decoder = token -> Mono.just(jwt);
    return new BearerTokenFilter(props, decoder);
  }

  private static MockServerWebExchange exchangeWithBearer(String token) {
    return MockServerWebExchange.from(MockServerHttpRequest.post("/api/rag/search").header(HttpHeaders.AUTHORIZATION, "Bearer " + token).build());
  }

  private static Jwt jwt(List<String> audience, String issuer, String tenant) {
    Map<String, Object> claims = validClaims();
    claims.put("iss", issuer);
    claims.put("aud", audience);
    claims.put("tenant_id", tenant);
    return jwt(claims);
  }

  private static Jwt jwt(Map<String, Object> claims) {
    return jwt(claims, Instant.now().minusSeconds(1), Instant.now().plusSeconds(300));
  }

  private static Jwt jwt(Map<String, Object> claims, Instant issuedAt, Instant expiresAt) {
    return new Jwt("token", issuedAt, expiresAt, Map.of("alg", "RS256"), claims);
  }

  private static Map<String, Object> validClaims() {
    return new HashMap<>(Map.of(
      "iss", ISSUER,
      "sub", "smoke-client",
      "aud", List.of(AUDIENCE),
      "tenant_id", "smoke-tenant",
      "project_ids", List.of("smoke-project"),
      "roles", List.of("rag-user"),
      "permissions", List.of("docs.admin", "docs.view", "policies.view")
    ));
  }

  private static TrustedIdentity identity() {
    return new TrustedIdentity("smoke-client", "smoke-tenant", List.of("smoke-project"), List.of("rag-user"), List.of("docs.admin", "docs.view", "policies.view"));
  }
}
