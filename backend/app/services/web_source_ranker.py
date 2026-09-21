"""
AskLaw Web Source Ranker

Ranks web-search candidates before they are passed to the LLM.

Deterministic signals:

    - query relevance
    - source authority
    - content quality
    - current-information intent
    - publication/update date
    - freshness
    - source type
    - legal-event strength
    - primary-source strength
    - commentary strength

The ranker:

    - performs NO network requests
    - calls NO LLM
    - only processes already-retrieved search results

Important:

A date extracted from a search snippet is treated as the date
associated with the source/article/result. It is NOT automatically
treated as the date of a court judgment.
"""

from __future__ import annotations

import re
from datetime import date
from urllib.parse import urlparse


# ============================================================
# AUTHORITY SIGNALS
# ============================================================

HIGH_AUTHORITY_DOMAINS = {
    "supremecourt.gov.in": 1.00,
    "sci.gov.in": 1.00,
    "main.sci.gov.in": 1.00,
    "api.sci.gov.in": 1.00,
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

LOW_QUALITY_DOMAINS = {
    "instagram.com",
    "facebook.com",
    "x.com",
    "twitter.com",
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
    r"\bupdat(?:e|ed|es)\b",
]

JUDGMENT_QUERY_PATTERNS = [
    r"\blatest .*judg(?:e)?ment",
    r"\brecent .*judg(?:e)?ment",
    r"\bcurrent .*judg(?:e)?ment",
    r"\blatest .*ruling",
    r"\brecent .*ruling",
    r"\blatest .*order",
    r"\brecent .*order",
    r"\bnew .*judg(?:e)?ment",
    r"\bnew .*ruling",
    r"\bnew .*order",
]

QUERY_TOPIC_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "can",
    "does",
    "for",
    "from",
    "get",
    "has",
    "have",
    "in",
    "india",
    "is",
    "latest",
    "new",
    "of",
    "on",
    "or",
    "recent",
    "recently",
    "ruling",
    "supreme",
    "court",
    "the",
    "this",
    "today",
    "was",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "with",
    "year",
    "judgment",
    "judgments",
    "judgement",
    "judgements",
    "order",
    "orders",
    "decision",
    "decisions",
    "developments",
    "development",
    "act",
    "law",
    "case",
    "cases",
}


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
    r"\bjudgement\b",
    r"\bjudgements\b",
    r"\bcase\b",
    r"\bcases\b",
    r"\bruling\b",
    r"\bverdict\b",
    r"\border\b",
    r"\bpetition\b",
    r"\bbench\b",
]


# ============================================================
# LEGAL EVENT SIGNALS
# ============================================================

STRONG_EVENT_PATTERNS = [
    r"\bjudgment\b",
    r"\bjudgement\b",
    r"\bruling\b",
    r"\bverdict\b",
    r"\border\b",
    r"\bheld\b",
    r"\bruled\b",
    r"\bdirected\b",
    r"\bdismissed\b",
    r"\ballowed\b",
    r"\bdisposed\b",
    r"\bbench\b",
    r"\bpetition\b",
    r"\bwrit petition\b",
    r"\bslp\b",
    r"\bcivil appeal\b",
    r"\bcriminal appeal\b",
    r"\bthe supreme court held\b",
    r"\bthe supreme court ruled\b",
    r"\bsupreme court has held\b",
    r"\bsupreme court has ruled\b",
]

WEAK_EVENT_PATTERNS = [
    r"\bdecision\b",
    r"\bcase law\b",
    r"\bcourt decision\b",
    r"\bcourt order\b",
]

COMMENTARY_PATTERNS = [
    r"\banalysis\b",
    r"\boverview\b",
    r"\bbackground\b",
    r"\bevolution\b",
    r"\bsignificance\b",
    r"\bexplainer\b",
    r"\bhistory\b",
    r"\bguide\b",
    r"\bunderstanding\b",
    r"\bdiscussion\b",
    r"\bcommentary\b",
]


# ============================================================
# SOURCE-TYPE SIGNALS
# ============================================================

