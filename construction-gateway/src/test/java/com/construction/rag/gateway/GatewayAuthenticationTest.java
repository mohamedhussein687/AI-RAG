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
import org.mockito.ArgumentCaptor;
import org.mockito.Mockito;
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
      GatewayProperties props = props(ai.url("/").toString(), "internal-ai-token");
      RagGatewayController controller = new RagGatewayController(new AiModuleClient(WebClient.builder(), props), null);
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
    RagGatewayController controller = new RagGatewayController(null, null);
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

  @Test
  void apiKeyChatExecutesStructuredDatabasePlanAndFinalizesAnswer() throws Exception {
    try (MockWebServer ai = new MockWebServer()) {
      ai.enqueue(new MockResponse().setHeader("Content-Type", "application/json").setBody("""
        {"type":"tool_calls","tool_calls":[{"id":"db_1","tool":"database_query","plan":{"operation":"count","table":"projects","filters":[{"column":"status","operator":"eq","value":"waiting"}],"limit":100}}],"local_rag_results":[],"final_answer_instruction":"Answer in Arabic."}
        """));
      ai.enqueue(new MockResponse().setHeader("Content-Type", "application/json").setBody("""
        {"answer":"عدد المشاريع waiting هو 4.","display":{"type":"metric","data":{"tool_results":[{"count":4}],"citations_valid":true}},"sources":[]}
        """));
      ai.start(InetAddress.getByName("127.0.0.1"), 0);
      GatewayProperties props = props(ai.url("/").toString(), "internal-ai-token");
      SafeDatabaseQueryService db = Mockito.mock(SafeDatabaseQueryService.class);
      Mockito.when(db.execute(Mockito.any(), Mockito.any())).thenReturn(Mono.just(Map.of("count", 4)));
      RagGatewayController controller = new RagGatewayController(new AiModuleClient(WebClient.builder(), props), db);
      ServerWebExchange exchange = MockServerWebExchange.from(MockServerHttpRequest.post("/api/chat").header("X-API-Key", "redacted").build());
      exchange.getAttributes().put(ApiKeyClientFilter.RAG_CLIENT_ATTR, new RagClient(7, "orbit", "mysql", "db", 3306, "orbit", "user", "encrypted", "active"));

      Object response = controller.chat(Map.of("message", "كم مشروع waiting؟"), exchange).block();
      RecordedRequest decide = ai.takeRequest(2, TimeUnit.SECONDS);
      RecordedRequest finalAnswer = ai.takeRequest(2, TimeUnit.SECONDS);

      assertThat(response).isInstanceOf(Map.class);
      assertThat(decide.getPath()).isEqualTo("/api/agent/decide");
      JsonNode decideBody = JSON.readTree(decide.getBody().readUtf8());
      assertThat(decideBody.get("external_tools").get(0).get("name").asText()).isEqualTo("database_query");
      assertThat(decideBody.get("allowed_schema").get("tables").get(0).get("name").asText()).isEqualTo("projects");
      assertThat(finalAnswer.getPath()).isEqualTo("/api/agent/final");
      JsonNode finalBody = JSON.readTree(finalAnswer.getBody().readUtf8());
      assertThat(finalBody.get("tool_results").get(0).get("result").get("count").asInt()).isEqualTo(4);
      ArgumentCaptor<Map> planCaptor = ArgumentCaptor.forClass(Map.class);
      Mockito.verify(db).execute(Mockito.argThat(client -> client.clientName().equals("orbit")), planCaptor.capture());
      assertThat(((Map<?, ?>) planCaptor.getValue().get("plan")).get("table")).isEqualTo("projects");
    }
  }

  private static BearerTokenFilter filter(Jwt jwt) {
    GatewayProperties props = props("http://ai", "internal");
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

  private static GatewayProperties props(String aiBaseUrl, String aiToken) {
    return new GatewayProperties(aiBaseUrl, aiToken, "", 5000, ISSUER, "http://jwks", AUDIENCE, "", "", "mysql", "", 3306, "", "", "");
  }
}
