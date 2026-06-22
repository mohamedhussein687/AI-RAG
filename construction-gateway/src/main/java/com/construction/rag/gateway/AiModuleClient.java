package com.construction.rag.gateway;

import java.time.Duration;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatusCode;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

@Component
class AiModuleClient {
  private static final Logger log = LoggerFactory.getLogger(AiModuleClient.class);
  private final WebClient webClient;
  private final GatewayProperties props;

  AiModuleClient(WebClient.Builder builder, GatewayProperties props) {
    this.props = props;
    this.webClient = builder.baseUrl(props.aiBaseUrl()).build();
  }

  Mono<Object> post(String path, Object body) {
    return webClient.post().uri(path)
      .header(HttpHeaders.AUTHORIZATION, "Bearer " + props.aiToken())
      .bodyValue(body)
      .retrieve()
      .onStatus(HttpStatusCode::isError, response ->
        response.bodyToMono(String.class)
          .defaultIfEmpty("AI module request failed")
          .map(message -> {
            String safe = safeBody(message);
            log.warn("ai_module_request_failed route={} status={} body={}", path, response.statusCode().value(), safe);
            return new ResponseStatusException(response.statusCode(), "route=" + path + " ai_status=" + response.statusCode().value() + " body=" + safe);
          }))
      .bodyToMono(Object.class)
      .timeout(Duration.ofMillis(Math.max(props.timeoutMs(), 1000)));
  }

  private static String safeBody(String body) {
    if (body == null) return "";
    String safe = body
      .replaceAll("(?i)(bearer\\s+)[A-Za-z0-9._-]+", "$1[REDACTED]")
      .replaceAll("(?i)(token|password|secret|api_key|authorization)(\"?\\s*[:=]\\s*\"?)[^\"\\s,}]+", "$1$2[REDACTED]");
    return safe.length() > 1000 ? safe.substring(0, 1000) : safe;
  }

  Mono<Object> get(String path) {
    return webClient.get().uri(path)
      .retrieve()
      .onStatus(HttpStatusCode::isError, response ->
        response.bodyToMono(String.class)
          .defaultIfEmpty("AI module request failed")
          .map(message -> new ResponseStatusException(response.statusCode(), message)))
      .bodyToMono(Object.class)
      .timeout(Duration.ofMillis(5000));
  }
}
