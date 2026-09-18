"""
AskLaw Claim Verifier

Verifies whether claims in an LLM-generated answer are supported
by retrieved evidence.

Design goals:

    - deterministic
    - no web requests
    - no additional LLM call
    - lightweight and fast
    - suitable for the current AskLaw MVP

Pipeline:

    Answer
      ↓
    Claim extraction
      ↓
    Claim normalization
      ↓
    Claim → evidence similarity
      ↓
    Support classification
      ↓
    Verification report

Important:

This service provides an evidence-support signal. It does NOT make
a legal determination about whether a claim is legally correct.
"""

from __future__ import annotations

import re
from typing import Any


# ============================================================
# CONFIGURATION
# ============================================================

MIN_CLAIM_LENGTH = 12

STRONG_SUPPORT_THRESHOLD = 0.42
PARTIAL_SUPPORT_THRESHOLD = 0.20

LEGAL_FACT_PATTERNS = (
    r"\barticle\s+\d+[A-Za-z]?\b",
    r"\bsection\s+\d+[A-Za-z]?\b",
    r"\bchapter\s+[IVXLC]+\b",
    r"\bpart\s+[IVXLC]+\b",
    r"\b(?:supreme|high)\s+court\b",
    r"\bjudgment\b",
    r"\bjudgement\b",
    r"\bruling\b",
    r"\border\b",
    r"\bpetition\b",
    r"\bcase\b",
    r"\bsection\b",
    r"\bact\b",
    r"\bconstitution\b",
    r"\bpenalty\b",
    r"\bsentence\b",
    r"\bpunishment\b",
    r"\bfundamental\s+right\b",
)


# ============================================================
# TEXT NORMALIZATION
# ============================================================

def _clean_text(value: Any) -> str:
    """Normalize arbitrary text into a compact string."""

    if value is None:
        return ""

    text = str(value)

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


def _tokenize(text: str) -> set[str]:
    """
    Lightweight tokenizer.

    Removes common stop words so content-word overlap is more useful.
    """

    stop_words = {
        "the",
        "a",
        "an",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "of",
        "to",
        "in",
        "on",
        "for",
        "from",
        "and",
        "or",
        "but",
        "with",
        "by",
        "as",
        "at",
        "it",
        "this",
        "that",
        "these",
        "those",
        "under",
        "into",
        "than",
        "their",
        "its",
        "has",
        "have",
        "had",
        "can",
        "may",
        "might",
        "will",
        "would",
        "should",
        "could",
        "about",
        "an",
    }

    tokens = re.findall(
        r"\b[a-z0-9]{2,}\b",
        text.lower(),
    )

    return {
        token
        for token in tokens
        if token not in stop_words
    }


# ============================================================
# CLAIM SPLITTING
# ============================================================

def _split_sentences(
    answer: str,
) -> list[str]:
    """
    Split an answer into sentence-like claims.

    Handles:
        - normal sentences
        - markdown bullets
        - numbered items
        - common legal abbreviations
        - sentence boundaries after ., ?, !

    Important:
        Common abbreviations such as "v.", "vs.", "No." and
        "e.g." are protected before sentence splitting.
    """

    answer = _clean_text(
        answer
    )

    if not answer:
        return []

    # --------------------------------------------------------
    # Normalize markdown bullets and numbered items.
    # --------------------------------------------------------

    answer = re.sub(
        r"(?:^|\n)\s*(?:[-*•]|\d+[.)])\s+",
        "\n",
        answer,
    )

    # --------------------------------------------------------
    # Protect common abbreviations containing periods.
    # --------------------------------------------------------

    protected = {
        "e.g.": "ASKLAW_EG_PLACEHOLDER",
        "i.e.": "ASKLAW_IE_PLACEHOLDER",
        "etc.": "ASKLAW_ETC_PLACEHOLDER",
        "vs.": "ASKLAW_VS_PLACEHOLDER",
        "v.": "ASKLAW_V_PLACEHOLDER",
        "no.": "ASKLAW_NO_PLACEHOLDER",
        "nos.": "ASKLAW_NOS_PLACEHOLDER",
        "u.s.": "ASKLAW_US_PLACEHOLDER",
        "dr.": "ASKLAW_DR_PLACEHOLDER",
        "mr.": "ASKLAW_MR_PLACEHOLDER",
        "mrs.": "ASKLAW_MRS_PLACEHOLDER",
        "prof.": "ASKLAW_PROF_PLACEHOLDER",
    }

    protected_text = answer

    for original, replacement in protected.items():
        protected_text = re.sub(
            re.escape(original),
            replacement,
            protected_text,
            flags=re.IGNORECASE,
        )

    # --------------------------------------------------------
    # Split on sentence-ending punctuation followed by
    # whitespace.
    # --------------------------------------------------------

    parts = re.split(
        r"(?<=[.!?])\s+",
        protected_text,
    )

    claims: list[str] = []

    for part in parts:

        claim = _clean_text(
            part
        )

        if not claim:
            continue

        # ----------------------------------------------------
        # Restore abbreviations.
        # ----------------------------------------------------

        for original, replacement in protected.items():
            claim = claim.replace(
                replacement,
                original,
            )

        if len(claim) < MIN_CLAIM_LENGTH:
            continue

        claims.append(
            claim
        )

    return claims


