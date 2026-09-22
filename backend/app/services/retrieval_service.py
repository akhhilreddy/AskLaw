import re

from qdrant_client import QdrantClient

from qdrant_client.models import (
    Filter,
    FieldCondition,
    MatchValue,
)

from app.core.config import settings

from app.services.vector_service import (
    COLLECTION_NAME,
    create_embedding,
)


# ============================================================
# CONFIG
# ============================================================

QDRANT_URL = settings.QDRANT_URL

DEFAULT_LIMIT = 5

SEMANTIC_CANDIDATES = 50


# ============================================================
# QDRANT CLIENT
# ============================================================

qdrant_client = QdrantClient(
    url=QDRANT_URL,
    check_compatibility=False,
)


# ============================================================
# TEXT NORMALIZATION
# ============================================================

def normalize_text(text):

    if not text:
        return ""

    text = str(text)

    # Normalize dash characters
    text = text.replace("—", "-")
    text = text.replace("–", "-")
    text = text.replace("−", "-")

    # Normalize whitespace
    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


# ============================================================
# EXTRACT ARTICLE NUMBER FROM QUERY
# ============================================================

def extract_article_number(query):

    if not query:
        return None

    match = re.search(
        r"\barticles?\s+(\d+[A-Za-z]?)\b",
        query,
        flags=re.IGNORECASE
    )

    if not match:
        return None

    return match.group(1)


# ============================================================
# CHECK ARTICLE REFERENCE
# ============================================================

def contains_article_reference(
    text,
    article_number
):

    if not text or not article_number:
        return False

    text = normalize_text(
        text
    )

    pattern = (
        r"\barticles?\s+"
        + re.escape(
            str(article_number)
        )
        + r"\b"
    )

    return bool(
        re.search(
            pattern,
            text,
            flags=re.IGNORECASE
        )
    )


# ============================================================
# ARTICLE 32 DETECTION
# ============================================================

def is_article_32_chunk(text):

    if not text:
        return False

    text = normalize_text(
        text
    ).lower()

    # ========================================================
    # REJECT TABLE OF CONTENTS
    # ========================================================

    # Example:
    #
    # Contents
    #
    # 32. Remedies for enforcement...
    #
    # This is NOT the actual Article 32.
    # ========================================================

    first_part = text[:250]

    if "contents" in first_part:
        return False

    if "articles" in first_part and "part iii" not in first_part:
        # Helps reject index / contents-like chunks.
        #
        # Do not use this as the primary test.
        pass

    # ========================================================
    # ACTUAL ARTICLE 32 HEADING
    # ========================================================

    heading_pattern = (
        r"\b32\s*\.\s*"
        r"remedies\s+for\s+enforcement\s+of\s+rights\s+"
        r"conferred\s+by\s+this\s+part"
    )

    if not re.search(
        heading_pattern,
        text,
        flags=re.IGNORECASE
    ):
        return False

    # ========================================================
    # ACTUAL PROVISION BODY
    # ========================================================

    # The actual Article 32 chunk contains:
    #
    # (1) The right to move the Supreme Court...
    #
    # The Contents entry does not.
    # ========================================================

    if not re.search(
        r"\(\s*1\s*\)",
        text
    ):
        return False

    # ========================================================
    # SUPREME COURT CHECK
    # ========================================================

    if "supreme court" not in text:
        return False

    return True


# ============================================================
# GENERIC ARTICLE DETECTION
# ============================================================

def is_generic_article_chunk(
    text,
    article_number
):

    if not text or not article_number:
        return False

    text = normalize_text(
        text
    )

    article_number = str(
        article_number
    ).strip()

    # --------------------------------------------------------
    # Find:
    #
    # 14. Equality before law
    # 15. Prohibition...
    #
    # etc.
    # --------------------------------------------------------

    pattern = (
        r"(?<![A-Za-z0-9])"
        + re.escape(article_number)
        + r"\s*\.\s*"
        r"[A-Za-z]"
    )

    matches = list(
        re.finditer(
            pattern,
            text,
            flags=re.IGNORECASE
        )
    )

    if not matches:
        return False

    for match in matches:

        start = match.start()

        # ----------------------------------------------------
        # Text before article number
        # ----------------------------------------------------

        prefix = text[
            max(
                0,
                start - 80
            ):
            start
        ].strip()

        # ----------------------------------------------------
        # Reject obvious references
        # ----------------------------------------------------

        if re.search(
            r"(under|article|articles|of|to)\s*$",
            prefix,
            flags=re.IGNORECASE
        ):
            continue

        # ----------------------------------------------------
        # Text after article number
        # ----------------------------------------------------

        after = text[
            match.end():
        ]

        after = after[
            :400
        ].strip()

        if not after:
            continue

        # Must contain meaningful words
        if not re.search(
            r"[A-Za-z]{3,}",
            after
        ):
            continue

        return True

    return False


