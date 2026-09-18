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
                    user_message,
                    user_id,
                )
            )
        )

    except Exception as exc:

        print()
        print("=" * 60)
        print("ASKLAW RETRIEVAL ERROR")
        print("=" * 60)
        print(
            str(exc)
        )
        print("=" * 60)

        error_event = {
            "type": "error",
            "content": (
                f"Retrieval error: {str(exc)}"
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

    # =====================================================
    # DEBUG
    # =====================================================

    print()
    print("=" * 60)
    print("ASKLAW AI PIPELINE")
    print("=" * 60)

    print(
        "QUERY:",
        user_message,
    )

    print(
        "ROUTE:",
        route,
    )

    print(
        "RAG RESULTS:",
        len(rag_results),
    )

    print(
        "WEB RESULTS:",
        len(web_results),
    )

    print("=" * 60)

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

        print()
        print("=" * 60)
        print("ASKLAW EVIDENCE ERROR")
        print("=" * 60)
        print(
            str(exc)
        )
        print("=" * 60)

        error_event = {
            "type": "error",
            "content": (
                f"Evidence processing error: {str(exc)}"
            ),
        }

        yield (
            json.dumps(
                error_event
            )
            + "\n"
        )

        return

    print()
    print(
        "EVIDENCE BUNDLE:",
        evidence_bundle.get(
            "counts",
            {},
        ),
    )

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

        print()
        print("=" * 60)
        print("ASKLAW PROMPT ERROR")
        print("=" * 60)
        print(
            str(exc)
        )
        print("=" * 60)

        error_event = {
            "type": "error",
            "content": (
                f"Prompt error: {str(exc)}"
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
    # DEBUG SOURCES
    # =====================================================

    print()
    print(
        "BACKEND SOURCES:",
        len(sources),
    )

    for index, source in enumerate(
        sources,
        start=1,
    ):

        print(
            f"SOURCE {index}:",
            source,
        )

    print("=" * 60)

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

        print()
        print("=" * 60)
        print("ASKLAW GROQ ERROR")
        print("=" * 60)
        print(
            str(exc)
        )
        print("=" * 60)

        error_event = {
            "type": "error",
            "content": (
                f"AI service error: {str(exc)}"
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

        print()
        print("=" * 60)
        print("ASKLAW STREAM ERROR")
        print("=" * 60)
        print(
            str(exc)
        )
        print("=" * 60)

        error_event = {
            "type": "error",
            "content": (
                f"Streaming error: {str(exc)}"
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

    print()
    print("=" * 60)
    print("ASKLAW GENERATED ANSWER")
    print("=" * 60)
    print(
        generated_answer
    )
    print("=" * 60)

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

            print()
            print("=" * 60)
            print("ASKLAW VERIFICATION ERROR")
            print("=" * 60)
            print(
                str(exc)
            )
            print("=" * 60)

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

    print()
    print(
        "VERIFICATION SUMMARY:",
        verification.get(
            "summary",
            {},
        ),
    )

    print(
        "GROUNDING SCORE:",
        grounding_score,
    )

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

    # =====================================================
    # DEBUG COMPLETE
    # =====================================================

    print()
    print("=" * 60)
    print("ASKLAW AI RESPONSE COMPLETE")
    print("=" * 60)

    print(
        "ROUTE:",
        route,
    )

    print(
        "SOURCES:",
        len(sources),
    )

    print(
        "CLAIMS:",
        verification.get(
            "summary",
            {},
        ).get(
            "total_claims",
            0,
        ),
    )

    print(
        "GROUNDING SCORE:",
        grounding_score,
    )

    print("=" * 60)