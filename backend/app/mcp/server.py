import asyncio
import logging

import httpx
from mcp.server.mcpserver import MCPServer

from app.core.config import settings


logger = logging.getLogger(__name__)

SEARXNG_REQUEST_TIMEOUT_SECONDS = 30.0
SEARXNG_MAX_ATTEMPTS = 3
SEARXNG_RETRY_DELAYS_SECONDS = (5.0, 15.0)
SEARXNG_TRANSIENT_STATUS_CODES = {502, 503, 504}

server = MCPServer(
    name="AskLaw MCP",
    version="1.0.0",
)


def _is_transient_search_error(exc: Exception) -> bool:
    if isinstance(exc, httpx.TransportError):
        return True

    return (
        isinstance(exc, httpx.HTTPStatusError)
        and exc.response.status_code in SEARXNG_TRANSIENT_STATUS_CODES
    )


async def _request_search(client: httpx.AsyncClient, url: str, params: dict) -> dict:
    for attempt in range(SEARXNG_MAX_ATTEMPTS):
        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            can_retry = (
                _is_transient_search_error(exc)
                and attempt < SEARXNG_MAX_ATTEMPTS - 1
            )
            if not can_retry:
                raise

            delay = SEARXNG_RETRY_DELAYS_SECONDS[attempt]
            logger.warning(
                "SearXNG request temporarily unavailable; retrying "
                "attempt=%s/%s delay_seconds=%s error=%s",
                attempt + 1,
                SEARXNG_MAX_ATTEMPTS,
                delay,
                type(exc).__name__,
            )
            await asyncio.sleep(delay)


@server.tool()
async def search_web(query: str, limit: int = 5) -> dict:
    """
    Search the web through the local AskLaw SearXNG instance.

    Args:
        query: Search query.
        limit: Maximum number of results.

    Returns:
        Structured search results.
    """

    url = settings.SEARXNG_URL

    params = {
        "q": query,
        "format": "json",
    }

    try:
        async with httpx.AsyncClient(
            timeout=SEARXNG_REQUEST_TIMEOUT_SECONDS,
        ) as client:
            data = await _request_search(client, url, params)

        results = []

        for item in data.get("results", [])[:limit]:

            results.append(
                {
                    "title": item.get(
                        "title",
                        "",
                    ),
                    "url": item.get(
                        "url",
                        "",
                    ),
                    "content": item.get(
                        "content",
                        "",
                    ),
                    "engine": item.get(
                        "engine",
                        "",
                    ),
                }
            )

        return {
            "query": query,
            "results": results,
            "count": len(results),
        }

    except Exception as exc:
        logger.warning("SearXNG request failed: %s", type(exc).__name__)

        return {
            "query": query,
            "results": [],
            "count": 0,
            "error": "Web search is temporarily unavailable",
        }


if __name__ == "__main__":

    print("=" * 60)
    print("ASKLAW MCP SERVER")
    print("=" * 60)
    print("Starting MCP server...")
    print(f"URL: http://{settings.MCP_HOST}:{settings.MCP_PORT}/mcp")
    print("=" * 60)

    asyncio.run(
        server.run_streamable_http_async(
            host=settings.MCP_HOST,
            port=settings.MCP_PORT,
            streamable_http_path="/mcp",
        )
    )