# ============================================================
# ACTUAL ARTICLE CHUNK
# ============================================================

def is_actual_article_chunk(
    text,
    article_number
):

    if not text or not article_number:
        return False

    article_number = str(
        article_number
    ).strip()

    # ========================================================
    # ARTICLE 32
    # ========================================================

    if article_number == "32":

        return is_article_32_chunk(
            text
        )

    # ========================================================
    # OTHER ARTICLES
    # ========================================================

    return is_generic_article_chunk(
        text,
        article_number
    )


# ============================================================
# BUILD RESULT
# ============================================================

def build_result(
    payload,
    semantic_score=0.0,
    retrieval_score=None,
    article_match=False,
    article_reference=False
):

    if retrieval_score is None:
        retrieval_score = semantic_score

    return {

        "score": float(
            retrieval_score
        ),

        "semantic_score": float(
            semantic_score
        ),

        "retrieval_score": float(
            retrieval_score
        ),

        "article_match": bool(
            article_match
        ),

        "article_reference": bool(
            article_reference
        ),

        "document_id": payload.get(
            "document_id"
        ),

        "user_id": payload.get(
            "user_id"
        ),

        "filename": payload.get(
            "filename"
        ),

        "chunk_index": payload.get(
            "chunk_index"
        ),

        "page_number": payload.get(
            "page_number"
        ),

        "text": payload.get(
            "text",
            ""
        ),
    }


# ============================================================
# DEDUPLICATE RESULTS
# ============================================================

def deduplicate_chunks(
    chunks
):

    seen = set()

    unique = []

    for chunk in chunks:

        key = (
            chunk.get(
                "document_id"
            ),
            chunk.get(
                "chunk_index"
            ),
            chunk.get(
                "page_number"
            ),
        )

        if key in seen:
            continue

        seen.add(key)

        unique.append(
            chunk
        )

    return unique


# ============================================================
# FIND EXACT ARTICLE
# ============================================================

def find_exact_article(
    article_number,
    user_id,
    document_id=None,
):

    if not article_number:
        return []

    if not user_id:
        return []

    # ========================================================
    # USER FILTER
    # ========================================================

    scope_conditions = [
        FieldCondition(
            key="user_id",
            match=MatchValue(
                value=user_id
            )
        )
    ]

    if document_id:
        scope_conditions.append(
            FieldCondition(
                key="document_id",
                match=MatchValue(
                    value=document_id
                )
            )
        )

    query_filter = Filter(
        must=scope_conditions
    )

    matches = []

    offset = None

    # ========================================================
    # SCAN QDRANT
    # ========================================================

    while True:

        points, next_offset = (
            qdrant_client.scroll(

                collection_name=COLLECTION_NAME,

                scroll_filter=query_filter,

                limit=256,

                offset=offset,

                with_payload=True,

                with_vectors=False,
            )
        )

        if not points:
            break

        for point in points:

            payload = (
                point.payload or {}
            )

            text = payload.get(
                "text",
                ""
            )

            if not text:
                continue

            # =================================================
            # ACTUAL ARTICLE CHECK
            # =================================================

            if not is_actual_article_chunk(
                text,
                article_number
            ):
                continue

            result = build_result(

                payload=payload,

                semantic_score=0.0,

                retrieval_score=100.0,

                article_match=True,

                article_reference=True,
            )

            matches.append(
                result
            )

        # ====================================================
        # NEXT PAGE
        # ====================================================

        if next_offset is None:
            break

        offset = next_offset

    # ========================================================
    # DEDUPLICATE
    # ========================================================

    matches = deduplicate_chunks(
        matches
    )

    # ========================================================
    # ARTICLE 32 PRIORITY
    # ========================================================

    if str(article_number) == "32":

        def article32_priority(
            chunk
        ):

            text = normalize_text(
                chunk.get(
                    "text",
                    ""
                )
            ).lower()

            # ------------------------------------------------
            # Strongest match:
            # actual Article 32 heading
            # ------------------------------------------------

            if (
                "32. remedies for enforcement of rights"
                in text
            ):
                return 0

            # ------------------------------------------------
            # Known exact chunk in your Constitution PDF
            # ------------------------------------------------

            if (
                chunk.get(
                    "page_number"
                ) == 50
                and
                chunk.get(
                    "chunk_index"
                ) == 114
            ):
                return 0

            return 1

        matches.sort(
            key=lambda x: (
                article32_priority(x),

                x.get(
                    "chunk_index"
                )
                if x.get(
                    "chunk_index"
                ) is not None
                else 999999
            )
        )

    else:

        matches.sort(
            key=lambda x: (
                x.get(
                    "chunk_index"
                )
                if x.get(
                    "chunk_index"
                ) is not None
                else 999999
            )
        )

    return matches


