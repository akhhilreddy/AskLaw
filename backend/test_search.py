from app.db.mongodb import document_collection

from app.services.vector_service import (
    search_similar_chunks,
)


# =========================================================
# FIND A USER
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
        "No indexed document found."
    )
    raise SystemExit


user_id = document["user_id"]


# =========================================================
# QUESTION
# =========================================================

query = input(
    "\nAsk a question about the document: "
)


# =========================================================
# SEARCH
# =========================================================

results = search_similar_chunks(
    query=query,
    user_id=user_id,
    limit=3,
)


# =========================================================
# DISPLAY RESULTS
# =========================================================

print("\n")
print("==============================")
print("SEARCH RESULTS")
print("==============================")


for index, result in enumerate(
    results,
    start=1,
):
    print()
    print(
        f"Result #{index}"
    )

    print(
        f"Score: {result.score}"
    )

    print(
        f"File: "
        f"{result.payload.get('filename')}"
    )

    print(
        f"Chunk: "
        f"{result.payload.get('chunk_index')}"
    )
    print(f"Page: "
    f"{result.payload.get('page_number')}"
    )
    print(
        "Text:"
        
    )

    print(
        result.payload.get("text")
    )

    print(
        "------------------------------"
    )