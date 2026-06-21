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

## Laravel API-Key Integration

Laravel backends may call the same public chat endpoint with an API key instead of a user JWT:

```http
POST /api/chat
X-API-Key: <client-api-key>
Content-Type: application/json
```

```json
{
  "message": "كم مشروع waiting؟"
}
```

The gateway resolves `X-API-Key` to a row in `rag_clients`, injects a server-side client context, asks the AI module for a structured `database_query` plan, validates that plan against the gateway allowlist, executes only a parameterized read-only query against the resolved client database, then sends the result to `/api/agent/final`.

The API-key flow does not require Keycloak, but it is limited to `/api/chat`. API keys and client DB passwords are never stored in plaintext:

- `api_key_hash`: SHA-256 hash of the client API key
- `db_password_encrypted`: AES-GCM encrypted with `GATEWAY_CLIENT_DB_ENCRYPTION_KEY`

Required protected environment for client seeding:

```text
GATEWAY_CLIENT_DB_ENCRYPTION_KEY=<base64 32-byte key>
ORBIT_API_KEY=<not committed>
ORBIT_DB_TYPE=mysql
ORBIT_DB_HOST=<orbit-db-host>
ORBIT_DB_PORT=3306
ORBIT_DB_NAME=<orbit-db-name>
ORBIT_DB_USERNAME=<orbit-db-readonly-user>
ORBIT_DB_PASSWORD=<not committed>
```

If the `ORBIT_*` values are absent, the gateway creates the `rag_clients` table but does not seed a fake client.
