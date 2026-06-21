# Construction RAG Gateway

The Spring Boot gateway is the public API boundary for the RAG deployment.

## Authentication

All protected public endpoints require a valid OIDC access token. The gateway validates:

- issuer: `GATEWAY_JWT_ISSUER`
- JWK set: `GATEWAY_JWT_JWK_SET_URI`
- audience: `GATEWAY_JWT_AUDIENCE`
- required trusted claims: `tenant_id`, `project_ids`, `roles`, `permissions`

Tenant, project, role, permission, and administrator context is derived only from the validated JWT. Requests containing client-supplied authorization context fields such as `tenant_id`, `project_ids`, `roles`, `permissions`, `admin`, or `is_admin` are rejected.

## Public Chat Contract

The documented public chat endpoint is:

```http
POST /api/chat
Authorization: Bearer <access-token>
Content-Type: application/json
```

Required request field:

```json
{
  "message": "ما هي سياسة الخوذة في الموقع؟"
}
```

Optional fields are user-facing conversation fields only, such as `conversation_id`, `locale`, and `conversation_history`.

The gateway injects trusted JWT context and calls the private FastAPI AI module with the internal service token. FastAPI remains private and continues to reject public user JWTs.

`/api/agent/decide` is exposed by the gateway for compatibility with the AI-module contract, but it is still authenticated with the user JWT at the gateway and forwarded internally with the service token. Public clients should prefer `/api/chat`.
