# AskLaw SearXNG on Render Free

This directory deploys the standalone SearXNG service used by AskLaw's WEB
and HYBRID research routes. It does not replace or modify the existing AskLaw
FastAPI/Celery service.

The service is public because Render Free does not provide a private service
for this deployment. It is intended only for a portfolio demo. Debugging,
metrics, the public-instance mode, and the SearXNG limiter are disabled. The
limiter must not be enabled without also deploying its required Valkey setup.

## A. Create the Render Web Service

In the Render dashboard, select **New**, then **Web Service**, connect GitHub,
and use these exact values:

| Render field | Exact value |
| --- | --- |
| Service type | `Web Service` |
| Repository | `https://github.com/akhhilreddy/AskLaw` |
| Name | `asklaw-searxng` |
| Branch | `deployment` |
| Region | `Singapore` (the same region as `asklaw-api`) |
| Root Directory | Leave blank |
| Language | `Docker` |
| Dockerfile Path | `deploy/searxng/Dockerfile` |
| Docker Build Context | `.` |
| Build Command | Leave blank / unavailable for Docker |
| Docker Command / Start Command | Leave blank |
| Plan | `Free` |
| Port | `10000` |
| Health Check Path | `/healthz` |
| Auto Deploy | `On` |

Leaving the Docker command blank preserves the official pinned image's
entrypoint and command. That runtime starts Granian and reads
`SEARXNG_PORT=10000` and `SEARXNG_BIND_ADDRESS=0.0.0.0` from the image. Do not
invent a separate shell start command and do not use Docker Compose for this
Render service.

`/healthz` is the image's lightweight application health endpoint. It returns
HTTP `200` without running an external search, so upstream search-engine
availability cannot make Render mark the container itself unhealthy.

## B. Configure the SearXNG environment

Add these variables to the new SearXNG service before its first deployment:

| Variable | Value |
| --- | --- |
| `SEARXNG_SECRET` | A strong, unique value stored only in Render |
| `SEARXNG_BASE_URL` | `https://asklaw-searxng.onrender.com/` |
| `SEARXNG_PORT` | `10000` |
| `SEARXNG_BIND_ADDRESS` | `0.0.0.0` |

If Render assigns a different hostname, replace the example base URL with the
exact assigned URL and retain its final `/`.

Generate the secret locally with a cryptographically secure generator such as
`openssl rand -hex 32`, then paste it directly into Render. Never add the value
to Git, `.env` files, screenshots, application logs, or chat messages.

No database, persistent disk, Redis, or Valkey service is required for this
SearXNG deployment.

## C. Verify the first deployment

Wait until Render reports the service as **Live**. Its public URL has this
format:

```text
https://<service-name>.onrender.com
```

For the current service, verify the lightweight health endpoint:

```bash
curl --fail --show-error --include \
  "https://asklaw-searxng.onrender.com/healthz"
```

Then verify the JSON search API separately:

```bash
curl --fail --show-error --include \
  "https://asklaw-searxng.onrender.com/search?q=India&format=json"
```

Success means HTTP `200`, `Content-Type: application/json`, and a JSON body
whose `results` array contains search results. The exact endpoint consumed by
AskLaw is `/search`; the AskLaw client adds `q` and `format=json` as query
parameters.

## D. Connect the existing AskLaw API

Open the existing `asklaw-api` Render Web Service, select **Environment**, and
set the existing variable to exactly:

```text
SEARXNG_URL=https://asklaw-searxng.onrender.com/search
```

The `/search` path is required. Do not use only the site root:

```text
SEARXNG_URL=https://asklaw-searxng.onrender.com
```

The root URL returns an HTTP `308` redirect, while AskLaw deliberately treats
non-success search responses as unavailable instead of relying on redirects.
The configured value must not include `?q=`, `format=json`, a trailing slash,
or credentials.

Select **Save and deploy**. This restarts the existing API/Celery container
with the corrected runtime environment; it does not require a frontend
deployment or changes to MongoDB, Qdrant, Redis, Gemini, Groq, or authentication.

After the deploy, confirm the AskLaw API remains healthy:

```bash
curl --fail --show-error --include \
  "https://asklaw-api.onrender.com/health"
```

## E. End-to-end verification

Sign in to AskLaw and ask:

```text
What is the latest Supreme Court judgment on privacy?
```

The API logs should show a successful SearXNG request to `/search`, nonzero
web candidates, route `web`, and web source metadata in the response. It must
not show an HTTP `308` from the SearXNG request.

Also verify:

- `What does Article 32 provide?` continues to use RAG.
- `What are the latest developments about Article 32?` continues to use
  HYBRID retrieval.
- `hello` remains conversational and returns no research evidence metadata.

Render Free services may need time to wake after inactivity. If the first
end-to-end query fails, call `/healthz`, repeat the direct JSON search test,
and then retry AskLaw.
