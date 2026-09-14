"""
AskLaw Web Source Ranker

Ranks web-search candidates before they are passed to the LLM.

The ranker uses deterministic signals:

    - source authority
    - query relevance
    - content quality
    - current-information intent
    - publication/update date extraction
    - freshness

It does NOT perform web requests.
It does NOT call an LLM.
It only ranks already-retrieved sources.

Important:
    A date extracted from search-result content is treated as the
    source/article date, NOT automatically as the date of a judgment.
"""

from __future__ import annotations

import re
from datetime import date
from urllib.parse import urlparse


# ============================================================
# AUTHORITY SIGNALS
# ============================================================

# Strong authority signals for Indian legal research.
HIGH_AUTHORITY_DOMAINS = {
    "supremecourt.gov.in": 1.00,
    "main.sci.gov.in": 1.00,
    "indiacode.nic.in": 1.00,
    "legislative.gov.in": 0.98,
    "doj.gov.in": 0.98,
    "lawmin.gov.in": 0.98,
    "pib.gov.in": 0.95,
    "nalsa.gov.in": 0.95,
    "highcourt.gov.in": 0.95,
}

MEDIUM_AUTHORITY_DOMAIN_SUFFIXES = (
    ".gov.in",
    ".nic.in",
    ".ac.in",
)

LEGAL_RESEARCH_DOMAINS = {
    "scobserver.in": 0.90,
    "barandbench.com": 0.88,
    "livelaw.in": 0.88,
    "indiankanoon.org": 0.86,
    "ipleaders.in": 0.72,
}


# ============================================================
# QUERY SIGNALS
# ============================================================

CURRENT_PATTERNS = [
    r"\blatest\b",
    r"\brecent\b",
    r"\bcurrent\b",
    r"\btoday\b",
    r"\brecently\b",
    r"\bthis week\b",
    r"\bthis month\b",
    r"\bthis year\b",
    r"\bnew\b",
    r"\brecent developments?\b",
    r"\blatest developments?\b",
]

LEGAL_PATTERNS = [
    r"\barticle\b",
    r"\bsection\b",
    r"\bclause\b",
    r"\bact\b",
    r"\blaw\b",
    r"\bcourt\b",
    r"\bsupreme court\b",
    r"\bhigh court\b",
    r"\bjudgment\b",
    r"\bjudgments\b",
    r"\bcase\b",
    r"\bcases\b",
    r"\bruling\b",
    r"\bverdict\b",
]


# ============================================================
# DATE EXTRACTION
# ============================================================

# Matches common textual date formats found in SearXNG snippets.
#
# Examples:
#   25 Aug 2026
#   25 August 2026
#   24 Aug 2017
#   27 Sept 2018
DATE_PATTERNS = [
    (
        re.compile(
            r"\b("
            r"0?[1-9]|[12]\d|3[01]"
            r")\s+"
            r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|"
            r"May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|"
            r"Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
            r"\s+"
            r"(20\d{2})\b",
            re.IGNORECASE,
        ),
        "%d %b %Y",
    ),
]

MONTH_MAP = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}


def _parse_textual_date(match: re.Match[str]) -> date | None:
    """Convert a textual day-month-year regex match into a date."""

    try:
        day = int(match.group(1))
        month_text = match.group(2).lower()
        year = int(match.group(3))

        month = MONTH_MAP.get(month_text)

        if month is None:
            return None

        return date(
            year=year,
            month=month,
            day=day,
        )

    except (TypeError, ValueError):
        return None


def _extract_result_date(
    result: dict,
) -> tuple[date | None, str | None, float]:
    """
    Extract the best available source date.

    Priority:

        1. Explicit SearXNG publishedDate
        2. Explicit SearXNG pubdate
        3. Date found in title
        4. Date found in content
        5. Date found in URL

    Returns:

        (date, source, confidence)

    Confidence reflects how directly the date was supplied.

    Important:
        This date is treated as a publication/update/search-result date.
        It must NOT be interpreted as the date of a court judgment.
    """

    # --------------------------------------------------------
    # 1. Explicit publishedDate
    # --------------------------------------------------------

    published_date = result.get("publishedDate")

    if published_date:
        parsed = _parse_explicit_date(published_date)

        if parsed:
            return (
                parsed,
                "publishedDate",
                1.00,
            )

    # --------------------------------------------------------
    # 2. Explicit pubdate
    # --------------------------------------------------------

    pubdate = result.get("pubdate")

    if pubdate:
        parsed = _parse_explicit_date(pubdate)

        if parsed:
            return (
                parsed,
                "pubdate",
                0.95,
            )

    # --------------------------------------------------------
    # 3. Title
    # --------------------------------------------------------

    title = (result.get("title") or "").strip()

    parsed = _find_date_in_text(title)

    if parsed:
        return (
            parsed,
            "title",
            0.90,
        )

    # --------------------------------------------------------
    # 4. Content
    # --------------------------------------------------------

    content = (result.get("content") or "").strip()

    parsed = _find_date_in_text(content)

    if parsed:
        return (
            parsed,
            "content",
            0.70,
        )

    # --------------------------------------------------------
    # 5. URL
    # --------------------------------------------------------

    url = (result.get("url") or "").strip()

    parsed = _find_date_in_text(url)

    if parsed:
        return (
            parsed,
            "url",
            0.55,
        )

    return (
        None,
        None,
        0.0,
    )


