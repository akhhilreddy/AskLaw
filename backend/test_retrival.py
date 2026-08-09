from app.db.mongodb import document_collection

from app.services.retrieval_service import (
    retrieve_relevant_chunks,
)


# =========================================================
# FIND A USER WITH A DOCUMENT
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
    print(
        "No documents found."
    )
    raise SystemExit


user_id = document["user_id"]


# =========================================================
# ASK QUESTION
# =========================================================

query = input(
    "\nAsk a question about your documents: "
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
# DISPLAY
# =========================================================

print()
print("==============================")
print("RETRIEVED CHUNKS")
print("==============================")


for index, chunk in enumerate(
    chunks,
    start=1,
):
    print()
    print(
        f"Result #{index}"
    )

    print(
        f"Score: {chunk['score']}"
    )

    print(
        f"File: {chunk['filename']}"
    )

    print(
        f"Page: {chunk['page_number']}"
    )

    print(
        f"Chunk: {chunk['chunk_index']}"
    )

    print("Text:")

    print(
        chunk["text"]
    )

    print(
        "------------------------------"
    )