PRIMARY_SOURCE_PATTERNS = [
    r"\bjudgment\b",
    r"\bjudgement\b",
    r"\border\b",
    r"\bjudgment\.pdf\b",
    r"\bjudgement\.pdf\b",
    r"\bsupreme court\b",
    r"\bhigh court\b",
    r"\bapi\.sci\.gov\.in\b",
    r"\bsci\.gov\.in\b",
    r"\bindia code\b",
]

COMMENTARY_SOURCE_PATTERNS = [
    r"\banalysis\b",
    r"\boverview\b",
    r"\bbackground\b",
    r"\bevolution\b",
    r"\bsignificance\b",
    r"\bexplainer\b",
    r"\bhistory\b",
    r"\bguide\b",
    r"\bunderstanding\b",
    r"\bcommentary\b",
]

NEWS_SOURCE_PATTERNS = [
    r"\blive law\b",
    r"\bbar and bench\b",
    r"\bnews\b",
    r"\bbreaking\b",
    r"\breport\b",
]


# ============================================================
# DOMAIN HELPERS
# ============================================================

def _normalize_domain(url: str) -> str:
    """Return normalized hostname without www."""

    try:
        hostname = urlparse(url).hostname or ""
        return hostname.lower().removeprefix("www.")
    except Exception:
        return ""


# ============================================================
# TOKENIZATION
# ============================================================

def _tokenize(text: str) -> set[str]:
    """Simple deterministic tokenizer."""

    return {
        token
        for token in re.findall(
            r"\b[a-z0-9]{2,}\b",
            text.lower(),
        )
    }


# ============================================================
# QUERY HELPERS
# ============================================================

def _wants_current_information(query: str) -> bool:
    """Return True when the query requests current information."""

    query_lower = query.lower()

    return any(
        re.search(pattern, query_lower)
        for pattern in CURRENT_PATTERNS
    )


def _wants_latest_judgment(query: str) -> bool:
    """
    Return True when the query specifically asks for a recent
    judgment, ruling, or order.
    """

    query_lower = query.lower()

    return any(
        re.search(pattern, query_lower)
        for pattern in JUDGMENT_QUERY_PATTERNS
    )


def _is_legal_query(
    query: str,
) -> bool:
    """Return True when the query clearly concerns a legal topic."""

    query_lower = query.lower()

    return any(
        re.search(pattern, query_lower)
        for pattern in LEGAL_PATTERNS
    )


# ============================================================
# DATE EXTRACTION
# ============================================================

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

DATE_PATTERN = re.compile(
    r"\b("
    r"0?[1-9]|[12]\d|3[01]"
    r")(?:\s+|[-_])"
    r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|"
    r"May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|"
    r"Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"(?:\s+|[-_])"
    r"(20\d{2})\b",
    re.IGNORECASE,
)


URL_TEXTUAL_DATE_PATTERN = re.compile(
    r"("
    r"0?[1-9]|[12]\d|3[01]"
    r")[-_]"
    r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|"
    r"May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|"
    r"Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"[-_]"
    r"(20\d{2})",
    re.IGNORECASE,
)


def _parse_textual_date(
    match: re.Match[str],
) -> date | None:
    """Convert a textual date regex match into a date."""

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


def _parse_explicit_date(
    value: object,
) -> date | None:
    """Parse common explicit date representations."""

    if isinstance(value, date):
        return value

    if not isinstance(value, str):
        return None

    value = value.strip()

    if not value:
        return None

    iso_match = re.match(
        r"^(20\d{2})-(\d{1,2})-(\d{1,2})",
        value,
    )

    if iso_match:
        try:
            return date(
                year=int(iso_match.group(1)),
                month=int(iso_match.group(2)),
                day=int(iso_match.group(3)),
            )
        except ValueError:
            return None

    textual_match = DATE_PATTERN.search(value)

    if textual_match:
        return _parse_textual_date(textual_match)

    return None


def _find_date_in_text(
    text: str,
) -> date | None:
    """Find the first supported textual date."""

    if not text:
        return None

    match = DATE_PATTERN.search(text)

    if match:
        return _parse_textual_date(match)

    return None


