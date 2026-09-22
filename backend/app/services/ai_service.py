# =========================================================
# ASKLAW AI SERVICE
# =========================================================
#
# Complete answer-generation pipeline.
#
# FLOW:
#
#     USER QUESTION
#           ↓
#     RETRIEVAL ORCHESTRATOR
#           ↓
#      ┌────┼────┐
#      ↓    ↓    ↓
#     RAG  WEB HYBRID
#      └────┼────┘
#           ↓
#     EVIDENCE SERVICE
#           ↓
#     PROMPT SERVICE
#           ↓
#         GROQ
#           ↓
#      STREAM ANSWER
#           ↓
#     CLAIM VERIFIER
#           ↓
#   VERIFICATION METADATA
#           ↓
#   BACKEND SOURCE METADATA
#
# IMPORTANT:
#
# Source metadata and verification metadata are generated
# by the backend. The LLM never generates them.
# =========================================================


import asyncio
import json
import logging


from groq import Groq


from app.core.config import Settings


from app.services.retrieval_orchestrator import (
    retrieve_for_query,
)


from app.services.prompt_service import (
    build_legal_prompt,
)


from app.services.evidence_service import (
    build_evidence_bundle,
)


from app.services.claim_verifier import (
    verify_claims,
    calculate_grounding_score,
)


# =========================================================
# SETTINGS
# =========================================================

settings = Settings()
logger = logging.getLogger(__name__)


# =========================================================
# GROQ CLIENT
# =========================================================

client = Groq(
    api_key=settings.GROQ_API_KEY
)


# =========================================================
# FALLBACK SYSTEM PROMPT
# =========================================================

SYSTEM_PROMPT = """
You are AskLaw, an AI assistant for
educational and informational legal research.

Answer clearly and professionally.

When no source material is available,
do not fabricate legal information.

Responses are for educational and
informational purposes only.

They do not constitute legal advice.
"""


# =========================================================
# BUILD RAG SOURCE METADATA
# =========================================================

def build_sources(
    retrieved_chunks,
):
    """
    Build authoritative metadata from backend RAG
    retrieval results.

    The LLM does NOT generate this metadata.
    """

    sources = []

    if not retrieved_chunks:
        return sources

    for chunk in retrieved_chunks:

        if not isinstance(
            chunk,
            dict,
        ):
            continue

        source = {
            "document_id": chunk.get(
                "document_id"
            ),

            "filename": chunk.get(
                "filename"
            ),

            "page_number": chunk.get(
                "page_number"
            ),

            "chunk_index": chunk.get(
                "chunk_index"
            ),

            "score": chunk.get(
                "score"
            ),

            "source_type": "document",
        }

        sources.append(
            source
        )

    return sources


# =========================================================
# BUILD WEB SOURCE METADATA
# =========================================================

def build_web_sources(
    web_results,
):
    """
    Build authoritative metadata from web retrieval results.

    The LLM does NOT generate this metadata.
    """

    sources = []

    if not web_results:
        return sources

    for result in web_results:

        if not isinstance(
            result,
            dict,
        ):
            continue

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

        source = {
            "title": result.get(
                "title",
                "",
            ),

            "url": result.get(
                "url",
                "",
            ),

            "content": result.get(
                "content",
                "",
            ),

            "engine": result.get(
                "engine",
                "",
            ),

            "source_type": "web",

            "legal_source_type": source_metadata.get(
                "source_type"
            ),

            "source_type_confidence": source_metadata.get(
                "source_type_confidence"
            ),

            "authority_score": ranking.get(
                "authority_score"
            ),

            "relevance_score": ranking.get(
                "relevance_score"
            ),

            "freshness_score": ranking.get(
                "freshness_score"
            ),

            "legal_event_score": ranking.get(
                "legal_event_score"
            ),

            "primary_source_score": ranking.get(
                "primary_source_score"
            ),

            "commentary_score": ranking.get(
                "commentary_score"
            ),

            "final_score": ranking.get(
                "final_score"
            ),

            "date_metadata": date_metadata,
        }

        sources.append(
            source
        )

    return sources


# =========================================================
# FIND USER MESSAGE
# =========================================================

def _get_latest_user_message(
    messages,
):
    """
    Find the latest user message.
    """

    for message in reversed(
        messages
    ):

        if message.role == "user":

            return message.content

    return None


# =========================================================
# STREAM RESPONSE
# =========================================================