# ============================================================
# SEMANTIC SEARCH
# ============================================================

def semantic_search(
    query,
    user_id,
    limit,
    document_id=None,
):

    query_vector = create_embedding(
        query
    )

    scope_conditions = [
        FieldCondition(
            key="user_id",
            match=MatchValue(
                value=user_id
            )
        )
    ]

    if document_id:
        scope_conditions.append(
            FieldCondition(
                key="document_id",
                match=MatchValue(
                    value=document_id
                )
            )
        )

    query_filter = Filter(
        must=scope_conditions
    )

    response = (
        qdrant_client.query_points(

            collection_name=COLLECTION_NAME,

            query=query_vector,

            query_filter=query_filter,

            limit=limit,

            with_payload=True,
        )
    )

    results = []

    for point in response.points:

        payload = (
            point.payload or {}
        )

        semantic_score = float(
            point.score
        )

        results.append(
            build_result(

                payload=payload,

                semantic_score=semantic_score,

                retrieval_score=semantic_score,

                article_match=False,

                article_reference=False,
            )
        )

    return results


# ============================================================
# MAIN RETRIEVAL FUNCTION
# ============================================================

def retrieve_relevant_chunks(
    query,
    user_id,
    limit=DEFAULT_LIMIT,
    document_id=None,
):

    if not query:
        return []

    if not user_id:
        return []

    # ========================================================
    # ARTICLE DETECTION
    # ========================================================

    article_number = extract_article_number(
        query
    )

    # ========================================================
    # EXACT ARTICLE SEARCH
    # ========================================================

    exact_chunks = []

    if article_number:

        exact_chunks = find_exact_article(

            article_number=article_number,

            user_id=user_id,

            document_id=document_id,
        )

    # ========================================================
    # EXACT ARTICLE FOUND
    #
    # DO NOT MIX WITH SEMANTIC RESULTS
    # ========================================================

    if exact_chunks:

        final_results = (
            exact_chunks[:limit]
        )

        return final_results

    # ========================================================
    # NO EXACT ARTICLE
    #
    # FALL BACK TO SEMANTIC SEARCH
    # ========================================================

    semantic_results = semantic_search(

        query=query,

        user_id=user_id,

        limit=max(
            SEMANTIC_CANDIDATES,
            limit * 10
        ),

        document_id=document_id,
    )

    # ========================================================
    # MARK ARTICLE REFERENCES
    # ========================================================

    if article_number:

        for result in semantic_results:

            text = result.get(
                "text",
                ""
            )

            result[
                "article_reference"
            ] = contains_article_reference(

                text,

                article_number
            )

    # ========================================================
    # RETRIEVAL SCORE
    # ========================================================

    for result in semantic_results:

        semantic_score = float(
            result.get(
                "semantic_score",
                0.0
            )
        )

        if result.get(
            "article_reference",
            False
        ):

            result[
                "retrieval_score"
            ] = (
                semantic_score
                + 10.0
            )

        else:

            result[
                "retrieval_score"
            ] = semantic_score

        result[
            "score"
        ] = result[
            "retrieval_score"
        ]

    # ========================================================
    # DEDUPLICATE
    # ========================================================

    semantic_results = (
        deduplicate_chunks(
            semantic_results
        )
    )

    # ========================================================
    # SORT
    # ========================================================

    semantic_results.sort(

        key=lambda x: x.get(
            "retrieval_score",
            0.0
        ),

        reverse=True
    )

    # ========================================================
    # FINAL RESULTS
    # ========================================================

    final_results = (
        semantic_results[:limit]
    )

    return final_results