def _find_numeric_date_in_text(
    text: str,
) -> date | None:
    """Find a numeric date such as 14.07.2026 or 14/07/2026."""

    if not text:
        return None

    match = re.search(
        r"\b(0?[1-9]|[12]\d|3[01])[./-](0?[1-9]|1[0-2])[./-](20\d{2})\b",
        text,
    )

    if not match:
        return None

    try:
        return date(
            year=int(match.group(3)),
            month=int(match.group(2)),
            day=int(match.group(1)),
        )
    except ValueError:
        return None


def _find_judgment_date_in_text(
    text: str,
) -> date | None:
    """
    Find a date that is explicitly associated with a judgment/order/ruling.

    A generic date at the beginning of a search snippet is not enough,
    because it can represent an article/update date rather than the date
    of the underlying legal event.
    """

    if not text:
        return None

    judgment_terms = (
        "judgment",
        "judgement",
        "order",
        "ruling",
        "decision",
    )

    for match in DATE_PATTERN.finditer(text):
        prefix = text[
            max(0, match.start() - 80):match.start()
        ].lower()

        if any(term in prefix for term in judgment_terms):
            return _parse_textual_date(match)

    url_match = URL_TEXTUAL_DATE_PATTERN.search(text)

    if url_match:
        prefix = text[
            max(0, url_match.start() - 80):url_match.start()
        ].lower()

        if any(term in prefix for term in judgment_terms):
            try:
                return date(
                    year=int(url_match.group(3)),
                    month=MONTH_MAP.get(
                        url_match.group(2).lower(),
                        0,
                    ),
                    day=int(url_match.group(1)),
                )
            except (TypeError, ValueError):
                return None

    numeric_match = re.search(
        r"(judg(?:ment|ement)|order|ruling|decision)"
        r"[^.]{0,80}?"
        r"(0?[1-9]|[12]\d|3[01])[./-](0?[1-9]|1[0-2])[./-](20\d{2})\b",
        text,
        flags=re.IGNORECASE,
    )

    if numeric_match:
        try:
            return date(
                year=int(numeric_match.group(4)),
                month=int(numeric_match.group(3)),
                day=int(numeric_match.group(2)),
            )
        except ValueError:
            return None

    return None


def _extract_result_date(
    result: dict,
    *,
    latest_judgment: bool = False,
) -> tuple[date | None, str | None, float]:
    """
    Extract the best date for ranking.

    For ordinary/current-information queries, source/article dates can come
    from publishedDate, pubdate, title, content, or URL.

    For latest-judgment queries, generic content dates are not treated as
    judgment dates. A judgment-specific date in the title, URL, or content
    is preferred; source-level publication metadata is only a fallback.
    """

    title = (result.get("title") or "").strip()
    content = (result.get("content") or "").strip()
    url = (result.get("url") or "").strip()

    if latest_judgment:
        parsed = _find_judgment_date_in_text(title)

        if parsed:
            return (
                parsed,
                "title_judgment",
                0.95,
            )

        parsed = _find_judgment_date_in_text(url)

        if parsed:
            return (
                parsed,
                "url_judgment",
                0.90,
            )

        parsed = _find_judgment_date_in_text(content)

        if parsed:
            return (
                parsed,
                "content_judgment",
                0.80,
            )

    published_date = result.get("publishedDate")

    if published_date:
        parsed = _parse_explicit_date(
            published_date
        )

        if parsed:
            return (
                parsed,
                "publishedDate",
                1.00,
            )

    pubdate = result.get("pubdate")

    if pubdate:
        parsed = _parse_explicit_date(
            pubdate
        )

        if parsed:
            return (
                parsed,
                "pubdate",
                0.95,
            )

    # Generic title/URL dates are only treated as source dates for ordinary
    # current-information queries. For latest-judgment queries, a date must
    # be explicitly tied to the legal event.
    if not latest_judgment:
        parsed = _find_date_in_text(title)

        if parsed:
            return (
                parsed,
                "title",
                0.90,
            )

        parsed = _find_date_in_text(url)

        if parsed:
            return (
                parsed,
                "url",
                0.55,
            )

        parsed = _find_date_in_text(content)

        if parsed:
            return (
                parsed,
                "content",
                0.70,
            )

    return (
        None,
        None,
        0.0,
    )


