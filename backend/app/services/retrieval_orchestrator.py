"""
AskLaw Retrieval Orchestrator

Connects the Query Router with:

    RAG retrieval
    MCP web search
    Hybrid retrieval

For current/recent legal queries, the orchestrator performs
targeted multi-query web retrieval to improve the candidate pool.

Flow:

    User Query
        |
        v
    Query Router
        |
        +---- RAG ------> Local document retrieval
        |
        +---- WEB ------> Targeted web retrieval -> ranking
        |
        +---- HYBRID ---> RAG + targeted web retrieval
        |
        v
    Unified Retrieval Result
        |
        v
    Prompt Service / LLM
"""

from __future__ import annotations

import asyncio
import re
from datetime import date
from typing import Any

from app.services.query_router import (
    QueryRoute,
    route_query,
)

from app.services.retrieval_service import (
    retrieve_relevant_chunks,
)

from app.mcp.server import (
    search_web,
)

from app.services.web_source_ranker import (
    rank_web_sources,
)


# ============================================================
# QUERY SIGNALS
# ============================================================

CURRENT_PATTERNS = (
    r"\blatest\b",
    r"\brecent\b",
    r"\bcurrent\b",
    r"\btoday\b",
    r"\brecently\b",
    r"\bthis week\b",
    r"\bthis month\b",
    r"\bthis year\b",
    r"\bnew\b",
    r"\bupdated?\b",
    r"\brecent developments?\b",
    r"\blatest developments?\b",
)

LEGAL_EVENT_PATTERNS = (
    r"\bjudgment\b",
    r"\bjudgement\b",
    r"\bruling\b",
    r"\border\b",
    r"\bverdict\b",
    r"\bcase\b",
    r"\bcourt\b",
    r"\bsupreme court\b",
    r"\bhigh court\b",
    r"\bpetition\b",
    r"\bbench\b",
)


# ============================================================
# QUERY HELPERS
# ============================================================

def _wants_current_web_research(
    query: str,
) -> bool:
    """Return True when the query asks for current/recent information."""

    query_lower = query.lower()

    return any(
        re.search(
            pattern,
            query_lower,
        )
        for pattern in CURRENT_PATTERNS
    )


def _wants_current_legal_event(
    query: str,
) -> bool:
    """
    Return True when the query asks for current/recent legal
    information involving a legal event.
    """

    query_lower = query.lower()

    wants_current = _wants_current_web_research(
        query
    )

    wants_event = any(
        re.search(
            pattern,
            query_lower,
        )
        for pattern in LEGAL_EVENT_PATTERNS
    )

    return wants_current and wants_event


def _current_year() -> int:
    """Return the current calendar year."""

    return date.today().year


# ============================================================
# QUERY TOPIC EXTRACTION
# ============================================================

