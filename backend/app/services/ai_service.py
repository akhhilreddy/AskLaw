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
        yield (
            "I couldn't find a user question "
            "to answer."
        )
        return

    # -----------------------------------------------------
    # BUILD RAG PROMPT
    # -----------------------------------------------------

    rag_prompt, retrieved_chunks = (
        build_rag_prompt(
            query=user_message,
            user_id=user_id,
            limit=5,
        )
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
    # STREAM RESPONSE
    # -----------------------------------------------------

    for chunk in stream:
        content = (
            chunk.choices[0].delta.content
        )

        if content:
            yield content