# ============================================================
# CLAIM CLASSIFICATION
# ============================================================

def _is_legal_claim(
    claim: str,
) -> bool:
    """Detect whether a sentence contains obvious legal-fact signals."""

    for pattern in LEGAL_FACT_PATTERNS:

        if re.search(
            pattern,
            claim,
            flags=re.IGNORECASE,
        ):
            return True

    return False


def _claim_type(
    claim: str,
) -> str:
    """
    Classify a claim broadly.

    Types:

        legal
        factual
        general
    """

    if _is_legal_claim(
        claim
    ):
        return "legal"

    lower = claim.lower()

    if any(
        word in lower
        for word in (
            "according to",
            "reported",
            "published",
            "announced",
            "recent",
            "today",
            "yesterday",
            "in 2026",
            "in 2025",
        )
    ):
        return "factual"

    return "general"


# ============================================================
# EVIDENCE TEXT
# ============================================================

def _evidence_text(
    evidence: dict,
) -> str:
    """Build searchable evidence text."""

    return _clean_text(
        " ".join(
            [
                _clean_text(
                    evidence.get("title")
                ),
                _clean_text(
                    evidence.get("text")
                ),
            ]
        )
    )


# ============================================================
# LEGAL IDENTIFIERS
# ============================================================

def _extract_legal_identifiers(
    text: str,
) -> dict[str, set[str]]:
    """
    Extract explicit legal identifiers.

    These are given special treatment so that a generic word overlap
    does not incorrectly verify a claim containing a different
    Article, Section, or year.
    """

    text = text.lower()

    articles = set(
        re.findall(
            r"\barticle\s+\d+[a-z]?\b",
            text,
        )
    )

    sections = set(
        re.findall(
            r"\bsection\s+\d+[a-z]?\b",
            text,
        )
    )

    years = set(
        re.findall(
            r"\b20\d{2}\b",
            text,
        )
    )

    return {
        "articles": articles,
        "sections": sections,
        "years": years,
    }


def _identifier_consistency_score(
    claim: str,
    evidence_text: str,
) -> float:
    """
    Verify consistency of explicit legal identifiers.

    Rules:

        - If claim has an Article, evidence should contain the same
          Article to receive identifier support.
        - Same for Section.
        - If claim explicitly contains a year, evidence containing
          that same year receives support.

    If the claim contains none of these identifiers, returns 0.0.
    """

    claim_ids = _extract_legal_identifiers(
        claim
    )

    evidence_ids = _extract_legal_identifiers(
        evidence_text
    )

    score_parts: list[float] = []

    if claim_ids["articles"]:

        matched = (
            claim_ids["articles"]
            & evidence_ids["articles"]
        )

        score_parts.append(
            len(matched)
            / len(claim_ids["articles"])
        )

    if claim_ids["sections"]:

        matched = (
            claim_ids["sections"]
            & evidence_ids["sections"]
        )

        score_parts.append(
            len(matched)
            / len(claim_ids["sections"])
        )

    if claim_ids["years"]:

        matched = (
            claim_ids["years"]
            & evidence_ids["years"]
        )

        score_parts.append(
            len(matched)
            / len(claim_ids["years"])
        )

    if not score_parts:
        return 0.0

    return sum(score_parts) / len(
        score_parts
    )


# ============================================================
# CLAIM / EVIDENCE MATCHING
# ============================================================

def _overlap_score(
    claim: str,
    evidence_text: str,
) -> float:
    """Calculate token overlap between claim and evidence."""

    claim_tokens = _tokenize(
        claim
    )

    evidence_tokens = _tokenize(
        evidence_text
    )

    if not claim_tokens:
        return 0.0

    overlap = len(
        claim_tokens
        & evidence_tokens
    )

    return overlap / len(
        claim_tokens
    )


