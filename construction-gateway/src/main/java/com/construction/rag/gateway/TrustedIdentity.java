package com.construction.rag.gateway;

import java.util.List;
import java.util.Map;

record TrustedIdentity(String userId, String tenantId, List<String> projectIds, List<String> roles, List<String> permissions) {
  Map<String, Object> userContext() {
    return Map.of(
      "id", userId,
      "tenant_id", tenantId,
      "project_ids", projectIds,
      "roles", roles,
      "permissions", permissions
    );
  }
}
