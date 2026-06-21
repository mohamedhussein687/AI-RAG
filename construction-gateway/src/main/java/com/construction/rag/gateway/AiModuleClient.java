package com.construction.rag.gateway;

import java.time.Duration;
import org.springframework.http.HttpHeaders;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;
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
      .retrieve().bodyToMono(Object.class)
      .timeout(Duration.ofMillis(Math.max(props.timeoutMs(), 1000)));
  }

  Mono<Object> get(String path) {
    return webClient.get().uri(path).retrieve().bodyToMono(Object.class).timeout(Duration.ofMillis(5000));
  }
}
