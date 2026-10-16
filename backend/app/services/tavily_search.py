"""Hosted search adapter; returns the same evidence shape as SearXNG."""
import asyncio
import logging

import httpx

from app.core.config import settings
from app.services.availability import SearchResponse
from app.services.research_runtime import remaining_seconds

logger = logging.getLogger(__name__)
TAVILY_SEARCH_URL = "https://api.tavily.com/search"


def _unavailable(query):
    return SearchResponse({"query": query, "results": [], "count": 0,
                           "error": "Web search is temporarily unavailable"}, unavailable=True)


async def search_tavily(query: str, limit: int = 5) -> dict:
    key = settings.TAVILY_API_KEY.strip()
    if not key:
        logger.warning("Hosted web search unavailable status=not_configured")
        return _unavailable(query)
    budget = min(settings.TAVILY_TIMEOUT_SECONDS, remaining_seconds())
    if budget <= 0:
        return _unavailable(query)
    try:
        # Basic depth and auto_parameters=False prevent automatic paid-depth
        # upgrades. No automatic retries: an uncertain POST may consume credit.
        async with asyncio.timeout(budget):
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(budget, connect=min(5, budget)),
                follow_redirects=False,
            ) as client:
                response = await client.post(
                    TAVILY_SEARCH_URL,
                    headers={"Authorization": "Bearer " + key},
                    json={"query": query, "search_depth": "basic",
                          "auto_parameters": False, "topic": "general",
                          "max_results": max(1, min(limit, 20)),
                          "include_answer": False, "include_raw_content": False,
                          "include_images": False},
                )
                response.raise_for_status()
                data = response.json()
                if not isinstance(data, dict) or not isinstance(data.get("results"), list):
                    raise ValueError("Invalid search response")
                results = []
                for item in data["results"][:max(1, min(limit, 20))]:
                    if not isinstance(item, dict):
                        continue
                    if not all(isinstance(item.get(field), str) for field in ("title", "url", "content")):
                        continue
                    if not item["url"].startswith(("https://", "http://")):
                        continue
                    result = {field: item[field] for field in ("title", "url", "content")}
                    result["engine"] = "tavily"
                    if isinstance(item.get("published_date"), str):
                        result["published_date"] = item["published_date"]
                    results.append(result)
                return SearchResponse({"query": query, "results": results, "count": len(results)})
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code
        status = "quota_or_rate_limit" if code in {429, 432, 433} else "authentication" if code in {401, 403} else "http_error"
    except (TimeoutError, httpx.TimeoutException):
        status = "timeout"
    except httpx.HTTPError:
        status = "connection_error"
    except (ValueError, TypeError):
        status = "invalid_response"
    logger.warning("Hosted web search unavailable status=%s", status)
    return _unavailable(query)
