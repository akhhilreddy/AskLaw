FROM searxng/searxng:2026.9.23-3cd69d30e

COPY deploy/searxng/settings.yml /etc/searxng/settings.yml

ENV SEARXNG_PORT=10000 \
    SEARXNG_BIND_ADDRESS=0.0.0.0

EXPOSE 10000