def _parse_explicit_date(value: object) -> date | None:
    """
    Parse an explicit date-like value returned by SearXNG.

    Handles common formats such as:

        2026-08-25
        2026-08-25T12:30:00
        2026-08-25T12:30:00Z
    """

    if isinstance(value, date):
        return value

    if not isinstance(value, str):
        return None

    value = value.strip()

    if not value:
        return None

    # ISO date at the beginning of the value.
    match = re.match(
        r"^(20\d{2})-(\d{1,2})-(\d{1,2})",
        value,
    )

    if match:
        try:
            return date(
                year=int(match.group(1)),
                month=int(match.group(2)),
                day=int(match.group(3)),
            )
        except ValueError:
            return None

    # Fallback to textual date parsing.
    return _find_date_in_text(value)


def _find_date_in_text(text: str) -> date | None:
    """Find the first supported textual date inside arbitrary text."""

    if not text:
        return None

    for pattern, _ in DATE_PATTERNS:
        match = pattern.search(text)

        if match:
            parsed = _parse_textual_date(match)

            if parsed:
                return parsed

    return None


# ============================================================
# FRESHNESS
# ============================================================

def _freshness_score(
    result_date: date | None,
    today: date | None = None,
) -> float:
    """
    Convert source age into a deterministic freshness score.

    Score behavior:

        1.00 -> very recent
        ~0.75 -> recent
        ~0.50 -> about one year old
        lower -> older material

    Unknown dates return a neutral score of 0.0 rather than
    pretending that the source is fresh.
    """

    if result_date is None:
        return 0.0

    if today is None:
        today = date.today()

    age_days = (today - result_date).days

    # Future dates should not receive a negative age.
    if age_days < 0:
        age_days = 0

    # --------------------------------------------------------
    # Freshness buckets
    # --------------------------------------------------------

    if age_days <= 7:
        return 1.00

    if age_days <= 30:
        return 0.95

    if age_days <= 90:
        return 0.85

    if age_days <= 180:
        return 0.75

    if age_days <= 365:
        return 0.60

    if age_days <= 730:
        return 0.45

    if age_days <= 1095:
        return 0.30

    if age_days <= 1825:
        return 0.20

    return 0.10


# ============================================================
# QUERY HELPERS
# ============================================================

def _wants_current_information(query: str) -> bool:
    """Return True when the query explicitly requests recent/current info."""

    query_lower = query.lower()

    return any(
        re.search(pattern, query_lower)
        for pattern in CURRENT_PATTERNS
    )


# ============================================================
# DOMAIN HELPERS
# ============================================================

def _normalize_domain(url: str) -> str:
    """Return a normalized hostname without www."""

    try:
        hostname = urlparse(url).hostname or ""
        return hostname.lower().strip("www.")
    except Exception:
        return ""


# ============================================================
# TOKENIZATION
# ============================================================

def _tokenize(text: str) -> set[str]:
    """Simple deterministic word tokenizer."""

    return {
        token
        for token in re.findall(
            r"\b[a-z0-9]{2,}\b",
            text.lower(),
        )
    }


# ============================================================
# RELEVANCE
# ============================================================

def _query_relevance(
    query: str,
    result: dict,
) -> float:
    """
    Estimate lexical relevance between query and result.

    Uses overlap between query terms and the source title/content.
    """

    query_tokens = _tokenize(query)

    if not query_tokens:
        return 0.0

    title = result.get("title", "")
    content = result.get("content", "")

    title_tokens = _tokenize(title)
    content_tokens = _tokenize(content)

    title_overlap = len(
        query_tokens & title_tokens
    ) / len(query_tokens)

    content_overlap = (
        len(query_tokens & content_tokens)
        / len(query_tokens)
    )

    # Titles are generally a stronger relevance signal than long
    # body snippets.
    score = (
        0.70 * title_overlap
        + 0.30 * content_overlap
    )

    return min(score, 1.0)


# ============================================================
# AUTHORITY
# ============================================================

def _authority_score(result: dict) -> float:
    """Score source authority using its domain."""

    domain = _normalize_domain(
        result.get("url", "")
    )

    if not domain:
        return 0.0

    if domain in HIGH_AUTHORITY_DOMAINS:
        return HIGH_AUTHORITY_DOMAINS[domain]

    if domain in LEGAL_RESEARCH_DOMAINS:
        return LEGAL_RESEARCH_DOMAINS[domain]

    if any(
        domain.endswith(suffix)
        for suffix in MEDIUM_AUTHORITY_DOMAIN_SUFFIXES
    ):
        return 0.82

    return 0.45