# ============================================================
# FRESHNESS
# ============================================================

def _freshness_score(
    result_date: date | None,
    today: date | None = None,
) -> float:
    """
    Convert source age into a deterministic freshness score.

    Very recent:
        1.00

    Recent:
        0.95 - 0.75

    Older:
        progressively lower
    """

    if result_date is None:
        return 0.0

    if today is None:
        today = date.today()

    age_days = max(
        (today - result_date).days,
        0,
    )

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
# RELEVANCE
# ============================================================

def _query_relevance(
    query: str,
    result: dict,
) -> float:
    """
    Estimate lexical relevance between query and result.
    Title is weighted more heavily than content.
    """

    query_tokens = _tokenize(query)

    if not query_tokens:
        return 0.0

    title_tokens = _tokenize(
        result.get("title", "")
    )

    content_tokens = _tokenize(
        result.get("content", "")
    )

    title_overlap = (
        len(query_tokens & title_tokens)
        / len(query_tokens)
    )

    content_overlap = (
        len(query_tokens & content_tokens)
        / len(query_tokens)
    )

    score = (
        0.70 * title_overlap
        + 0.30 * content_overlap
    )

    return min(score, 1.0)


def _topic_relevance(
    query: str,
    result: dict,
) -> float:
    """
    Estimate relevance to the substantive legal topic.

    Generic retrieval words such as "latest", "Supreme Court", and
    "judgment" are removed so they do not make every recent court document
    look highly relevant to the actual topic.
    """

    topic_tokens = {
        token
        for token in _tokenize(query)
        if token not in QUERY_TOPIC_STOPWORDS
    }

    if not topic_tokens:
        return 0.0

    title_tokens = _tokenize(
        result.get("title", "")
    )

    content_tokens = _tokenize(
        result.get("content", "")
    )

    matched_score = 0.0

    for token in topic_tokens:
        if token in title_tokens:
            matched_score += 1.0
        elif token in content_tokens:
            matched_score += 0.60

    return min(
        matched_score / len(topic_tokens),
        1.0,
    )


# ============================================================
# AUTHORITY
# ============================================================

def _authority_score(
    result: dict,
) -> float:
    """Score source authority based on domain."""

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

    if domain in LOW_QUALITY_DOMAINS:
        return 0.10

    return 0.45


# ============================================================
# CONTENT QUALITY
# ============================================================

def _content_quality_score(
    result: dict,
) -> float:
    """Score basic result quality."""

    title = (
        result.get("title") or ""
    ).strip()

    content = (
        result.get("content") or ""
    ).strip()

    url = (
        result.get("url") or ""
    ).strip()

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

    junk_patterns = (
        "captcha",
        "enable javascript",
        "access denied",
        "page not found",
        "unusual traffic",
    )

    if any(
        pattern in content.lower()
        for pattern in junk_patterns
    ):
        score *= 0.25

    return min(score, 1.0)


# ============================================================
# CURRENT INTENT
# ============================================================

def _current_intent_score(
    query: str,
    result: dict,
) -> float:
    """
    Score alignment with current-information intent.

    This is weaker than actual freshness.
    """

    if not _wants_current_information(query):
        return 0.5

    title = (
        result.get("title") or ""
    ).lower()

    content = (
        result.get("content") or ""
    ).lower()

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
        "ruling",
        "held",
        "ruled",
    )

    hits = sum(
        1
        for word in current_words
        if word in title or word in content
    )

    return min(
        0.5 + (hits * 0.08),
        1.0,
    )


# ============================================================
# LEGAL EVENT DETECTION
# ============================================================

def _count_patterns(
    text: str,
    patterns: list[str],
) -> int:
    """Count how many distinct patterns match."""

    if not text:
        return 0

    count = 0

    for pattern in patterns:
        if re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        ):
            count += 1

    return count


