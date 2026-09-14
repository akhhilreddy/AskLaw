"""
AskLaw Query Router

Determines whether a user query should use:

    rag     -> uploaded/local documents
    web     -> MCP/SearXNG web search
    hybrid  -> both RAG and web search

The router does NOT answer the question.
It only determines the retrieval strategy.
"""

import re
from enum import Enum


# ============================================================
# ROUTE TYPES
# ============================================================

class QueryRoute(str, Enum):
    RAG = "rag"
    WEB = "web"
    HYBRID = "hybrid"


# ============================================================
# DOCUMENT / LOCAL-EVIDENCE INDICATORS
# ============================================================

RAG_PATTERNS = [
    # Constitution / legal provisions
    r"\barticle\s+\d+[a-z]?\b",
    r"\barticles\s+\d+[a-z]?\b",
    r"\bsection\s+\d+[a-z]?\b",
    r"\bsections\s+\d+[a-z]?\b",
    r"\bclause\s+\d+[a-z]?\b",
    r"\bclauses\s+\d+[a-z]?\b",
    r"\bpart\s+[ivx]+\b",
    r"\bparts\s+[ivx]+\b",
    r"\bschedule\s+\d+[a-z]?\b",
    r"\bschedules?\b",

    # Constitutional / document concepts
    r"\bpreamble\b",
    r"\bfundamental rights?\b",
    r"\bdirective principles?\b",
    r"\bconstitutional remedies\b",

    # Explicit document-oriented questions
    r"\baccording to (the|my|this)\b",
    r"\bin (the|this) document\b",
    r"\bin the constitution\b",
    r"\bprovided document\b",
    r"\bprovided documents\b",
    r"\buploaded document\b",
    r"\buploaded documents\b",
    r"\bsource material\b",
    r"\bsource document\b",
    r"\bwhat does .* say\b",
    r"\bwhat is stated\b",
    r"\bwhat does the constitution say\b",
]


# ============================================================
# WEB / CURRENT INFORMATION INDICATORS
# ============================================================

WEB_PATTERNS = [
    # Current / recent
    r"\blatest\b",
    r"\brecent\b",
    r"\btoday\b",
    r"\bcurrently\b",
    r"\bcurrent\b",
    r"\bnew\b",
    r"\brecently\b",

    # Time-sensitive
    r"\bthis week\b",
    r"\bthis month\b",
    r"\bthis year\b",
    r"\b202[0-9]\b",

    # News / developments
    r"\bnews\b",
    r"\bdevelopment(s)?\b",
    r"\bupdate(s)?\b",
    r"\bwhat happened\b",
    r"\bongoing\b",

    # Case / judgment discovery
    r"\bjudgment(s)?\b",
    r"\bcase(s)?\b",
    r"\bverdict(s)?\b",
    r"\bruling(s)?\b",
    r"\bdecision(s)?\b",

    # General legal procedures / requirements
    r"\blegal requirements?\b",
    r"\brequirements?\b",
    r"\bprocedure\b",
    r"\bprocess\b",
    r"\beligibility\b",
    r"\beligible\b",
    r"\bhow can i\b",
    r"\bhow do i\b",
    r"\bwhere can i\b",
    r"\bhow to\b",
]


# ============================================================
# GENERAL LEGAL-QUESTION INDICATORS
# ============================================================

# These indicate that the user is asking for general legal
# information rather than specifically asking about the
# uploaded/local document.
GENERAL_LEGAL_PATTERNS = [
    r"^\s*what is\b",
    r"^\s*what are\b",
    r"^\s*what does\b",
    r"^\s*who is\b",
    r"^\s*who are\b",
    r"^\s*explain\b",
    r"^\s*define\b",
    r"^\s*definition of\b",
    r"^\s*meaning of\b",
    r"\bact\b",
    r"\blaw\b",
    r"\blegal\b",
    r"\bright\b",
    r"\brights\b",
    r"\boffence\b",
    r"\boffense\b",
    r"\bpenalty\b",
    r"\bpunishment\b",
    r"\bprocedure\b",
    r"\brequirements?\b",
    r"\beligibility\b",
]


# ============================================================
# HELPERS
# ============================================================

def _matches_any(
    query: str,
    patterns: list[str],
) -> bool:
    query_lower = query.lower()

    return any(
        re.search(pattern, query_lower)
        for pattern in patterns
    )


def _has_document_intent(query: str) -> bool:
    return _matches_any(query, RAG_PATTERNS)


def _has_web_intent(query: str) -> bool:
    return _matches_any(query, WEB_PATTERNS)


def _has_general_legal_intent(query: str) -> bool:
    return _matches_any(query, GENERAL_LEGAL_PATTERNS)


# ============================================================
# ROUTER
# ============================================================

def route_query(
    query: str,
) -> QueryRoute:

    query = query.strip()

    # Preserve existing behavior for empty input.
    if not query:
        return QueryRoute.RAG

    has_rag_signal = _has_document_intent(query)
    has_web_signal = _has_web_intent(query)
    has_general_legal_signal = _has_general_legal_intent(query)

    # --------------------------------------------------------
    # HYBRID
    # --------------------------------------------------------
    # Both local/document intent and current/web intent.
    if has_rag_signal and has_web_signal:
        return QueryRoute.HYBRID

    # --------------------------------------------------------
    # WEB
    # --------------------------------------------------------
    # Explicit current/web intent wins.
    if has_web_signal:
        return QueryRoute.WEB

    # --------------------------------------------------------
    # RAG
    # --------------------------------------------------------
    # Strong document-specific intent.
    if has_rag_signal:
        return QueryRoute.RAG

    # --------------------------------------------------------
    # GENERAL LEGAL -> WEB
    # --------------------------------------------------------
    # General legal questions should not automatically fall back
    # to uploaded documents.
    #
    # Examples:
    #   "What is the POCSO Act?"
    #   "What is bail?"
    #   "Explain consumer protection law."
    if has_general_legal_signal:
        return QueryRoute.WEB

    # --------------------------------------------------------
    # SAFE DEFAULT
    # --------------------------------------------------------
    # Preserve the historical default for completely ambiguous
    # queries that do not provide enough intent information.
    return QueryRoute.RAG


# ============================================================
# DEBUG / EXPLAINABILITY HELPER
# ============================================================

def explain_route(
    query: str,
) -> dict:

    return {
        "query": query,
        "route": route_query(query).value,
        "rag_signal": _has_document_intent(query),
        "web_signal": _has_web_intent(query),
        "general_legal_signal": _has_general_legal_intent(query),
    }