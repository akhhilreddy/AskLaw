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

# ROUTE TYPES

class QueryRoute(str, Enum):

    RAG = "rag"
    WEB = "web"
    HYBRID = "hybrid"



# LEGAL / DOCUMENT INDICATORS


RAG_PATTERNS = [

    # Constitution / legal provisions
    r"\barticle\s+\d+[a-z]?\b",
    r"\barticles\s+\d+",
    r"\bsection\s+\d+[a-z]?\b",
    r"\bclause\s+\d+\b",
    r"\bpart\s+[ivx]+\b",

    # Document-oriented questions
    r"\baccording to (the|my|this)\b",
    r"\bin (the|this) document\b",
    r"\bin the constitution\b",
    r"\bprovided document\b",
    r"\buploaded document\b",
    r"\bsource material\b",
    r"\bwhat does .* say\b",
    r"\bwhat is stated\b",
    r"\bwhat does the constitution say\b",
]



# WEB / CURRENT INFORMATION INDICATORS


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
    r"\bverdict\b",
    r"\bruling(s)?\b",
]



# HELPERS


def _matches_any(
    query: str,
    patterns: list[str],
) -> bool:

    query_lower = query.lower()

    return any(
        re.search(pattern, query_lower)
        for pattern in patterns
    )



# ROUTER


def route_query(
    query: str,
) -> QueryRoute:

    query = query.strip()

    if not query:
        return QueryRoute.RAG

    has_rag_signal = _matches_any(
        query,
        RAG_PATTERNS,
    )

    has_web_signal = _matches_any(
        query,
        WEB_PATTERNS,
    )

 
    # HYBRID
  
    if has_rag_signal and has_web_signal:
        return QueryRoute.HYBRID


    # WEB


    if has_web_signal:
        return QueryRoute.WEB

   
    # RAG
    

    return QueryRoute.RAG


 
# DEBUG HELPER
 

def explain_route(
    query: str,
) -> dict:

    route = route_query(query)

    return {
        "query": query,
        "route": route.value,
        "rag_signal": _matches_any(
            query,
            RAG_PATTERNS,
        ),
        "web_signal": _matches_any(
            query,
            WEB_PATTERNS,
        ),
    }