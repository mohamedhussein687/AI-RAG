# Keycloak Auth Stack

This directory contains the reusable production Keycloak deployment assets for
`modelauth.techlabeg.com`.

The deployed stack is separate from the GPU RAG stack:

- Compose project: `construction-rag-auth`
- Public hostname: `https://modelauth.techlabeg.com`
- Internal upstream: `http://127.0.0.1:8180`
- Realm: `techlab`
- API audience: `construction-rag-api`

Secrets are generated on the server under
`/home/rag/.config/construction-rag/keycloak.env` and
`/home/rag/.config/construction-rag/keycloak-smoke.env`. They are never stored
in Git.

Operational commands:

```bash
sudo /home/rag/bin/keycloak-status.sh
sudo /home/rag/bin/keycloak-restart.sh
sudo /home/rag/bin/keycloak-backup.sh
sudo /home/rag/bin/keycloak-admin-allow-ip.sh <IP_ADDRESS>
```
