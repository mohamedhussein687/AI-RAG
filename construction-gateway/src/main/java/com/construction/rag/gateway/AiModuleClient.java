package com.construction.rag.gateway;

import java.time.Duration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatusCode;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

@Component
class AiModuleClient {
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
          .map(message -> new ResponseStatusException(response.statusCode(), message)))
      .bodyToMono(Object.class)
      .timeout(Duration.ofMillis(Math.max(props.timeoutMs(), 1000)));
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