def _extract_legal_topic(
    query: str,
) -> str:
    """
    Extract the core topic from a natural-language current legal query.

    Example:

        "What is the latest Supreme Court judgment on privacy in India?"

    becomes approximately:

        "privacy"

    This is intentionally deterministic and conservative.
    """

    topic = query.lower().strip()

    # Remove common question openings.
    topic = re.sub(
        r"^\s*what\s+is\s+",
        "",
        topic,
    )

    topic = re.sub(
        r"^\s*what\s+are\s+",
        "",
        topic,
    )

    topic = re.sub(
        r"^\s*what\s+was\s+",
        "",
        topic,
    )

    topic = re.sub(
        r"^\s*which\s+",
        "",
        topic,
    )

    # Remove temporal wording.
    topic = re.sub(
        r"\bthe\s+latest\b",
        "",
        topic,
    )

    topic = re.sub(
        r"\blatest\b",
        "",
        topic,
    )

    topic = re.sub(
        r"\brecent\b",
        "",
        topic,
    )

    topic = re.sub(
        r"\bcurrent\b",
        "",
        topic,
    )

    topic = re.sub(
        r"\bnew\b",
        "",
        topic,
    )

    topic = re.sub(
        r"\brecently\b",
        "",
        topic,
    )

    # Remove legal-event wording.
    topic = re.sub(
        r"\bjudgments?\b",
        "",
        topic,
    )

    topic = re.sub(
        r"\bjudgements?\b",
        "",
        topic,
    )

    topic = re.sub(
        r"\brulings?\b",
        "",
        topic,
    )

    topic = re.sub(
        r"\borders?\b",
        "",
        topic,
    )

    topic = re.sub(
        r"\bverdicts?\b",
        "",
        topic,
    )

    # Remove court names.
    topic = re.sub(
        r"\bsupreme\s+court\b",
        "",
        topic,
    )

    topic = re.sub(
        r"\bhigh\s+court\b",
        "",
        topic,
    )

    topic = re.sub(
        r"\bcourt\b",
        "",
        topic,
    )

    # Remove geographical filler.
    topic = re.sub(
        r"\bin\s+india\b",
        "",
        topic,
    )

    topic = re.sub(
        r"\bof\s+india\b",
        "",
        topic,
    )

    # Remove common connective words.
    topic = re.sub(
        r"\bon\b",
        "",
        topic,
    )

    topic = re.sub(
        r"\bin\b",
        "",
        topic,
    )

    topic = re.sub(
        r"\bfor\b",
        "",
        topic,
    )

    topic = re.sub(
        r"\babout\b",
        "",
        topic,
    )

    topic = re.sub(
        r"\bregarding\b",
        "",
        topic,
    )

    topic = re.sub(
        r"\brelated\s+to\b",
        "",
        topic,
    )

    # Normalize whitespace.
    topic = re.sub(
        r"\s+",
        " ",
        topic,
    ).strip()

    # Remove punctuation at the edges.
    topic = topic.strip(
        " ?!.,:;()[]{}"
    )

    return topic


# ============================================================
# TARGETED WEB QUERY GENERATION
# ============================================================

def _build_targeted_web_queries(
    query: str,
) -> list[str]:
    """
    Build targeted web queries for current/recent legal research.

    The original user query is always preserved.

    For current/recent legal-event queries, additional focused
    queries are generated around the extracted legal topic.
    """

    base_query = query.strip()

    queries = [
        base_query
    ]

    if not _wants_current_legal_event(
        base_query
    ):
        return queries

    year = _current_year()

    topic = _extract_legal_topic(
        base_query
    )

    # --------------------------------------------------------
    # Fallback if topic extraction failed.
    # --------------------------------------------------------

    if not topic:
        topic = base_query

    # --------------------------------------------------------
    # Focused general searches.
    # --------------------------------------------------------

    queries.append(
        f"latest Supreme Court judgment "
        f"{topic} India {year}"
    )

    queries.append(
        f"Supreme Court {topic} ruling "
        f"India {year}"
    )

    queries.append(
        f"Supreme Court {topic} judgment "
        f"India {year}"
    )

    # --------------------------------------------------------
    # Primary-source searches.
    # --------------------------------------------------------

    queries.append(
        f"site:api.sci.gov.in "
        f"{topic} Supreme Court {year}"
    )

    queries.append(
        f"site:sci.gov.in "
        f"{topic} Supreme Court {year}"
    )

    # --------------------------------------------------------
    # Preserve order and remove duplicates.
    # --------------------------------------------------------

    seen: set[str] = set()
    unique_queries: list[str] = []

    for item in queries:

        normalized = re.sub(
            r"\s+",
            " ",
            item.strip().lower(),
        )

        if not normalized:
            continue

        if normalized in seen:
            continue

        seen.add(normalized)

        unique_queries.append(
            item.strip()
        )

    return unique_queries


# ============================================================
# RESULT NORMALIZATION
# ============================================================