def stream_response(
    messages,
    user_id=None,
    document_id=None,
):
    """
    Complete AskLaw response pipeline.

    1. Extract user question.
    2. Route query.
    3. Retrieve RAG / WEB / HYBRID context.
    4. Build structured evidence bundle.
    5. Build grounded prompt.
    6. Call Groq.
    7. Stream tokens.
    8. Verify generated claims against evidence.
    9. Send backend-generated sources.
    10. Send verification metadata.
    11. Send route information.
    """

    # =====================================================
    # FIND USER QUESTION
    # =====================================================

    user_message = (
        _get_latest_user_message(
            messages
        )
    )

    # =====================================================
    # SAFETY CHECK
    # =====================================================

    if not user_message:

        error_event = {
            "type": "error",
            "content": (
                "I couldn't find a user question "
                "to answer."
            ),
        }

        yield (
            json.dumps(
                error_event
            )
            + "\n"
        )

        return

    # =====================================================
    # RETRIEVAL
    # =====================================================

    try:

        retrieval_result = (
            asyncio.run(
                retrieve_for_query(
                    query=user_message,
                    user_id=user_id,
                    document_id=document_id,
                )
            )
        )

    except Exception as exc:
        logger.exception("Research retrieval failed")

        error_event = {
            "type": "error",
            "content": (
                "Research retrieval failed. Please try again."
            ),
        }

        yield (
            json.dumps(
                error_event
            )
            + "\n"
        )

        return

    # =====================================================
    # EXTRACT RETRIEVAL RESULTS
    # =====================================================

    route = retrieval_result.get(
        "route",
        "rag",
    )

    rag_results = retrieval_result.get(
        "rag_results",
        [],
    )

    web_results = retrieval_result.get(
        "web_results",
        [],
    )

    logger.info(
        "Research retrieval completed route=%s rag_results=%s web_results=%s",
        route,
        len(rag_results),
        len(web_results),
    )

    # =====================================================
    # BUILD STRUCTURED EVIDENCE
    # =====================================================

    try:

        evidence_bundle = build_evidence_bundle(
            rag_results=rag_results,
            web_results=web_results,
            query=user_message,
        )

    except Exception as exc:
        logger.exception("Evidence processing failed")

        error_event = {
            "type": "error",
            "content": (
                "Evidence processing failed. Please try again."
            ),
        }

        yield (
            json.dumps(
                error_event
            )
            + "\n"
        )

        return

    # =====================================================
    # BUILD GROUNDED LEGAL PROMPT
    # =====================================================

    try:

        legal_prompt = build_legal_prompt(
            query=user_message,
            route=route,
            rag_results=rag_results,
            web_results=web_results,
            evidence_bundle=evidence_bundle,
        )

    except Exception as exc:
        logger.exception("Research prompt construction failed")

        error_event = {
            "type": "error",
            "content": (
                "The research prompt could not be prepared. Please try again."
            ),
        }

        yield (
            json.dumps(
                error_event
            )
            + "\n"
        )

        return

    # =====================================================
    # BUILD BACKEND SOURCE METADATA
    # =====================================================

    rag_sources = build_sources(
        rag_results
    )

    web_sources = build_web_sources(
        web_results
    )

    sources = (
        rag_sources
        + web_sources
    )

    # =====================================================
    # BUILD GROQ MESSAGES
    # =====================================================

    if legal_prompt:

        groq_messages = [
            {
                "role": "system",
                "content": legal_prompt,
            },
            {
                "role": "user",
                "content": user_message,
            },
        ]

    else:

        groq_messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": user_message,
            },
        ]

    # =====================================================
    # CALL GROQ
    # =====================================================

    try:

        stream = (
            client.chat.completions.create(
                model="openai/gpt-oss-120b",
                messages=groq_messages,
                temperature=0.2,
                max_completion_tokens=2048,
                stream=True,
            )
        )

    except Exception as exc:
        logger.exception("AI provider request failed")

        error_event = {
            "type": "error",
            "content": (
                "The AI service is temporarily unavailable. Please try again."
            ),
        }

        yield (
            json.dumps(
                error_event
            )
            + "\n"
        )

        return

    # =====================================================
    # STREAM GROQ TOKENS
    # =====================================================

    generated_answer_parts = []

    try:

        for chunk in stream:

            if not chunk.choices:
                continue

            content = (
                chunk
                .choices[0]
                .delta
                .content
            )

            if not content:
                continue

            generated_answer_parts.append(
                content
            )

            token_event = {
                "type": "token",
                "content": content,
            }

            yield (
                json.dumps(
                    token_event
                )
                + "\n"
            )

    except Exception as exc:
        logger.exception("AI response streaming failed")

        error_event = {
            "type": "error",
            "content": (
                "The response stream was interrupted. Please try again."
            ),
        }

        yield (
            json.dumps(
                error_event
            )
            + "\n"
        )

        return

    # =====================================================
    # FULL GENERATED ANSWER
    # =====================================================

    generated_answer = "".join(
        generated_answer_parts
    ).strip()

    # =====================================================
    # CLAIM VERIFICATION
    # =====================================================

    verification = {
        "claims": [],
        "summary": {
            "total_claims": 0,
            "supported_claims": 0,
            "partial_claims": 0,
            "unsupported_claims": 0,
            "legal_claims": 0,
        },
    }

    grounding_score = 0.0

    if generated_answer:

        try:

            verification = verify_claims(
                answer=generated_answer,
                evidence=evidence_bundle.get(
                    "evidence",
                    [],
                ),
            )

            grounding_score = (
                calculate_grounding_score(
                    verification
                )
            )

        except Exception as exc:
            logger.exception("Claim verification failed")

            verification = {
                "claims": [],
                "summary": {
                    "total_claims": 0,
                    "supported_claims": 0,
                    "partial_claims": 0,
                    "unsupported_claims": 0,
                    "legal_claims": 0,
                },
                "error": str(exc),
            }

            grounding_score = 0.0

    # =====================================================
    # SEND BACKEND SOURCE METADATA
    # =====================================================

    if sources:

        source_event = {
            "type": "sources",
            "sources": sources,
        }

        yield (
            json.dumps(
                source_event
            )
            + "\n"
        )

    # =====================================================
    # SEND CLAIM VERIFICATION
    # =====================================================

    verification_event = {
        "type": "verification",
        "grounding_score": grounding_score,
        "summary": verification.get(
            "summary",
            {},
        ),
        "claims": verification.get(
            "claims",
            [],
        ),
    }

    yield (
        json.dumps(
            verification_event
        )
        + "\n"
    )

    # =====================================================
    # SEND RETRIEVAL ROUTE
    # =====================================================

    route_event = {
        "type": "route",
        "route": route,
    }

    yield (
        json.dumps(
            route_event
        )
        + "\n"
    )

    logger.info(
        "AI response completed route=%s sources=%s claims=%s grounding_score=%s",
        route,
        len(sources),
        verification.get("summary", {}).get("total_claims", 0),
        grounding_score,
    )
