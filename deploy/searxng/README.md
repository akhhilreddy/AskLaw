# AskLaw SearXNG on Render Free

This directory contains the standalone SearXNG service used by AskLaw's web
research path. It does not change the existing FastAPI, Celery, MCP, or RAG
deployment.

## Create the Render Web Service

In the Render dashboard, create a new **Web Service** with these settings:

| Setting | Value |
| --- | --- |
| Repository | `AskLaw` |
| Branch | `deployment` |
| Runtime | `Docker` |
| Dockerfile path | `deploy/searxng/Dockerfile` |
| Docker build context | `.` |
| Instance type | `Free` |
| Port | `10000` |
| Health check path | `/healthz` |

Leave the repository root directory unset so the Docker build context remains
the repository root. No custom build or start command is required; the pinned
official SearXNG image supplies the container entrypoint.

## Environment variables

Configure these variables on the SearXNG Render service:

| Variable | Required value |
| --- | --- |
| `SEARXNG_SECRET` | A strong, unique secret stored only in Render |
| `SEARXNG_BASE_URL` | `https://<searxng-service-name>.onrender.com/` |
| `SEARXNG_PORT` | `10000` |
| `SEARXNG_BIND_ADDRESS` | `0.0.0.0` |

Generate `SEARXNG_SECRET` locally with a cryptographically secure generator,
for example `openssl rand -hex 32`, and paste the generated value directly
into Render. Never add it to this repository or application logs.

The limiter remains disabled. Do not enable it unless a supported Valkey
service and its required SearXNG configuration are deployed as well.

## Verify the deployment

After Render reports the service healthy, its public URL will be:

```text
https://<searxng-service-name>.onrender.com
```

The exact JSON API test is:

```http
GET /search?q=India&format=json
```

For example:

```bash
curl --fail --show-error \
  "https://<searxng-service-name>.onrender.com/search?q=India&format=json"
```

A successful response has HTTP status `200` and a JSON body containing a
`results` array. The health check is available at:

```text
https://<searxng-service-name>.onrender.com/healthz
```

Once this standalone service is verified, the existing AskLaw API service can
be configured in a separate deployment step to use:

```text
SEARXNG_URL=https://<searxng-service-name>.onrender.com/search
```

That API configuration change is intentionally outside this deployment-only
task.
