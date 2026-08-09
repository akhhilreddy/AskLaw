from app.db.mongodb import document_collection

from app.services.rag_service import (
    build_rag_prompt,
)


# =========================================================
# FIND A USER WITH DOCUMENTS
# =========================================================

document = document_collection.find_one(
    {
        "chunks": {
            "$exists": True,
            "$ne": [],
        }
    }
)


if not document:
    print("No documents found.")
    raise SystemExit


user_id = document["user_id"]


# =========================================================
# ASK QUESTION
# =========================================================

query = input(
    "\nAsk a legal question: "
)


# =========================================================
# BUILD RAG PROMPT
# =========================================================

prompt, chunks = build_rag_prompt(
    query=query,
    user_id=user_id,
    limit=5,
)


# =========================================================
# DISPLAY RESULTS
# =========================================================

if not prompt:
    print()
    print(
        "No relevant document chunks were found."
    )
    raise SystemExit


print()
print("==============================")
print("RAG PIPELINE")
print("==============================")

print(
    f"Retrieved chunks: {len(chunks)}"
)

print()
print("==============================")
print("PROMPT SENT TO LLM")
print("==============================")
print()

print(prompt)