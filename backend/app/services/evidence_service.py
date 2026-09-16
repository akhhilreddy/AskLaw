"""
AskLaw Evidence Service

Normalizes and combines evidence retrieved from:

    - local RAG / Qdrant
    - web search / SearXNG

The service does NOT:
    - call an LLM
    - perform web requests
    - decide whether a legal claim is true

It only creates a structured evidence bundle that can be passed
to the Prompt Service / Groq layer.

Responsibilities:

    1. Normalize RAG and web evidence
    2. Classify web sources
    3. Preserve source authority metadata
    4. Deduplicate obvious duplicate evidence
    5. Group related sources
    6. Detect basic conflicting signals
    7. Produce a unified evidence bundle
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse


# ============================================================
# SOURCE PRIORITY
# ============================================================

SOURCE_PRIORITY = {
    "primary": 4,
    "legal_reporting": 3,
    "commentary": 2,
    "general": 1,
    "rag": 4,
}


# ============================================================
# TEXT HELPERS
# ============================================================

def _clean_text(value: Any) -> str:
    """Return normalized text."""

    if value is None:
        return ""

    return re.sub(
        r"\s+",
        " ",
        str(value),
    ).strip()


def _normalize_url(url: Any) -> str:
    """Normalize a URL for duplicate detection."""

    if not url:
        return ""

    try:
        parsed = urlparse(
            str(url).strip()
        )

        if not parsed.netloc:
            return str(url).strip().lower()

        return (
            f"{parsed.scheme.lower()}://"
            f"{parsed.netloc.lower()}"
            f"{parsed.path.rstrip('/')}"
        ).rstrip("/")

    except Exception:
        return str(url).strip().lower()


def _tokenize(text: str) -> set[str]:
    """Simple deterministic tokenizer."""

    return {
        token
        for token in re.findall(
            r"\b[a-z0-9]{2,}\b",
            text.lower(),
        )
    }


def _text_similarity(
    left: str,
    right: str,
) -> float:
    """
    Calculate lightweight token Jaccard similarity.

    This is only used for obvious duplicate/related-source detection.
    """

    left_tokens = _tokenize(left)
    right_tokens = _tokenize(right)

    if not left_tokens or not right_tokens:
        return 0.0

    intersection = len(
        left_tokens & right_tokens
    )

    union = len(
        left_tokens | right_tokens
    )

    if union == 0:
        return 0.0

    return intersection / union


# ============================================================
# RAG NORMALIZATION
# ============================================================

def _normalize_rag_result(
    result: dict,
    index: int,
) -> dict:
    """
    Normalize a local RAG result into the unified evidence schema.

    Supports common fields used by the existing retrieval service.
    """

    # Different retrieval implementations may use slightly
    # different names, so support the common variants.
    text = _clean_text(
        result.get("text")
        or result.get("content")
        or result.get("chunk")
        or result.get("document")
        or ""
    )

    metadata = result.get(
        "metadata",
        {},
    )

    if not isinstance(
        metadata,
        dict,
    ):
        metadata = {}

    title = _clean_text(
        result.get("title")
        or metadata.get("title")
        or metadata.get("document_name")
        or metadata.get("filename")
        or "Local legal document"
    )

    page = (
        result.get("page")
        or metadata.get("page")
        or metadata.get("page_number")
    )

    chunk_id = (
        result.get("chunk_id")
        or metadata.get("chunk_id")
        or metadata.get("id")
    )

    score = (
        result.get("score")
        or result.get("similarity")
        or result.get("relevance_score")
    )

    return {
        "evidence_id": f"rag-{index}",
        "source_kind": "rag",
        "source_type": "rag",
        "title": title,
        "url": _clean_text(
            result.get("url")
            or metadata.get("url")
            or ""
        ),
        "text": text,
        "page": page,
        "chunk_id": chunk_id,
        "retrieval_score": score,
        "authority_score": 1.0,
        "freshness_score": None,
        "legal_event_score": None,
        "primary_source_score": 1.0,
        "commentary_score": 0.0,
        "date_metadata": {},
        "source_metadata": metadata,
        "topic_key": _clean_text(
            metadata.get("topic_key")
            or title
        ).lower(),
    }


# ============================================================
# WEB NORMALIZATION
# ============================================================

def _normalize_web_result(
    result: dict,
    index: int,
) -> dict:
    """
    Normalize a ranked web result into the unified evidence schema.
    """

    ranking = result.get(
        "ranking",
        {},
    )

    if not isinstance(
        ranking,
        dict,
    ):
        ranking = {}

    date_metadata = result.get(
        "date_metadata",
        {},
    )

    if not isinstance(
        date_metadata,
        dict,
    ):
        date_metadata = {}

    source_metadata = result.get(
        "source_metadata",
        {},
    )

    if not isinstance(
        source_metadata,
        dict,
    ):
        source_metadata = {}

    title = _clean_text(
        result.get("title")
        or "Web source"
    )

    content = _clean_text(
        result.get("content")
        or result.get("text")
        or ""
    )

    url = _clean_text(
        result.get("url")
        or ""
    )

    source_type = (
        source_metadata.get("source_type")
        or "general"
    )

    authority_score = ranking.get(
        "authority_score",
        0.0,
    )

    freshness_score = ranking.get(
        "freshness_score",
        0.0,
    )

    legal_event_score = ranking.get(
        "legal_event_score",
        0.0,
    )

    primary_source_score = ranking.get(
        "primary_source_score",
        0.0,
    )

    commentary_score = ranking.get(
        "commentary_score",
        0.0,
    )

    final_score = ranking.get(
        "final_score",
        0.0,
    )

    return {
        "evidence_id": f"web-{index}",
        "source_kind": "web",
        "source_type": source_type,
        "title": title,
        "url": url,
        "text": content,
        "page": None,
        "chunk_id": None,
        "retrieval_score": final_score,
        "authority_score": authority_score,
        "freshness_score": freshness_score,
        "legal_event_score": legal_event_score,
        "primary_source_score": primary_source_score,
        "commentary_score": commentary_score,
        "date_metadata": date_metadata,
        "source_metadata": source_metadata,
        "topic_key": _clean_text(
            source_metadata.get("topic_key")
            or title
        ).lower(),
    }


# ============================================================
# DEDUPLICATION
# ============================================================

def _deduplicate_evidence(
    evidence: list[dict],
) -> list[dict]:
    """
    Remove obvious duplicate evidence.

    URLs are preferred for web sources.
    Text similarity is used as a secondary safeguard.
    """

    seen_urls: set[str] = set()
    unique: list[dict] = []

    for item in evidence:

        url = _normalize_url(
            item.get("url")
        )

        # ----------------------------------------------------
        # Exact URL duplicate
        # ----------------------------------------------------

        if url:

            if url in seen_urls:
                continue

            seen_urls.add(
                url
            )

        text = _clean_text(
            item.get("text")
        )

        duplicate_text = False

        # ----------------------------------------------------
        # Avoid repeated large text snippets.
        # ----------------------------------------------------

        if text:

            for existing in unique:

                existing_text = _clean_text(
                    existing.get("text")
                )

                similarity = _text_similarity(
                    text,
                    existing_text,
                )

                if (
                    similarity >= 0.92
                    and len(text) >= 100
                    and len(existing_text) >= 100
                ):
                    duplicate_text = True
                    break

        if duplicate_text:
            continue

        unique.append(
            item
        )

    return unique


# ============================================================
# SOURCE GROUPING
# ============================================================

def _group_evidence(
    evidence: list[dict],
) -> dict[str, list[dict]]:
    """
    Group evidence by broad source category.
    """

    groups = {
        "primary": [],
        "legal_reporting": [],
        "commentary": [],
        "general": [],
        "rag": [],
    }

    for item in evidence:

        source_type = item.get(
            "source_type",
            "general",
        )

        if source_type not in groups:
            source_type = "general"

        groups[source_type].append(
            item
        )

    # RAG takes its own category even though its
    # legal-document nature may be primary.
    return groups


# ============================================================
# RELATED-SOURCE DETECTION
# ============================================================

def _related(
    left: dict,
    right: dict,
) -> bool:
    """
    Detect whether two sources are obviously related.
    """

    left_topic = _clean_text(
        left.get("topic_key")
    ).lower()

    right_topic = _clean_text(
        right.get("topic_key")
    ).lower()

    if (
        left_topic
        and right_topic
        and left_topic == right_topic
    ):
        return True

    left_title = _clean_text(
        left.get("title")
    )

    right_title = _clean_text(
        right.get("title")
    )

    if _text_similarity(
        left_title,
        right_title,
    ) >= 0.55:
        return True

    return False


def _build_related_groups(
    evidence: list[dict],
) -> list[dict]:
    """
    Build simple related-source groups.
    """

    groups: list[dict] = []
    assigned: set[str] = set()

    for item in evidence:

        evidence_id = item.get(
            "evidence_id"
        )

        if evidence_id in assigned:
            continue

        related_items = [
            item
        ]

        assigned.add(
            evidence_id
        )

        for candidate in evidence:

            candidate_id = candidate.get(
                "evidence_id"
            )

            if candidate_id in assigned:
                continue

            if _related(
                item,
                candidate,
            ):
                related_items.append(
                    candidate
                )
                assigned.add(
                    candidate_id
                )

        groups.append(
            {
                "group_id": f"group-{len(groups) + 1}",
                "evidence_ids": [
                    entry.get(
                        "evidence_id"
                    )
                    for entry in related_items
                ],
                "titles": [
                    entry.get(
                        "title"
                    )
                    for entry in related_items
                ],
            }
        )

    return groups


# ============================================================
# CONFLICT SIGNALS
# ============================================================

CONFLICT_PATTERNS = [
    r"\boverruled\b",
    r"\breversed\b",
    r"\bdissent\b",
    r"\bdiffered\b",
    r"\bcontrary\b",
    r"\binconsistent\b",
    r"\bconflict\b",
    r"\bdispute\b",
    r"\bdisagreed\b",
    r"\bchallenged\b",
]


def _conflict_signal(
    item: dict,
) -> float:
    """
    Detect explicit textual conflict language.

    This does NOT determine that sources actually conflict.
    It only identifies language worth further verification.
    """

    text = " ".join(
        [
            _clean_text(
                item.get("title")
            ),
            _clean_text(
                item.get("text")
            ),
        ]
    ).lower()

    hits = 0

    for pattern in CONFLICT_PATTERNS:

        if re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        ):
            hits += 1

    return min(
        hits * 0.20,
        1.0,
    )


def _detect_conflicts(
    evidence: list[dict],
) -> list[dict]:
    """
    Produce candidate conflict signals.

    We only flag cases for further verification. We do not claim
    that the legal sources are actually contradictory.
    """

    conflicts: list[dict] = []

    # --------------------------------------------------------
    # Textual conflict signals
    # --------------------------------------------------------

    for item in evidence:

        signal = _conflict_signal(
            item
        )

        if signal >= 0.20:

            conflicts.append(
                {
                    "type": "textual_conflict_signal",
                    "evidence_ids": [
                        item.get(
                            "evidence_id"
                        )
                    ],
                    "score": round(
                        signal,
                        4,
                    ),
                    "reason": (
                        "Source contains language "
                        "associated with legal disagreement "
                        "or competing interpretations."
                    ),
                }
            )

    # --------------------------------------------------------
    # Same-topic source disagreement candidates
    # --------------------------------------------------------

    for index, left in enumerate(
        evidence
    ):

        for right in evidence[index + 1:]:

            if not _related(
                left,
                right,
            ):
                continue

            left_type = left.get(
                "source_type"
            )

            right_type = right.get(
                "source_type"
            )

            # Primary vs commentary is not itself a conflict.
            # This is only a signal when both sources contain
            # strong legal-event language that may differ.
            left_event = (
                left.get(
                    "legal_event_score"
                )
                or 0.0
            )

            right_event = (
                right.get(
                    "legal_event_score"
                )
                or 0.0
            )

            if (
                left_event >= 0.40
                and right_event >= 0.40
            ):

                conflicts.append(
                    {
                        "type": "related_legal_event",
                        "evidence_ids": [
                            left.get(
                                "evidence_id"
                            ),
                            right.get(
                                "evidence_id"
                            ),
                        ],
                        "score": round(
                            min(
                                left_event,
                                right_event,
                            ),
                            4,
                        ),
                        "reason": (
                            "Multiple sources appear to "
                            "discuss the same legal event. "
                            "Further claim-level comparison "
                            "may be required."
                        ),
                    }
                )

    return conflicts


# ============================================================
# EVIDENCE SORTING
# ============================================================

def _evidence_sort_key(
    item: dict,
) -> tuple[float, float, float, float]:
    """
    Rank evidence inside the unified bundle.

    Priority:
        source authority
        primary-source strength
        retrieval score
        freshness
    """

    return (
        float(
            item.get(
                "authority_score"
            )
            or 0.0
        ),
        float(
            item.get(
                "primary_source_score"
            )
            or 0.0
        ),
        float(
            item.get(
                "retrieval_score"
            )
            or 0.0
        ),
        float(
            item.get(
                "freshness_score"
            )
            or 0.0
        ),
    )


# ============================================================
# PUBLIC API
# ============================================================

def build_evidence_bundle(
    rag_results: list[dict] | None = None,
    web_results: list[dict] | None = None,
    query: str = "",
) -> dict:
    """
    Build a structured evidence bundle from RAG and web results.

    Returns a stable structure for the Prompt Service / Groq layer.
    """

    rag_results = rag_results or []
    web_results = web_results or []

    evidence: list[dict] = []

    # --------------------------------------------------------
    # Normalize RAG
    # --------------------------------------------------------

    for index, result in enumerate(
        rag_results,
        start=1,
    ):

        if not isinstance(
            result,
            dict,
        ):
            continue

        normalized = _normalize_rag_result(
            result,
            index,
        )

        if not normalized.get(
            "text"
        ):
            continue

        evidence.append(
            normalized
        )

    # --------------------------------------------------------
    # Normalize WEB
    # --------------------------------------------------------

    for index, result in enumerate(
        web_results,
        start=1,
    ):

        if not isinstance(
            result,
            dict,
        ):
            continue

        normalized = _normalize_web_result(
            result,
            index,
        )

        if not normalized.get(
            "text"
        ):
            continue

        evidence.append(
            normalized
        )

    # --------------------------------------------------------
    # Deduplicate
    # --------------------------------------------------------

    evidence = _deduplicate_evidence(
        evidence
    )

    # --------------------------------------------------------
    # Sort strongest evidence first
    # --------------------------------------------------------

    evidence.sort(
        key=_evidence_sort_key,
        reverse=True,
    )

    # --------------------------------------------------------
    # Groups
    # --------------------------------------------------------

    groups = _group_evidence(
        evidence
    )

    related_groups = _build_related_groups(
        evidence
    )

    # --------------------------------------------------------
    # Conflict signals
    # --------------------------------------------------------

    conflicts = _detect_conflicts(
        evidence
    )

    # --------------------------------------------------------
    # Add evidence indices
    # --------------------------------------------------------

    for index, item in enumerate(
        evidence,
        start=1,
    ):
        item["evidence_index"] = index

    # --------------------------------------------------------
    # Bundle
    # --------------------------------------------------------

    return {
        "query": query,
        "evidence": evidence,
        "primary_sources": groups["primary"],
        "legal_reporting": groups["legal_reporting"],
        "commentary": groups["commentary"],
        "general_sources": groups["general"],
        "rag_evidence": groups["rag"],
        "related_groups": related_groups,
        "conflicts": conflicts,
        "counts": {
            "total": len(evidence),
            "rag": len(groups["rag"]),
            "primary": len(groups["primary"]),
            "legal_reporting": len(
                groups["legal_reporting"]
            ),
            "commentary": len(
                groups["commentary"]
            ),
            "general": len(
                groups["general"]
            ),
            "conflicts": len(conflicts),
        },
    }