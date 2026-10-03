"""Source-backed lookup for short, non-current definition questions."""

import logging
import re

import httpx


logger = logging.getLogger(__name__)

WIKIPEDIA_API_URL = "https://en.wikipedia.org/w/api.php"
WIKIPEDIA_USER_AGENT = "AskLaw/1.0 (https://github.com/akhhilreddy/AskLaw)"
DEFINITION_PATTERN = re.compile(
    r"^\s*what\s+(?:is|are)\s+(?:(?:a|an|the)\s+)?(.+?)\s*\??\s*$",
    re.IGNORECASE,
)
CURRENT_TERMS = re.compile(
    r"\b(?:latest|recent|current|today|newest|updated?)\b",
    re.IGNORECASE,
)


def definition_subject(query: str) -> str | None:
    """Extract only simple definitions; current research keeps normal search."""

    if CURRENT_TERMS.search(query):
        return None

    match = DEFINITION_PATTERN.fullmatch(query)
    if not match:
        return None

    subject = match.group(1).strip(" ?.!,:;")
    return subject if 2 <= len(subject) <= 120 else None


async def search_wikipedia_definition(subject: str) -> dict | None:
    """Get a short, attributed page introduction from Wikimedia's API."""

    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": subject,
        "gsrlimit": 1,
        "prop": "extracts",
        "exintro": 1,
        "explaintext": 1,
        "exchars": 1000,
        "format": "json",
        "formatversion": 2,
    }

    try:
        async with httpx.AsyncClient(
            timeout=15.0,
            headers={"User-Agent": WIKIPEDIA_USER_AGENT},
        ) as client:
            response = await client.get(WIKIPEDIA_API_URL, params=params)
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError):
        logger.warning("Wikipedia definition lookup failed")
        return None

    if not isinstance(data, dict):
        return None

    query_data = data.get("query", {})
    if not isinstance(query_data, dict):
        return None

    pages = query_data.get("pages", [])
    if not isinstance(pages, list) or not pages:
        return None

    page = pages[0]
    if not isinstance(page, dict):
        return None

    page_id = page.get("pageid")
    title = page.get("title")
    extract = page.get("extract")
    if (
        not isinstance(page_id, int)
        or page_id <= 0
        or not isinstance(title, str)
        or not isinstance(extract, str)
        or not extract.strip()
        or title.lower().endswith("(disambiguation)")
    ):
        return None

    return {
        "title": f"Wikipedia: {title}",
        "url": f"https://en.wikipedia.org/?curid={page_id}",
        "content": extract.strip()[:1000],
        "engine": "wikipedia",
    }