# ============================================================
# CONTENT QUALITY
# ============================================================

def _content_quality_score(result: dict) -> float:
    """
    Score basic result quality.

    This is deliberately conservative and deterministic.
    """

    title = (result.get("title") or "").strip()
    content = (result.get("content") or "").strip()
    url = (result.get("url") or "").strip()

    score = 0.0

    if title:
        score += 0.30

    if url:
        score += 0.20

    content_length = len(content)

    if content_length >= 200:
        score += 0.40
    elif content_length >= 80:
        score += 0.25
    elif content_length > 0:
        score += 0.10

    # Avoid obvious search-result junk.
    junk_patterns = (
        "captcha",
        "enable javascript",
        "access denied",
        "page not found",
    )

    if any(
        pattern in content.lower()
        for pattern in junk_patterns
    ):
        score *= 0.25

    return min(score, 1.0)


# ============================================================
# CURRENT-INTENT SIGNAL
# ============================================================

def _current_intent_score(
    query: str,
    result: dict,
) -> float:
    """
    Give a modest bonus when current information is requested.

    This signal is intentionally weaker than true freshness.

    A source containing words such as "latest" or "2026" is not
    automatically recent or authoritative.
    """

    if not _wants_current_information(query):
        return 0.5

    title = (result.get("title") or "").lower()
    content = (result.get("content") or "").lower()

    current_words = (
        "latest",
        "recent",
        "2026",
        "2025",
        "new",
        "today",
        "recently",
        "judgment",
        "judgement",
        "order",
    )

    hits = sum(
        1
        for word in current_words
        if word in title or word in content
    )

    return min(
        0.5 + (hits * 0.10),
        1.0,
    )


# ============================================================
# RESULT SCORING
# ============================================================

def _score_result(
    query: str,
    result: dict,
) -> dict:
    """Return the result with ranking signals attached."""

    relevance = _query_relevance(
        query,
        result,
    )

    authority = _authority_score(
        result,
    )

    content_quality = _content_quality_score(
        result,
    )

    current_intent = _current_intent_score(
        query,
        result,
    )

    result_date, date_source, date_confidence = (
        _extract_result_date(result)
    )

    freshness = _freshness_score(
        result_date,
    )

    wants_current = _wants_current_information(
        query,
    )

    # --------------------------------------------------------
    # Query-dependent weighting
    # --------------------------------------------------------
    #
    # Normal legal query:
    #
    #   relevance + authority dominate
    #
    # Latest/current query:
    #
    #   freshness gets a stronger role
    #
    # This prevents an old but foundational source from being
    # unnecessarily pushed down for a normal legal question,
    # while allowing recent material to rise for queries that
    # explicitly ask for current information.

    if wants_current:
        final_score = (
            0.35 * relevance
            + 0.25 * authority
            + 0.15 * content_quality
            + 0.05 * current_intent
            + 0.20 * freshness
        )
    else:
        final_score = (
            0.45 * relevance
            + 0.30 * authority
            + 0.15 * content_quality
            + 0.10 * current_intent
        )

    ranked = dict(result)

    ranked["ranking"] = {
        "relevance_score": round(
            relevance,
            4,
        ),
        "authority_score": round(
            authority,
            4,
        ),
        "content_quality_score": round(
            content_quality,
            4,
        ),
        "current_intent_score": round(
            current_intent,
            4,
        ),
        "freshness_score": round(
            freshness,
            4,
        ),
        "final_score": round(
            final_score,
            4,
        ),
    }

    # --------------------------------------------------------
    # Date metadata
    # --------------------------------------------------------

    ranked["date_metadata"] = {
        "date": (
            result_date.isoformat()
            if result_date
            else None
        ),
        "source": date_source,
        "confidence": round(
            date_confidence,
            4,
        ),
    }

    return ranked


# ============================================================
# DEDUPLICATION
# ============================================================

def _deduplicate_results(
    results: list[dict],
) -> list[dict]:
    """Remove duplicate URLs while preserving first occurrence."""

    seen: set[str] = set()
    deduplicated: list[dict] = []

    for result in results:
        url = (result.get("url") or "").strip().lower()

        if not url:
            continue

        if url in seen:
            continue

        seen.add(url)
        deduplicated.append(result)

    return deduplicated


# ============================================================
# PUBLIC RANKING FUNCTION
# ============================================================

def rank_web_sources(
    query: str,
    results: list[dict],
    limit: int = 5,
) -> list[dict]:
    """
    Rank and return the strongest web sources.

    No network requests are made here.
    """

    if not results:
        return []

    cleaned = _deduplicate_results(
        results
    )

    ranked = [
        _score_result(
            query,
            result,
        )
        for result in cleaned
    ]

    ranked.sort(
        key=lambda item: item["ranking"]["final_score"],
        reverse=True,
    )

    return ranked[:limit]