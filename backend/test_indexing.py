from app.db.mongodb import document_collection
from app.services.indexing_service import index_document


# =========================================================
# SHOW AVAILABLE CHUNKED DOCUMENTS
# =========================================================

documents = list(
    document_collection.find(
        {
            "chunks": {
                "$exists": True,
                "$ne": [],
            }
        },
        {
            "filename": 1,
            "chunk_count": 1,
            "user_id": 1,
        },
    )
)


if not documents:
    print(
        "No chunked documents found."
    )
    raise SystemExit


print()
print("==============================")
print("AVAILABLE DOCUMENTS")
print("==============================")


for index, document in enumerate(
    documents,
    start=1,
):
    print()
    print(
        f"[{index}] "
        f"{document.get('filename')}"
    )

    print(
        f"    Chunks: "
        f"{document.get('chunk_count', 0)}"
    )

    print(
        f"    ID: "
        f"{document['_id']}"
    )


# =========================================================
# SELECT DOCUMENT
# =========================================================

print()

choice = input(
    "Enter document number to index: "
).strip()


try:
    selected_index = int(choice) - 1
    document = documents[selected_index]

except (
    ValueError,
    IndexError,
):
    print(
        "Invalid document selection."
    )
    raise SystemExit


# =========================================================
# DOCUMENT DETAILS
# =========================================================

document_id = str(
    document["_id"]
)

user_id = document["user_id"]


print()
print("==============================")
print("SELECTED DOCUMENT")
print("==============================")

print(
    f"Filename: "
    f"{document['filename']}"
)

print(
    f"Document ID: "
    f"{document_id}"
)

print(
    f"Chunk count: "
    f"{document.get('chunk_count', 0)}"
)

print("==============================")


# =========================================================
# INDEX DOCUMENT
# =========================================================

success = index_document(
    document_id=document_id,
    user_id=user_id,
)


print()

if success:
    print(
        "Document indexed successfully in Qdrant."
    )
else:
    print(
        "Failed to index document."
    )