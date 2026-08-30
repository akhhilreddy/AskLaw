import json

from groq import Groq

from app.core.config import Settings

from app.services.rag_service import (
    build_rag_prompt,
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

When no document context is available,
do not fabricate legal information.

Responses are for educational and
informational purposes only.

They do not constitute legal advice.
"""


# =========================================================
# BUILD SOURCE METADATA
# =========================================================

def build_sources(
    retrieved_chunks,
):
    """
    Build source metadata from the actual
    retrieved Qdrant chunks.

    IMPORTANT:
    These values come from our backend,
    NOT from the LLM.
    """

    sources = []

    for chunk in retrieved_chunks:

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
        }

        sources.append(
            source
        )

    return sources


# =========================================================
# STREAM RESPONSE
# =========================================================

def stream_response(
    messages,
    user_id,
):

    # -----------------------------------------------------
    # FIND LATEST USER QUESTION
    # -----------------------------------------------------

    user_message = None

    for message in reversed(messages):

        if message.role == "user":

            user_message = (
                message.content
            )

            break

    # -----------------------------------------------------
    # SAFETY CHECK
    # -----------------------------------------------------

    if not user_message:

        error_event = {
            "type": "error",
            "content": (
                "I couldn't find a user question "
                "to answer."
            ),
        }

        yield (
            json.dumps(error_event)
            + "\n"
        )

        return

    # -----------------------------------------------------
    # BUILD RAG PROMPT
    # -----------------------------------------------------

    rag_result = build_rag_prompt(
        query=user_message,
        user_id=user_id,
        limit=5,
    )

    # -----------------------------------------------------
    # EXTRACT RAG DATA
    # -----------------------------------------------------

    rag_prompt = rag_result.get(
        "prompt"
    )

    retrieved_chunks = rag_result.get(
        "sources",
        [],
    )

    # -----------------------------------------------------
    # BUILD REAL SOURCE METADATA
    #
    # These sources come directly from
    # our retrieval pipeline.
    #
    # The LLM does NOT generate them.
    # -----------------------------------------------------

    sources = build_sources(
        retrieved_chunks
    )

    # =====================================================
    # BUILD GROQ MESSAGES
    # =====================================================

    if not rag_prompt:

        # -------------------------------------------------
        # NO DOCUMENT CONTEXT
        # -------------------------------------------------

        groq_messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            }
        ]

        # Preserve conversation history
        # when no RAG context exists.

        for message in messages:

            groq_messages.append(
                {
                    "role": message.role,
                    "content": message.content,
                }
            )

    else:

        # -------------------------------------------------
        # DOCUMENT-GROUNDED RESPONSE
        # -------------------------------------------------

        groq_messages = [
            {
                "role": "system",
                "content": rag_prompt,
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

        stream = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=groq_messages,
            temperature=0.2,
            max_completion_tokens=2048,
            stream=True,
        )

    except Exception as e:

        error_event = {
            "type": "error",
            "content": (
                f"AI service error: {str(e)}"
            ),
        }

        yield (
            json.dumps(error_event)
            + "\n"
        )

        return

    # =====================================================
    # STREAM RESPONSE TOKENS
    # =====================================================

    for chunk in stream:

        if not chunk.choices:
            continue

        content = (
            chunk.choices[0]
            .delta
            .content
        )

        if not content:
            continue

        token_event = {
            "type": "token",
            "content": content,
        }

        yield (
            json.dumps(token_event)
            + "\n"
        )

    # =====================================================
    # SEND REAL SOURCES
    # =====================================================
    #
    # IMPORTANT:
    #
    # The source information below is generated
    # by our Python backend from Qdrant results.
    #
    # It is NOT generated by Groq.
    #
    # Therefore if Groq says:
    #
    #   "page 95, chunk 253"
    #
    # but Qdrant actually returned:
    #
    #   "page 50, chunk 114"
    #
    # our frontend still receives the real
    # source metadata.
    #
    # =====================================================

    if sources:

        source_event = {
            "type": "sources",
            "sources": sources,
        }

        yield (
            json.dumps(source_event)
            + "\n"
        )