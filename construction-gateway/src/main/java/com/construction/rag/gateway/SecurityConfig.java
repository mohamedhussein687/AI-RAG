package com.construction.rag.gateway;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
@EnableConfigurationProperties(GatewayProperties.class)
class SecurityConfig {
  @Bean
  SecurityWebFilterChain security(ServerHttpSecurity http) {
    return http.csrf(ServerHttpSecurity.CsrfSpec::disable)
      .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
      .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
      .logout(ServerHttpSecurity.LogoutSpec::disable)
      .authorizeExchange(ex -> ex.anyExchange().permitAll())
      .build();
  }
}
