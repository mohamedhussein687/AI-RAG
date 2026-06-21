package com.construction.rag.gateway;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "gateway")
public record GatewayProperties(
    String aiBaseUrl,
    String aiToken,
    String publicToken,
    long timeoutMs,
    String jwtIssuer,
    String jwtJwkSetUri,
    String jwtAudience,
    String clientDbEncryptionKey,
    String orbitApiKey,
    String orbitDbType,
    String orbitDbHost,
    Integer orbitDbPort,
    String orbitDbName,
    String orbitDbUsername,
    String orbitDbPassword
) {}