def _legal_event_score(
    result: dict,
) -> float:
    """
    Estimate how strongly a result indicates an actual legal event.

    This is a ranking signal, NOT a legal conclusion.
    """

    title = (
        result.get("title") or ""
    ).strip()

    content = (
        result.get("content") or ""
    ).strip()

    text = f"{title} {content}"

    strong_hits = _count_patterns(
        text,
        STRONG_EVENT_PATTERNS,
    )

    weak_hits = _count_patterns(
        text,
        WEAK_EVENT_PATTERNS,
    )

    commentary_hits = _count_patterns(
        text,
        COMMENTARY_PATTERNS,
    )

    score = (
        strong_hits * 0.14
        + weak_hits * 0.07
        - commentary_hits * 0.05
    )

    return max(
        0.0,
        min(score, 1.0),
    )


# ============================================================
# SOURCE TYPE CLASSIFICATION
# ============================================================

def _classify_source_type(
    result: dict,
) -> tuple[str, float]:
    """
    Classify source into:

        primary
        legal_reporting
        commentary
        general
    """

    title = (
        result.get("title") or ""
    ).lower()

    content = (
        result.get("content") or ""
    ).lower()

    url = (
        result.get("url") or ""
    ).lower()

    text = (
        f"{title} {content} {url}"
    )

    primary_hits = _count_patterns(
        text,
        PRIMARY_SOURCE_PATTERNS,
    )

    commentary_hits = _count_patterns(
        text,
        COMMENTARY_SOURCE_PATTERNS,
    )

    news_hits = _count_patterns(
        text,
        NEWS_SOURCE_PATTERNS,
    )

    domain = _normalize_domain(
        result.get("url", "")
    )

    if domain in HIGH_AUTHORITY_DOMAINS:
        return (
            "primary",
            0.95,
        )

    if (
        primary_hits >= 2
        and commentary_hits == 0
    ):
        return (
            "primary",
            0.80,
        )

    if (
        commentary_hits >= 2
        and primary_hits == 0
    ):
        return (
            "commentary",
            0.85,
        )

    if (
        news_hits >= 1
        or domain in LEGAL_RESEARCH_DOMAINS
    ):
        return (
            "legal_reporting",
            0.80,
        )

    if commentary_hits >= 1:
        return (
            "commentary",
            0.65,
        )

    return (
        "general",
        0.50,
    )


# ============================================================
# PRIMARY SOURCE SIGNAL
# ============================================================

def _primary_source_score(
    result: dict,
    source_type: str,
) -> float:
    """Estimate primary-source strength."""

    domain = _normalize_domain(
        result.get("url", "")
    )

    if domain in HIGH_AUTHORITY_DOMAINS:
        return 1.0

    if source_type == "primary":
        return 0.85

    if source_type == "legal_reporting":
        return 0.35

    if source_type == "commentary":
        return 0.15

    return 0.20


# ============================================================
# COMMENTARY SIGNAL
# ============================================================

def _commentary_score(
    result: dict,
    source_type: str,
) -> float:
    """Estimate whether the result is commentary."""

    if source_type == "commentary":
        return 1.0

    if source_type == "legal_reporting":
        return 0.35

    if source_type == "primary":
        return 0.05

    title = (
        result.get("title") or ""
    ).lower()

    hits = _count_patterns(
        title,
        COMMENTARY_PATTERNS,
    )

    return min(
        hits * 0.20,
        1.0,
    )


# ============================================================
# TOPIC GROUPING
# ============================================================

def _topic_key(
    result: dict,
) -> str:
    """
    Create a lightweight normalized topic key.

    Used later for identifying obvious same-topic/same-case sources.
    """

    title = (
        result.get("title") or ""
    ).lower()

    title = re.sub(
        r"[^a-z0-9\s]",
        " ",
        title,
    )

    tokens = [
        token
        for token in title.split()
        if len(token) >= 4
    ]

    return " ".join(
        tokens[:8]
    )


# ============================================================
# RESULT SCORING
# ============================================================

