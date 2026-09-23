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

CONTRADICTION_CONTEXT_THRESHOLD = 0.60
MATERIAL_COVERAGE_THRESHOLD = 0.72

TOKEN_EQUIVALENTS = {
    "apex": "supreme",
    "judiciary": "court",
    "courts": "court",
    "writs": "writ",
    "rights": "right",
    "remedies": "remedy",
    "relief": "remedy",
    "reliefs": "remedy",
    "grants": "issue",
    "grant": "issue",
    "granted": "issue",
    "issuing": "issue",
    "issued": "issue",
    "protect": "enforce",
    "protects": "enforce",
    "protecting": "enforce",
    "protected": "enforce",
    "enforcement": "enforce",
    "provides": "provide",
    "provided": "provide",
    "providing": "provide",
    "guarantee": "provide",
    "guarantees": "provide",
    "guaranteed": "provide",
    "confers": "provide",
    "conferred": "provide",
    "requires": "require",
    "required": "require",
    "requiring": "require",
}

MATERIAL_QUALIFIERS = {
    "all",
    "always",
    "automatic",
    "automatically",
    "each",
    "every",
    "exclusive",
    "exclusively",
    "mandatory",
    "must",
    "never",
    "only",
    "specific",
    "unlimited",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
}

LEGAL_FACT_PATTERNS = (
    r"\barticle\s+\d+[A-Za-z]?\b",
    r"\bsection\s+\d+[A-Za-z]?\b",
    r"\bclause\s*\(?\d+[A-Za-z]?\)?",
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
        "source",
        "an",
    }

    tokens = re.findall(
        r"\b[a-z0-9]{2,}\b",
        text.lower(),
    )

    normalized_tokens = set()

    for token in tokens:

        if token in stop_words:
            continue

        token = TOKEN_EQUIVALENTS.get(
            token,
            token,
        )

        if token.endswith("ies") and len(token) > 4:
            token = f"{token[:-3]}y"

        elif (
            token.endswith("s")
            and not token.endswith("ss")
            and len(token) > 4
        ):
            token = token[:-1]

        normalized_tokens.add(
            token
        )

    return normalized_tokens


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

    articles = {
        f"article {value}"
        for value in re.findall(
            r"\barticle\s+(\d+[a-z]?)\b",
            text,
        )
    }

    sections = {
        f"section {value}"
        for value in re.findall(
            r"\bsection\s+(\d+[a-z]?)\b",
            text,
        )
    }

    clauses = {
        f"clause {value}"
        for value in re.findall(
            r"\bclause\s*\(?\s*(\d+[a-z]?)\s*\)?",
            text,
        )
    }

    chapters = {
        f"chapter {value}"
        for value in re.findall(
            r"\bchapter\s+([ivxlcdm]+|\d+[a-z]?)\b",
            text,
        )
    }

    parts = {
        f"part {value}"
        for value in re.findall(
            r"\bpart\s+([ivxlcdm]+|\d+[a-z]?)\b",
            text,
        )
    }

    act_years = {
        f"act {value}"
        for value in re.findall(
            r"\bact\s*,?\s*(?:of\s+)?((?:18|19|20)\d{2})\b",
            text,
        )
    }

    act_years.update(
        {
            f"act {value}"
            for value in re.findall(
                r"\b((?:18|19|20)\d{2})\s+act\b",
                text,
            )
        }
    )

    return {
        "articles": articles,
        "sections": sections,
        "clauses": clauses,
        "chapters": chapters,
        "parts": parts,
        "act_years": act_years,
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
        - Clause, Chapter, Part, and an Act's explicit year are
          checked in the same way.

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

    for category in (
        "clauses",
        "chapters",
        "parts",
        "act_years",
    ):

        if not claim_ids[category]:
            continue

        matched = (
            claim_ids[category]
            & evidence_ids[category]
        )

        score_parts.append(
            len(matched)
            / len(claim_ids[category])
        )

    if not score_parts:
        return 0.0

    return sum(score_parts) / len(
        score_parts
    )


def _evidence_propositions(
    text: str,
) -> list[str]:
    """Split evidence into small proposition-sized comparison units."""

    text = _clean_text(
        text
    )

    if not text:
        return []

    return [
        _clean_text(part)
        for part in re.split(
            r"(?<=[.!?;])\s+|\n+",
            text,
        )
        if _clean_text(part)
    ]


def _mask_legal_identifiers(
    text: str,
) -> str:
    """Remove legal identifiers so their numbers do not look factual."""

    patterns = (
        r"\barticle\s+\d+[a-z]?\b",
        r"\bsection\s+\d+[a-z]?\b",
        r"\bclause\s*\(?\s*\d+[a-z]?\s*\)?",
        r"\bchapter\s+(?:[ivxlcdm]+|\d+[a-z]?)\b",
        r"\bpart\s+(?:[ivxlcdm]+|\d+[a-z]?)\b",
        r"\bact\s*,?\s*(?:of\s+)?(?:18|19|20)\d{2}\b",
        r"\b(?:18|19|20)\d{2}\s+act\b",
    )

    masked = text

    for pattern in patterns:
        masked = re.sub(
            pattern,
            " ",
            masked,
            flags=re.IGNORECASE,
        )

    return masked


def _mask_reference_numbers(
    text: str,
) -> str:
    """Remove page, case, petition, and citation numbers."""

    patterns = (
        r"\bpage\s+\d+(?:\s*[-–]\s*\d+)?\b",
        r"\b(?:case|petition|appeal|application|diary)\s+"
        r"(?:no\.?|number)?\s*\d+(?:[/-]\d+)*\b",
        r"\b(?:no\.|nos\.|number)\s*\d+(?:[/-]\d+)*\b",
        r"\b(?:slp|w\.p\.|wp|c\.a\.|ia|i\.a\.)\s*"
        r"(?:\([a-z]+\))?\s*(?:no\.?)?\s*\d+(?:[/-]\d+)*\b",
    )

    masked = text

    for pattern in patterns:
        masked = re.sub(
            pattern,
            " ",
            masked,
            flags=re.IGNORECASE,
        )

    return masked


def _proposition_tokens(
    text: str,
) -> set[str]:
    """Return the non-identifier, non-numeric meaning of a proposition."""

    text = _mask_legal_identifiers(
        text
    )

    text = _mask_reference_numbers(
        text
    )

    text = re.sub(
        r"\b\d+(?:,\d{3})*(?:\.\d+)?%?\b",
        " ",
        text,
    )

    return _tokenize(
        text
    )


def _context_similarity(
    claim_text: str,
    evidence_text: str,
) -> tuple[float, int]:
    """Compare propositions without letting identifiers drive overlap."""

    claim_tokens = _proposition_tokens(
        claim_text
    )

    evidence_tokens = _proposition_tokens(
        evidence_text
    )

    if not claim_tokens:
        return 0.0, 0

    overlap = len(
        claim_tokens
        & evidence_tokens
    )

    return (
        overlap / len(claim_tokens),
        overlap,
    )


def _has_legal_identifier_contradiction(
    claim: str,
    evidence_text: str,
) -> bool:
    """Detect a wrong provision attached to the same proposition."""

    claim_ids = _extract_legal_identifiers(
        claim
    )

    propositions = _evidence_propositions(
        evidence_text
    )

    for category, expected in claim_ids.items():

        if not expected:
            continue

        matching_identifier_found = False
        conflicting_identifier_found = False

        for proposition in propositions:

            actual = _extract_legal_identifiers(
                proposition
            )[category]

            if not actual:
                continue

            context_score, overlap = _context_similarity(
                claim,
                proposition,
            )

            if (
                context_score
                < CONTRADICTION_CONTEXT_THRESHOLD
                or overlap < 2
            ):
                continue

            if expected & actual:
                matching_identifier_found = True

            elif expected.isdisjoint(actual):
                conflicting_identifier_found = True

        if (
            conflicting_identifier_found
            and not matching_identifier_found
        ):
            return True

    return False


def _normalize_numeric_value(
    value: str,
) -> str:
    """Normalize a numeric expression for deterministic comparison."""

    return re.sub(
        r"[\s,]",
        "",
        value.lower(),
    )


def _extract_numeric_facts(
    text: str,
) -> list[dict[str, Any]]:
    """Extract material numeric values with proposition context."""

    facts: list[dict[str, Any]] = []

    prepared_text = _mask_reference_numbers(
        _mask_legal_identifiers(
            text
        )
    )

    for proposition in _evidence_propositions(
        prepared_text
    ):

        masked = proposition

        occupied: list[tuple[int, int]] = []

        for match in re.finditer(
            r"\b\d{1,2}[/-]\d{1,2}[/-](?:18|19|20)\d{2}\b",
            masked,
        ):

            facts.append(
                {
                    "kind": "date",
                    "value": _normalize_numeric_value(
                        match.group(0)
                    ),
                    "context": proposition,
                }
            )

            occupied.append(
                match.span()
            )

        for match in re.finditer(
            r"\b(?:18|19|20)\d{2}\b",
            masked,
        ):

            facts.append(
                {
                    "kind": "year",
                    "value": match.group(0),
                    "context": proposition,
                }
            )

            occupied.append(
                match.span()
            )

        for match in re.finditer(
            r"\b\d+(?:,\d{3})*(?:\.\d+)?%?\b",
            masked,
        ):

            if any(
                start <= match.start() < end
                for start, end in occupied
            ):
                continue

            value = match.group(0)

            facts.append(
                {
                    "kind": (
                        "percentage"
                        if value.endswith("%")
                        else "number"
                    ),
                    "value": _normalize_numeric_value(
                        value
                    ),
                    "context": proposition,
                }
            )

    return facts


def _has_numeric_contradiction(
    claim: str,
    evidence_text: str,
) -> bool:
    """Detect conflicting values only for the same factual proposition."""

    claim_facts = _extract_numeric_facts(
        claim
    )

    evidence_facts = _extract_numeric_facts(
        evidence_text
    )

    for claim_fact in claim_facts:

        relevant: list[dict[str, Any]] = []

        for evidence_fact in evidence_facts:

            if evidence_fact["kind"] != claim_fact["kind"]:
                continue

            context_score, overlap = _context_similarity(
                claim_fact["context"],
                evidence_fact["context"],
            )

            if (
                context_score
                >= CONTRADICTION_CONTEXT_THRESHOLD
                and overlap >= 2
            ):
                relevant.append(
                    evidence_fact
                )

        if not relevant:
            continue

        if any(
            item["value"] == claim_fact["value"]
            for item in relevant
        ):
            continue

        return True

    return False


def _has_unsupported_numeric_fact(
    claim: str,
    evidence_text: str,
) -> bool:
    """Detect a material claim number absent from matching evidence."""

    claim_facts = _extract_numeric_facts(
        claim
    )

    evidence_facts = _extract_numeric_facts(
        evidence_text
    )

    for claim_fact in claim_facts:

        supported = False

        for evidence_fact in evidence_facts:

            if (
                evidence_fact["kind"] != claim_fact["kind"]
                or evidence_fact["value"] != claim_fact["value"]
            ):
                continue

            context_score, overlap = _context_similarity(
                claim_fact["context"],
                evidence_fact["context"],
            )

            claim_context = _proposition_tokens(
                claim_fact["context"]
            )

            evidence_context = _proposition_tokens(
                evidence_fact["context"]
            )

            if (
                (
                    context_score
                    >= CONTRADICTION_CONTEXT_THRESHOLD
                    and overlap >= 2
                )
                or (
                    claim_context == evidence_context
                    and overlap >= 1
                )
                or (
                    not claim_context
                    and not evidence_context
                )
            ):
                supported = True
                break

        if not supported:
            return True

    return False


def _has_material_unsupported_addition(
    claim: str,
    evidence_text: str,
) -> bool:
    """Detect important claim detail missing from otherwise related evidence."""

    claim_tokens = _proposition_tokens(
        claim
    )

    evidence_tokens = _proposition_tokens(
        evidence_text
    )

    if not claim_tokens:
        return False

    matched = claim_tokens & evidence_tokens
    unmatched = claim_tokens - evidence_tokens
    coverage = len(matched) / len(
        claim_tokens
    )

    if unmatched & MATERIAL_QUALIFIERS:
        return len(matched) >= 2

    return (
        len(matched) >= 2
        and len(unmatched) >= 2
        and coverage < MATERIAL_COVERAGE_THRESHOLD
    )


def _has_explicit_contradiction(
    claim: str,
    evidence: dict,
) -> bool:
    """Return whether one evidence item clearly contradicts the claim."""

    evidence_text = _evidence_text(
        evidence
    )

    return (
        _has_numeric_contradiction(
            claim,
            evidence_text,
        )
        or _has_legal_identifier_contradiction(
            claim,
            evidence_text,
        )
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

    if (
        overlap == 1
        and len(claim_tokens) >= 3
    ):
        return PARTIAL_SUPPORT_THRESHOLD - 0.001

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
            "clauses",
            "chapters",
            "parts",
            "act_years",
        )
    )

    # --------------------------------------------------------
    # Claims containing explicit legal identifiers.
    # --------------------------------------------------------

    if has_explicit_identifier:

        # Mismatched explicit identifiers should strongly
        # reduce support.
        if identifier_score == 0.0:
            score = min(
                overlap * 0.45,
                1.0,
            )

        else:
            score = min(
                0.65 * overlap
                + 0.35 * identifier_score,
                1.0,
            )

            if identifier_score < 1.0:
                score = min(
                    score,
                    STRONG_SUPPORT_THRESHOLD - 0.001,
                )

    else:

        # ----------------------------------------------------
        # Generic factual/general claim.
        # ----------------------------------------------------

        score = min(
            overlap,
            1.0,
        )

    # --------------------------------------------------------
    # Deterministic contradiction and completeness guards.
    # --------------------------------------------------------

    if _has_numeric_contradiction(
        claim,
        evidence_text,
    ):
        return 0.0

    if _has_legal_identifier_contradiction(
        claim,
        evidence_text,
    ):
        return 0.0

    if (
        score >= STRONG_SUPPORT_THRESHOLD
        and _has_unsupported_numeric_fact(
            claim,
            evidence_text,
        )
    ):
        return STRONG_SUPPORT_THRESHOLD - 0.001

    if (
        score >= STRONG_SUPPORT_THRESHOLD
        and _has_material_unsupported_addition(
            claim,
            evidence_text,
        )
    ):
        return STRONG_SUPPORT_THRESHOLD - 0.001

    return score


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

        explicit_contradiction = any(
            _has_explicit_contradiction(
                claim,
                item,
            )
            for item in evidence
        )

        if (
            explicit_contradiction
            and best_score < STRONG_SUPPORT_THRESHOLD
        ):
            best_score = 0.0
            support = "unsupported"

        else:
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
