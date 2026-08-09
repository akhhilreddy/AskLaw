# =========================================================
# BUILD GROUNDED LEGAL PROMPT
# =========================================================

def build_legal_prompt(
    query: str,
    retrieved_chunks: list,
):
    # -----------------------------------------------------
    # Build the source context
    # -----------------------------------------------------

    context_parts = []

    for index, chunk in enumerate(
        retrieved_chunks,
        start=1,
    ):
        filename = chunk.get(
            "filename",
            "Unknown document",
        )

        page_number = chunk.get(
            "page_number"
        )

        text = chunk.get(
            "text",
            "",
        )

        if page_number:
            source = (
                f"{filename}, "
                f"page {page_number}"
            )
        else:
            source = filename

        context_parts.append(
            f"""
SOURCE {index}
Source: {source}

{text}
"""
        )

    context = "\n".join(
        context_parts
    )

    # -----------------------------------------------------
    # Build the final prompt
    # -----------------------------------------------------

    prompt = f"""
You are AskLaw, an AI assistant for
educational and informational legal research.

Use ONLY the provided source material
to answer the user's question.

Do not invent facts, laws, sections,
cases, or legal conclusions.

If the provided sources do not contain
enough information to answer the question,
clearly say that the available documents
do not provide enough information.

When possible, identify the relevant
document and page in your answer.

USER QUESTION:
{query}

SOURCE MATERIAL:
{context}

IMPORTANT:
This response is for educational and
informational purposes only. It does not
constitute legal advice and should not be
treated as a substitute for advice from
a qualified lawyer.

Provide a clear, concise answer based
on the source material above.
"""

    return prompt