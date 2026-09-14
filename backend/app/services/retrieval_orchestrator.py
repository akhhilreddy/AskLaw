"""
AskLaw Retrieval Orchestrator

Connects the Query Router with:

    RAG retrieval
    MCP web search
    Hybrid retrieval

The orchestrator does NOT generate the final answer.
It only gathers the appropriate source material.

Flow:

    User Query
        |
        v
    Query Router
        |
        +---- RAG ------> Local document retrieval
        |
        +---- WEB ------> MCP -> SearXNG -> Web Source Ranking
        |
        +---- HYBRID ---> RAG + MCP -> Web Source Ranking
        |
        v
    Unified Retrieval Result
        |
        v
    Prompt Service / LLM
"""

from __future__ import annotations

import asyncio
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
# DEFAULTS
# ============================================================

DEFAULT_RAG_LIMIT = 5
DEFAULT_WEB_LIMIT = 5

# Ask SearXNG/MCP for more candidates than we finally return.
# The ranking layer needs a larger candidate pool to choose from.
WEB_CANDIDATE_MULTIPLIER = 3
MIN_WEB_CANDIDATES = 10


# ============================================================
# NORMALIZE RAG RESULTS
# ============================================================

def _normalize_rag_results(
    chunks: list[Any],
) -> list[dict]:

    normalized = []

    for chunk in chunks:

        if not isinstance(chunk, dict):
            continue

        normalized.append(
            {
                "type": "document",
                "filename": chunk.get(
                    "filename"
                ),
                "page_number": chunk.get(
                    "page_number"
                ),
                "chunk_index": chunk.get(
                    "chunk_index"
                ),
                "text": chunk.get(
                    "text",
                    "",
                ),
            }
        )

    return normalized


# ============================================================
# NORMALIZE WEB RESULTS
# ============================================================

def _normalize_web_results(
    result: dict,
) -> list[dict]:

    if not isinstance(result, dict):
        return []

    results = result.get(
        "results",
        [],
    )

    normalized = []

    for item in results:

        if not isinstance(item, dict):
            continue

        normalized.append(
            {
                "type": "web",
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

    return normalized


# ============================================================
# RAG RETRIEVAL
# ============================================================

def retrieve_rag(
    query: str,
    document_id: str,
    limit: int = DEFAULT_RAG_LIMIT,
) -> list[dict]:

    if not document_id:
        return []

    chunks = retrieve_relevant_chunks(
        query,
        document_id,
        limit=limit,
    )

    return _normalize_rag_results(
        chunks
    )


# ============================================================
# WEB RETRIEVAL
# ============================================================

async def retrieve_web(
    query: str,
    limit: int = DEFAULT_WEB_LIMIT,
) -> list[dict]:
    """
    Retrieve web candidates through MCP/SearXNG,
    then rank them before returning the final sources.

    Flow:

        MCP/SearXNG
            ↓
        Candidate results
            ↓
        Normalize
            ↓
        Rank
            ↓
        Top results
    """

    # --------------------------------------------------------
    # Get a larger candidate pool than the final result count.
    # --------------------------------------------------------

    candidate_limit = max(
        limit * WEB_CANDIDATE_MULTIPLIER,
        MIN_WEB_CANDIDATES,
    )

    result = await search_web(
        query,
        candidate_limit,
    )

    # --------------------------------------------------------
    # Normalize raw MCP/SearXNG results.
    # --------------------------------------------------------

    normalized = _normalize_web_results(
        result
    )

    print(
        f"WEB CANDIDATES: {len(normalized)}"
    )

    # --------------------------------------------------------
    # Rank the candidates.
    # --------------------------------------------------------

    ranked = rank_web_sources(
        query=query,
        results=normalized,
        limit=limit,
    )

    print(
        f"WEB RANKED RESULTS: {len(ranked)}"
    )

    # --------------------------------------------------------
    # Debug ranking information.
    # --------------------------------------------------------

    for index, item in enumerate(
        ranked,
        start=1,
    ):

        ranking = item.get(
            "ranking",
            {},
        )

        print(
            f"[WEB #{index}] "
            f"{item.get('title', '')} | "
            f"score={ranking.get('final_score', 0)} | "
            f"authority={ranking.get('authority_score', 0)} | "
            f"relevance={ranking.get('relevance_score', 0)}"
        )

    return ranked


# ============================================================
# MAIN ORCHESTRATOR
# ============================================================

async def retrieve_for_query(
    query: str,
    document_id: str | None = None,
    rag_limit: int = DEFAULT_RAG_LIMIT,
    web_limit: int = DEFAULT_WEB_LIMIT,
) -> dict:

    # -----------------------------------------------------
    # DETERMINE ROUTE
    # -----------------------------------------------------

    route = route_query(
        query
    )

    print()
    print("=" * 60)
    print("ASKLAW RETRIEVAL ORCHESTRATOR")
    print("=" * 60)
    print(f"QUERY: {query}")
    print(f"ROUTE: {route.value}")
    print("=" * 60)

    # -----------------------------------------------------
    # RAG
    # -----------------------------------------------------

    if route == QueryRoute.RAG:

        rag_results = retrieve_rag(
            query=query,
            document_id=document_id,
            limit=rag_limit,
        )

        print(
            f"RAG RESULTS: {len(rag_results)}"
        )

        return {
            "query": query,
            "route": route.value,
            "rag_results": rag_results,
            "web_results": [],
        }

    # -----------------------------------------------------
    # WEB
    # -----------------------------------------------------

    if route == QueryRoute.WEB:

        web_results = await retrieve_web(
            query=query,
            limit=web_limit,
        )

        print(
            f"WEB RESULTS: {len(web_results)}"
        )

        return {
            "query": query,
            "route": route.value,
            "rag_results": [],
            "web_results": web_results,
        }

    # -----------------------------------------------------
    # HYBRID
    # -----------------------------------------------------

    if route == QueryRoute.HYBRID:

        # Run both retrieval operations concurrently.

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
            f"RAG RESULTS: {len(rag_results)}"
        )

        print(
            f"WEB RESULTS: {len(web_results)}"
        )

        return {
            "query": query,
            "route": route.value,
            "rag_results": rag_results,
            "web_results": web_results,
        }

    # -----------------------------------------------------
    # SAFETY FALLBACK
    # -----------------------------------------------------

    return {
        "query": query,
        "route": QueryRoute.RAG.value,
        "rag_results": [],
        "web_results": [],
    }


# ============================================================
# SYNCHRONOUS HELPER
# ============================================================

def retrieve_for_query_sync(
    query: str,
    document_id: str | None = None,
    rag_limit: int = DEFAULT_RAG_LIMIT,
    web_limit: int = DEFAULT_WEB_LIMIT,
) -> dict:

    return asyncio.run(
        retrieve_for_query(
            query=query,
            document_id=document_id,
            rag_limit=rag_limit,
            web_limit=web_limit,
        )
    )