def _normalize_rag_results(
    results: Any,
) -> list[dict]:
    """
    Normalize RAG retrieval output into a stable list format.
    """

    if results is None:
        return []

    if isinstance(
        results,
        list,
    ):
        normalized: list[dict] = []

        for item in results:

            if isinstance(
                item,
                dict,
            ):
                normalized.append(
                    item
                )

        return normalized

    return []


def _normalize_web_results(
    results: Any,
) -> list[dict]:
    """
    Normalize MCP/SearXNG output into a stable list format.
    """

    if not results:
        return []

    if isinstance(
        results,
        dict,
    ):

        raw_results = results.get(
            "results",
            [],
        )

        if not isinstance(
            raw_results,
            list,
        ):
            return []

        normalized: list[dict] = []

        for item in raw_results:

            if isinstance(
                item,
                dict,
            ):
                normalized.append(
                    dict(item)
                )

        return normalized

    if isinstance(
        results,
        list,
    ):
        return [
            dict(item)
            for item in results
            if isinstance(
                item,
                dict,
            )
        ]

    return []


# ============================================================
# WEB RESULT DEDUPLICATION
# ============================================================

def _deduplicate_web_results(
    results: list[dict],
) -> list[dict]:
    """Deduplicate web results by normalized URL."""

    seen: set[str] = set()
    deduplicated: list[dict] = []

    for result in results:

        url = (
            result.get("url") or ""
        ).strip().lower()

        if not url:
            continue

        if url in seen:
            continue

        seen.add(url)

        deduplicated.append(
            result
        )

    return deduplicated


# ============================================================
# RAG RETRIEVAL
# ============================================================

def retrieve_rag(
    query: str,
    document_id: str | None = None,
    limit: int = 5,
) -> list[dict]:
    """
    Retrieve relevant chunks from local legal documents.
    """

    results = retrieve_relevant_chunks(
        query=query,
        document_id=document_id,
        limit=limit,
    )

    return _normalize_rag_results(
        results
    )


# ============================================================
# WEB RETRIEVAL
# ============================================================

async def retrieve_web(
    query: str,
    limit: int = 5,
) -> list[dict]:
    """
    Retrieve and rank web sources.

    Normal query:
        one SearXNG search.

    Current/recent legal query:
        several targeted SearXNG searches in parallel.
    """

    targeted_queries = _build_targeted_web_queries(
        query
    )

    # --------------------------------------------------------
    # Request more candidates before ranking.
    # --------------------------------------------------------

    candidate_limit = max(
        limit * 3,
        10,
    )

    # --------------------------------------------------------
    # Search all queries in parallel.
    # --------------------------------------------------------

    search_tasks = [
        search_web(
            search_query,
            candidate_limit,
        )
        for search_query in targeted_queries
    ]

    search_results = await asyncio.gather(
        *search_tasks,
        return_exceptions=True,
    )

    # --------------------------------------------------------
    # Combine candidate results.
    # --------------------------------------------------------

    combined_candidates: list[dict] = []

    for search_result in search_results:

        if isinstance(
            search_result,
            Exception,
        ):
            print(
                "WEB SEARCH ERROR:",
                repr(search_result),
            )
            continue

        normalized = _normalize_web_results(
            search_result
        )

        combined_candidates.extend(
            normalized
        )

    # --------------------------------------------------------
    # Deduplicate.
    # --------------------------------------------------------

    deduplicated = _deduplicate_web_results(
        combined_candidates
    )

    # --------------------------------------------------------
    # Debug output.
    # --------------------------------------------------------

    print(
        f"WEB TARGETED QUERIES: "
        f"{len(targeted_queries)}"
    )

    for index, search_query in enumerate(
        targeted_queries,
        start=1,
    ):
        print(
            f"[WEB QUERY #{index}] "
            f"{search_query}"
        )

    print(
        f"WEB CANDIDATES: "
        f"{len(deduplicated)}"
    )

    # --------------------------------------------------------
    # Rank.
    # --------------------------------------------------------

    ranked = rank_web_sources(
        query=query,
        results=deduplicated,
        limit=limit,
    )

    print(
        f"WEB RANKED RESULTS: "
        f"{len(ranked)}"
    )

    for index, item in enumerate(
        ranked,
        start=1,
    ):
        ranking = item.get(
            "ranking",
            {},
        )

        date_metadata = item.get(
            "date_metadata",
            {},
        )

        source_metadata = item.get(
            "source_metadata",
            {},
        )

        print(
            f"[WEB #{index}] "
            f"{item.get('title', '')} "
            f"| score="
            f"{ranking.get('final_score')} "
            f"| authority="
            f"{ranking.get('authority_score')} "
            f"| relevance="
            f"{ranking.get('relevance_score')} "
            f"| freshness="
            f"{ranking.get('freshness_score')} "
            f"| event="
            f"{ranking.get('legal_event_score')} "
            f"| type="
            f"{source_metadata.get('source_type')} "
            f"| date="
            f"{date_metadata.get('date')}"
        )

    return ranked


