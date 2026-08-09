from app.db.mongodb import document_collection

from app.services.retrieval_service import (
    retrieve_relevant_chunks,
)

from app.services.prompt_service import (
    build_legal_prompt,
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
# QUESTION
# =========================================================

query = input(
    "\nAsk a legal question: "
)


# =========================================================
# RETRIEVE
# =========================================================

chunks = retrieve_relevant_chunks(
    query=query,
    user_id=user_id,
    limit=5,
)


# =========================================================
# BUILD PROMPT
# =========================================================

prompt = build_legal_prompt(
    query=query,
    retrieved_chunks=chunks,
)


# =========================================================
# DISPLAY PROMPT
# =========================================================

print()
print("==============================")
print("GENERATED GROQ PROMPT")
print("==============================")
print()

print(prompt)