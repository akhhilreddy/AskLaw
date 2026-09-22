import logging

import httpx
from mcp.server.mcpserver import MCPServer

from app.core.config import settings


logger = logging.getLogger(__name__)

server = MCPServer(
    name="AskLaw MCP",
    version="1.0.0",
)


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
        async with httpx.AsyncClient(timeout=15.0) as client:

            response = await client.get(
                url,
                params=params,
            )

            response.raise_for_status()

            data = response.json()

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

    import asyncio

    asyncio.run(
        server.run_streamable_http_async(
            host=settings.MCP_HOST,
            port=settings.MCP_PORT,
            streamable_http_path="/mcp",
        )
    )