# ============================================================
# MAIN ASYNC ORCHESTRATOR
# ============================================================

async def retrieve_for_query(
    query: str,
    document_id: str | None = None,
    rag_limit: int = 5,
    web_limit: int = 5,
) -> dict:
    """
    Route the query and retrieve appropriate evidence.

    Returns:

        {
            "route": "rag" | "web" | "hybrid",
            "rag_results": [...],
            "web_results": [...]
        }
    """

    route = route_query(
        query
    )

    route_value = (
        route.value
        if isinstance(
            route,
            QueryRoute,
        )
        else str(route)
    )

    print(
        "\n"
        + "=" * 60
    )

    print(
        "ASKLAW RETRIEVAL ORCHESTRATOR"
    )

    print(
        "=" * 60
    )

    print(
        "QUERY:",
        query,
    )

    print(
        "ROUTE:",
        route_value,
    )

    print(
        "=" * 60
    )

    # ========================================================
    # RAG
    # ========================================================

    if route_value == "rag":

        rag_results = await asyncio.to_thread(
            retrieve_rag,
            query,
            document_id,
            rag_limit,
        )

        print(
            f"RAG RESULTS: "
            f"{len(rag_results)}"
        )

        return {
            "route": "rag",
            "rag_results": rag_results,
            "web_results": [],
        }

    # ========================================================
    # WEB
    # ========================================================

    if route_value == "web":

        web_results = await retrieve_web(
            query,
            web_limit,
        )

        print(
            f"WEB RESULTS: "
            f"{len(web_results)}"
        )

        return {
            "route": "web",
            "rag_results": [],
            "web_results": web_results,
        }

    # ========================================================
    # HYBRID
    # ========================================================

    if route_value == "hybrid":

        rag_task = asyncio.to_thread(
            retrieve_rag,
            query,
            document_id,
            rag_limit,
        )

        web_task = retrieve_web(
            query,
            web_limit,
        )

        rag_results, web_results = (
            await asyncio.gather(
                rag_task,
                web_task,
            )
        )

        print(
            f"RAG RESULTS: "
            f"{len(rag_results)}"
        )

        print(
            f"WEB RESULTS: "
            f"{len(web_results)}"
        )

        return {
            "route": "hybrid",
            "rag_results": rag_results,
            "web_results": web_results,
        }

    # ========================================================
    # FALLBACK
    # ========================================================

    rag_results = await asyncio.to_thread(
        retrieve_rag,
        query,
        document_id,
        rag_limit,
    )

    return {
        "route": "rag",
        "rag_results": rag_results,
        "web_results": [],
    }


# ============================================================
# SYNC HELPER
# ============================================================

def retrieve_for_query_sync(
    query: str,
    document_id: str | None = None,
    rag_limit: int = 5,
    web_limit: int = 5,
) -> dict:
    """
    Synchronous wrapper for callers that cannot await.
    """

    return asyncio.run(
        retrieve_for_query(
            query=query,
            document_id=document_id,
            rag_limit=rag_limit,
            web_limit=web_limit,
        )
    )