# AskLaw production container foundation

This directory contains secret-free configuration for the production Compose
stack. It does not deploy to OCI and it does not contain a usable production
environment file.

## Architecture

`compose.production.yml` builds two application images:

- one Python 3.12.11 backend image shared by FastAPI, Celery, and MCP;
- one Node 22.23.2 build followed by a Caddy 2.11.4 static runtime for the
  frontend and HTTPS reverse proxy.

Only Caddy publishes host ports 80 and 443. The API is reachable through its
configured Caddy hostname. MongoDB, Redis, Qdrant, SearXNG, Celery, and MCP are
attached only to the private Compose network and publish no host ports.

Separate frontend and API hostnames preserve the existing unprefixed FastAPI
routes without colliding with SPA routes such as `/documents`. For local stack
testing the defaults are `http://localhost` and `http://api.localhost`. A real
deployment should use sibling hostnames such as `app.example.com` and
`api.example.com`, then rebuild the frontend with that API URL.

## Configuration

Copy `production.env.example` to a secure, untracked location. Generate new
values for `SECRET_KEY` and `SEARXNG_SECRET`; configure the real Groq key and
origins there. The checked-in example values are deliberately unusable.

Validate the resolved Compose model without starting services:

```bash
docker compose \
  --env-file /secure/path/asklaw-production.env \
  -f compose.production.yml config --quiet
```

`VITE_API_BASE_URL` is a Vite build-time value. Rebuild the frontend image when
the API hostname changes.

## Runtime decisions

- FastAPI uses one Uvicorn worker initially because each process loads the
  embedding model. Scale only after measuring memory and streaming load.
- Celery uses Linux `prefork`, concurrency 1, and recycles a child after 25
  tasks. This is conservative for a small ARM VM and avoids the macOS-only
  development `solo` choice.
- The backend image downloads `all-MiniLM-L6-v2` during image construction and
  runs with Hugging Face offline mode enabled. Runtime restarts therefore do
  not depend on an external model download.
- The normal requirements remain cross-platform for local development. Linux
  containers constrain Torch 2.13.0 to the official `+cpu` wheel because the
  default ARM64 PyPI wheel also resolves large CUDA 13 dependencies that an OCI
  Always Free CPU VM cannot use.
- Redis uses AOF with `everysec` syncing and `noeviction` so queued indexing
  work is not intentionally evicted under memory pressure.
- Docker JSON logs rotate at 10 MiB with three files per service.
- MongoDB, Redis, Qdrant, SearXNG cache, and Caddy certificate/configuration
  state use named volumes. `docker compose down` preserves them; never use
  `down --volumes` against production.

## Local development compatibility

The original `docker-compose.yml`, `start.sh`, and `stop.sh` remain the local
development workflow. Its MongoDB and Qdrant defaults are now portable named
volumes. Existing bind-mounted data is not moved or deleted: set the existing
`ASKLAW_MONGODB_DATA` and `ASKLAW_QDRANT_DATA` values to continue using it.