def _score_result(
    query: str,
    result: dict,
) -> dict:
    """Attach all ranking signals to a result."""

    wants_current = _wants_current_information(
        query,
    )

    wants_latest_judgment = _wants_latest_judgment(
        query,
    )

    relevance = _query_relevance(
        query,
        result,
    )

    topic_relevance = _topic_relevance(
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
        _extract_result_date(
            result,
            latest_judgment=wants_latest_judgment,
        )
    )

    freshness = _freshness_score(
        result_date,
    )

    source_type, source_type_confidence = (
        _classify_source_type(result)
    )

    legal_event = _legal_event_score(
        result,
    )

    primary_source = _primary_source_score(
        result,
        source_type,
    )

    commentary = _commentary_score(
        result,
        source_type,
    )

    # ========================================================
    # NORMAL QUERY
    # ========================================================

    if not wants_current:

        # Legal questions need a stronger preference for authoritative
        # primary sources (official legislation/court/government sources)
        # while still keeping topical relevance as the largest signal.
        if _is_legal_query(query):

            final_score = (
                0.35 * relevance
                + 0.25 * authority
                + 0.15 * content_quality
                + 0.20 * primary_source
                + 0.05 * legal_event
            )

        else:

            final_score = (
                0.45 * relevance
                + 0.30 * authority
                + 0.15 * content_quality
                + 0.05 * primary_source
                + 0.05 * legal_event
            )

    # ========================================================
    # CURRENT INFORMATION QUERY
    # ========================================================

    elif not wants_latest_judgment:

        final_score = (
            0.35 * relevance
            + 0.23 * authority
            + 0.12 * content_quality
            + 0.05 * current_intent
            + 0.15 * freshness
            + 0.05 * primary_source
            + 0.05 * legal_event
        )

    # ========================================================
    # LATEST / RECENT LEGAL EVENT QUERY
    # ========================================================

    else:

        # Topic relevance is explicit here so that a recent official court
        # document cannot outrank a genuinely topical result merely because
        # it contains generic words such as "Supreme Court" and "judgment".
        final_score = (
            0.30 * relevance
            + 0.15 * topic_relevance
            + 0.18 * authority
            + 0.08 * content_quality
            + 0.04 * current_intent
            + 0.15 * freshness
            + 0.05 * legal_event
            + 0.05 * primary_source
        )

        final_score -= (
            0.05 * commentary
        )

        # Completely topic-mismatched results are still allowed to pass
        # through the pipeline, but are strongly demoted.
        if topic_relevance == 0.0:
            final_score *= 0.45
        elif topic_relevance < 0.30:
            final_score *= 0.75

    final_score = max(
        0.0,
        min(
            final_score,
            1.0,
        ),
    )

    ranked = dict(result)

    ranked["ranking"] = {
        "relevance_score": round(
            relevance,
            4,
        ),
        "topic_relevance_score": round(
            topic_relevance,
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
        "legal_event_score": round(
            legal_event,
            4,
        ),
        "primary_source_score": round(
            primary_source,
            4,
        ),
        "commentary_score": round(
            commentary,
            4,
        ),
        "final_score": round(
            final_score,
            4,
        ),
    }

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

    ranked["source_metadata"] = {
        "source_type": source_type,
        "source_type_confidence": round(
            source_type_confidence,
            4,
        ),
        "domain": _normalize_domain(
            result.get("url", "")
        ),
        "topic_key": _topic_key(
            result
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
# SOURCE GROUPING
# ============================================================

def _annotate_source_groups(
    ranked: list[dict],
) -> list[dict]:
    """
    Attach simple source-group identifiers.

    This will support later conflict detection and source diversity.
    """

    groups: dict[str, int] = {}

    for item in ranked:

        metadata = item.get(
            "source_metadata",
            {},
        )

        topic_key = metadata.get(
            "topic_key",
            "",
        )

        if not topic_key:
            continue

        if topic_key not in groups:
            groups[topic_key] = (
                len(groups) + 1
            )

        metadata["source_group"] = (
            groups[topic_key]
        )

        item["source_metadata"] = (
            metadata
        )

    return ranked


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

    No network requests are made.
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
        key=lambda item: (
            item["ranking"]["final_score"],
            item["ranking"]["authority_score"],
            item["ranking"]["freshness_score"],
        ),
        reverse=True,
    )

    ranked = _annotate_source_groups(
        ranked
    )

    return ranked[:limit]