def _support_score(
    claim: str,
    evidence: dict,
) -> float:
    """
    Calculate claim/evidence support score.

    Uses:

        - content-word overlap
        - legal identifier consistency

    Explicit legal identifiers are important enough that a mismatch
    can prevent a strong support classification.
    """

    evidence_text = _evidence_text(
        evidence
    )

    if not evidence_text:
        return 0.0

    overlap = _overlap_score(
        claim,
        evidence_text,
    )

    identifier_score = (
        _identifier_consistency_score(
            claim,
            evidence_text,
        )
    )

    claim_identifiers = (
        _extract_legal_identifiers(
            claim
        )
    )

    has_explicit_identifier = any(
        claim_identifiers[key]
        for key in (
            "articles",
            "sections",
            "years",
        )
    )

    # --------------------------------------------------------
    # Claims containing explicit legal identifiers.
    # --------------------------------------------------------

    if has_explicit_identifier:

        # Mismatched explicit identifiers should strongly
        # reduce support.
        if identifier_score == 0.0:
            return min(
                overlap * 0.45,
                1.0,
            )

        return min(
            0.65 * overlap
            + 0.35 * identifier_score,
            1.0,
        )

    # --------------------------------------------------------
    # Generic factual/general claim.
    # --------------------------------------------------------

    return min(
        overlap,
        1.0,
    )


# ============================================================
# SUPPORT CLASSIFICATION
# ============================================================

def _classify_support(
    score: float,
) -> str:
    """Convert numerical support score into a category."""

    if score >= STRONG_SUPPORT_THRESHOLD:
        return "supported"

    if score >= PARTIAL_SUPPORT_THRESHOLD:
        return "partial"

    return "unsupported"


# ============================================================
# BEST EVIDENCE
# ============================================================

def _best_evidence(
    claim: str,
    evidence: list[dict],
) -> list[dict]:
    """Find strongest evidence items for a claim."""

    matches: list[dict] = []

    for item in evidence:

        score = _support_score(
            claim,
            item,
        )

        if score <= 0:
            continue

        matches.append(
            {
                "evidence_id": item.get(
                    "evidence_id"
                ),
                "title": item.get(
                    "title"
                ),
                "url": item.get(
                    "url"
                ),
                "source_type": item.get(
                    "source_type"
                ),
                "score": round(
                    score,
                    4,
                ),
            }
        )

    matches.sort(
        key=lambda item: (
            item["score"],
            item.get(
                "source_type"
            ) == "primary",
        ),
        reverse=True,
    )

    return matches[:3]


# ============================================================
# PUBLIC VERIFICATION FUNCTION
# ============================================================

def verify_claims(
    answer: str,
    evidence: list[dict] | None = None,
) -> dict:
    """
    Verify claims in an answer against evidence.

    Returns:

        {
            "claims": [...],
            "summary": {...}
        }
    """

    evidence = evidence or []

    claims = _split_sentences(
        answer
    )

    verified_claims: list[dict] = []

    for index, claim in enumerate(
        claims,
        start=1,
    ):

        matches = _best_evidence(
            claim,
            evidence,
        )

        best_score = (
            matches[0]["score"]
            if matches
            else 0.0
        )

        support = _classify_support(
            best_score
        )

        verified_claims.append(
            {
                "claim_id": f"claim-{index}",
                "claim": claim,
                "claim_type": _claim_type(
                    claim
                ),
                "support": support,
                "support_score": round(
                    best_score,
                    4,
                ),
                "evidence": matches,
            }
        )

    supported = sum(
        1
        for item in verified_claims
        if item["support"] == "supported"
    )

    partial = sum(
        1
        for item in verified_claims
        if item["support"] == "partial"
    )

    unsupported = sum(
        1
        for item in verified_claims
        if item["support"] == "unsupported"
    )

    legal_claims = sum(
        1
        for item in verified_claims
        if item["claim_type"] == "legal"
    )

    return {
        "claims": verified_claims,
        "summary": {
            "total_claims": len(
                verified_claims
            ),
            "supported_claims": supported,
            "partial_claims": partial,
            "unsupported_claims": unsupported,
            "legal_claims": legal_claims,
        },
    }


# ============================================================
# GROUNDING SCORE
# ============================================================

def calculate_grounding_score(
    verification: dict,
) -> float:
    """
    Calculate an overall grounding score.

    Supported:
        1.0

    Partial:
        0.5

    Unsupported:
        0.0
    """

    claims = verification.get(
        "claims",
        [],
    )

    if not claims:
        return 0.0

    score = 0.0

    for claim in claims:

        support = claim.get(
            "support"
        )

        if support == "supported":
            score += 1.0

        elif support == "partial":
            score += 0.5

    return round(
        score / len(claims),
        4,
    )