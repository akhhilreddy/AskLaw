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
import logging
import re
from datetime import date
from typing import Any

logger = logging.getLogger(__name__)

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

RECENT_DEVELOPMENT_PATTERNS = (
    r"\brecent developments?\b",
    r"\blatest developments?\b",
    r"\brecent legal developments?\b",
    r"\blatest legal developments?\b",
    r"\bnew legal developments?\b",
    r"\brecent changes?\b",
    r"\blatest changes?\b",
    r"\brecent legal changes?\b",
    r"\blatest legal changes?\b",
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


def _wants_recent_legal_developments(
    query: str,
) -> bool:
    """
    Return True when the query explicitly asks for recent/latest
    developments or changes in a legal topic.

    This is separate from `_wants_current_legal_event` because a
    development query may not contain words such as judgment,
    ruling, order, or case.
    """

    query_lower = query.lower()

    return any(
        re.search(
            pattern,
            query_lower,
        )
        for pattern in RECENT_DEVELOPMENT_PATTERNS
    )


def _extract_article_reference(
    query: str,
) -> str | None:
    """
    Extract an Article reference such as:

        Article 32
        article 226

    Returns the article number as a string when present.
    """

    match = re.search(
        r"\barticle\s+(\d+[A-Za-z]?)\b",
        query,
        flags=re.IGNORECASE,
    )

    if not match:
        return None

    return match.group(1)


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

        What is the latest Supreme Court judgment on privacy in India?

    becomes approximately:

        privacy
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

    # Remove legal event wording.
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

    # Remove geography/filler.
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

    Special handling exists for:
        1. latest/recent judgments, rulings, and orders
        2. recent/latest legal developments or changes
        3. Article-specific recent-development questions

    The goal is to search for legal events and primary material,
    rather than merely recent educational content.
    """

    base_query = query.strip()

    queries = [
        base_query
    ]

    wants_current_event = _wants_current_legal_event(
        base_query
    )

    wants_recent_developments = _wants_recent_legal_developments(
        base_query
    )

    if not (
        wants_current_event
        or wants_recent_developments
    ):
        return queries

    year = _current_year()

    article_number = _extract_article_reference(
        base_query
    )

    topic = _extract_legal_topic(
        base_query
    )

    # ========================================================
    # ARTICLE-SPECIFIC CURRENT RESEARCH
    # ========================================================

    if article_number:

        article_queries = [
            (
                f"Article {article_number} "
                f"Supreme Court recent judgment India {year}"
            ),
            (
                f"Article {article_number} "
                f"Supreme Court recent order India {year}"
            ),
            (
                f"Article {article_number} "
                f"recent constitutional development India {year}"
            ),
            (
                f'site:api.sci.gov.in '
                f'"Article {article_number}" {year}'
            ),
            (
                f'site:sci.gov.in '
                f'"Article {article_number}" {year}'
            ),
        ]

        # For an explicit latest-judgment request, add a tighter
        # judgment-focused query.
        if _wants_current_legal_event(base_query):

            article_queries.insert(
                0,
                (
                    f"latest Supreme Court judgment "
                    f"Article {article_number} India {year}"
                ),
            )

        queries.extend(
            article_queries
        )

    # ========================================================
    # TOPIC-BASED CURRENT LEGAL RESEARCH
    # ========================================================

    else:

        if not topic:
            topic = base_query

        if _wants_current_legal_event(base_query):

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

        if wants_recent_developments:

            queries.append(
                f"Supreme Court recent legal developments "
                f"{topic} India {year}"
            )

            queries.append(
                f"Supreme Court recent cases "
                f"{topic} India {year}"
            )

            queries.append(
                f"Supreme Court recent orders "
                f"{topic} India {year}"
            )

        queries.append(
            f"site:api.sci.gov.in "
            f"{topic} Supreme Court {year}"
        )

        queries.append(
            f"site:sci.gov.in "
            f"{topic} Supreme Court {year}"
        )

    # ========================================================
    # LEGAL-REPORTING FALLBACKS FOR DEVELOPMENT QUERIES
    # ========================================================

    if wants_recent_developments:

        if article_number:

            queries.append(
                (
                    f'site:livelaw.in '
                    f'"Article {article_number}" '
                    f'Supreme Court {year}'
                )
            )

            queries.append(
                (
                    f'site:barandbench.com '
                    f'"Article {article_number}" '
                    f'Supreme Court {year}'
                )
            )

        elif topic:

            queries.append(
                (
                    f'site:livelaw.in '
                    f'{topic} Supreme Court {year}'
                )
            )

            queries.append(
                (
                    f'site:barandbench.com '
                    f'{topic} Supreme Court {year}'
                )
            )

    # ========================================================
    # PRESERVE ORDER + DEDUPLICATE
    # ========================================================

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
    """Normalize RAG retrieval output."""

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
    """Normalize MCP/SearXNG output."""

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
    """Deduplicate web results by URL."""

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
    user_id: str,
    document_id: str | None = None,
    limit: int = 5,
) -> list[dict]:
    """
    Retrieve relevant local-document chunks.

    When document_id is supplied, retrieval remains user-scoped
    and is additionally limited to that document.
    """

    results = retrieve_relevant_chunks(
        query=query,
        user_id=user_id,
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

    candidate_limit = max(
        limit * 3,
        10,
    )

    # Run all web searches in parallel.
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

    # Combine candidates.
    combined_candidates: list[dict] = []

    for search_result in search_results:

        if isinstance(
            search_result,
            Exception,
        ):
            logger.warning("A targeted web search failed: %s", type(search_result).__name__)
            continue

        normalized = _normalize_web_results(
            search_result
        )

        combined_candidates.extend(
            normalized
        )

    # Deduplicate.
    deduplicated = _deduplicate_web_results(
        combined_candidates
    )

    # Rank.
    ranked = rank_web_sources(
        query=query,
        results=deduplicated,
        limit=limit,
    )

    logger.info(
        "Web retrieval completed targeted_queries=%s candidates=%s results=%s",
        len(targeted_queries),
        len(deduplicated),
        len(ranked),
    )

    return ranked


# ============================================================
# MAIN ASYNC ORCHESTRATOR
# ============================================================

async def retrieve_for_query(
    query: str,
    user_id: str,
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

    # ========================================================
    # RAG
    # ========================================================

    if route_value == "rag":

        rag_results = await asyncio.to_thread(
            retrieve_rag,
            query,
            user_id,
            document_id,
            rag_limit,
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
            user_id,
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
        user_id,
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
    user_id: str,
    document_id: str | None = None,
    rag_limit: int = 5,
    web_limit: int = 5,
) -> dict:
    """Synchronous wrapper for callers that cannot await."""

    return asyncio.run(
        retrieve_for_query(
            query=query,
            user_id=user_id,
            document_id=document_id,
            rag_limit=rag_limit,
            web_limit=web_limit,
        )
    )
