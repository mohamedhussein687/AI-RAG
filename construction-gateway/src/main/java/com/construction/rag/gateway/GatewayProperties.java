package com.construction.rag.gateway;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "gateway")
public record GatewayProperties(String aiBaseUrl, String aiToken, String publicToken, long timeoutMs) {}
