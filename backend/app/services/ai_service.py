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
You are AskLaw, an AI legal assistant.

Your job is to explain legal concepts
in simple language.

Rules:

- Answer clearly and professionally.
- Use headings and bullet points when helpful.
- Never claim to be a licensed lawyer.
- Do not provide fabricated legal information.
- Responses are for educational and
  informational purposes only.
- Responses do not constitute legal advice.
"""


# =========================================================
# BUILD SOURCE METADATA
# =========================================================

def build_sources(
    retrieved_chunks,
):
    """
    Convert retrieved chunks into clean
    source metadata for the frontend.
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

        sources.append(source)

    return sources


# =========================================================
# STREAM RESPONSE
# =========================================================

def stream_response(
    messages,
    user_id,
):

    # -----------------------------------------------------
    # FIND THE LATEST USER QUESTION
    # -----------------------------------------------------

    user_message = None

    for message in reversed(messages):

        if message.role == "user":

            user_message = message.content
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

    rag_prompt = rag_result["prompt"]

    retrieved_chunks = rag_result["sources"]

    # -----------------------------------------------------
    # BUILD CLEAN SOURCE METADATA
    # -----------------------------------------------------

    sources = build_sources(
        retrieved_chunks
    )

    # -----------------------------------------------------
    # IF NO DOCUMENTS WERE FOUND
    # -----------------------------------------------------

    if not rag_prompt:

        groq_messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            }
        ]

        for message in messages:

            groq_messages.append(
                {
                    "role": message.role,
                    "content": message.content,
                }
            )

    # -----------------------------------------------------
    # USE RETRIEVED LEGAL CONTEXT
    # -----------------------------------------------------

    else:

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

    # -----------------------------------------------------
    # CALL GROQ
    # -----------------------------------------------------

    stream = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=groq_messages,
        temperature=0.3,
        max_completion_tokens=2048,
        stream=True,
    )

    # -----------------------------------------------------
    # STREAM RESPONSE TOKENS
    # -----------------------------------------------------

    for chunk in stream:

        content = (
            chunk.choices[0].delta.content
        )

        if content:

            token_event = {
                "type": "token",
                "content": content,
            }

            yield (
                json.dumps(token_event)
                + "\n"
            )

    # -----------------------------------------------------
    # SEND SOURCES AFTER ANSWER
    # -----------------------------------------------------

    if sources:

        source_event = {
            "type": "sources",
            "sources": sources,
        }

        yield (
            json.dumps(source_event)
            + "\n"
        )