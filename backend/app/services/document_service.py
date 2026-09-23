from datetime import datetime, timezone

from bson import ObjectId
from fastapi import UploadFile, HTTPException, status
from pypdf import PdfReader

from app.core.config import settings
from app.db.mongodb import document_collection

from app.tasks.document_tasks import (
    index_document,
)
from app.services.vector_service import delete_document_chunks


# =========================================================
# CHUNK SETTINGS
# =========================================================

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150


def validate_upload(file: UploadFile) -> str:
    """Validate upload metadata and return a storage-safe display filename."""

    raw_filename = (file.filename or "").strip()

    if not raw_filename:
        raise HTTPException(status_code=400, detail="File name is required")

    if any(ord(character) < 32 for character in raw_filename):
        raise HTTPException(status_code=400, detail="File name is invalid")

    filename = raw_filename.replace("\\", "/").rsplit("/", 1)[-1].strip()

    if (
        not filename
        or filename.lower() == ".pdf"
        or len(filename) > 255
        or not filename.lower().endswith(".pdf")
    ):
        raise HTTPException(status_code=400, detail="A valid PDF file name is required")

    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    size = getattr(file, "size", None)
    stream = getattr(file, "file", None)

    if size is None and stream is not None:
        try:
            stream.seek(0, 2)
            size = stream.tell()
            stream.seek(0)
        except (AttributeError, OSError):
            size = None

    if size is not None and size > settings.MAX_DOCUMENT_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="PDF exceeds the configured upload size limit",
        )

    file.filename = filename
    return filename


# =========================================================
# GET OWNED DOCUMENT
# =========================================================

def get_owned_document(
    document_id: str,
    user_id: str,
):
    try:
        object_id = ObjectId(
            document_id
        )
    except Exception:
        return None

    return document_collection.find_one(
        {
            "_id": object_id,
            "user_id": user_id,
        },
        {
            "filename": 1,
            "status": 1,
        },
    )


# =========================================================
# LIST USER DOCUMENTS
# =========================================================

def get_user_documents(
    user_id: str,
):
    document_collection.update_many(
        {
            "user_id": user_id,
            "status": {
                "$exists": False,
            },
        },
        {
            "$set": {
                "status": "uploaded",
            }
        },
    )

    documents = document_collection.find(
        {
            "user_id": user_id,
        },
        {
            "filename": 1,
            "content_type": 1,
            "content": 1,
            "page_count": 1,
            "chunk_count": 1,
            "status": 1,
            "uploaded_at": 1,
        },
    ).sort(
        [
            ("uploaded_at", -1),
            ("_id", -1),
        ]
    )

    results = []

    for document in documents:
        content = document.get(
            "content",
            "",
        )

        item = {
            "document_id": str(
                document["_id"]
            ),
            "filename": document.get(
                "filename"
            ),
            "content_type": document.get(
                "content_type"
            ),
            "page_count": document.get(
                "page_count"
            ),
            "character_count": len(
                content
            ),
            "chunk_count": document.get(
                "chunk_count"
            ),
            "status": document.get(
                "status",
                "uploaded",
            ),
        }

        if document.get(
            "uploaded_at"
        ) is not None:
            item["uploaded_at"] = document[
                "uploaded_at"
            ]

        results.append(
            item
        )

    return results


# =========================================================
# DELETE OWNED DOCUMENT
# =========================================================

def delete_owned_document(
    document_id: str,
    user_id: str,
):
    """
    Delete vectors before the MongoDB record so a vector cleanup failure
    remains visible and retryable through the same endpoint.
    """

    try:
        object_id = ObjectId(document_id)
    except Exception:
        return None

    document = document_collection.find_one(
        {
            "_id": object_id,
            "user_id": user_id,
        },
        {
            "filename": 1,
            "status": 1,
        },
    )

    if not document:
        return None

    if document.get("status") in {"uploaded", "processing"}:
        raise HTTPException(
            status_code=409,
            detail="This document is still being indexed. Try deleting it after processing finishes.",
        )

    try:
        delete_document_chunks(
            document_id=document_id,
            user_id=user_id,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="Document vectors could not be removed. The document was not deleted.",
        ) from exc

    result = document_collection.delete_one(
        {
            "_id": object_id,
            "user_id": user_id,
        }
    )

    if result.deleted_count == 0:
        return None

    return {
        "message": "Document deleted successfully",
        "document_id": document_id,
        "filename": document.get("filename"),
    }


# =========================================================
# CREATE CHUNKS FOR ONE PAGE
# =========================================================

def create_page_chunks(
    text: str,
    page_number: int,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
):
    text = text.strip()

    if not text:
        return []

    chunks = []

    start = 0
    text_length = len(text)

    while start < text_length:
        end = start + chunk_size

        chunk_text = text[start:end].strip()

        if chunk_text:
            chunks.append(
                {
                    "text": chunk_text,
                    "page_number": page_number,
                }
            )

        if end >= text_length:
            break

        start = end - overlap

    return chunks


# =========================================================
# SAVE UPLOADED PDF
# =========================================================

def save_uploaded_document(
    file: UploadFile,
    user_id: str,
):
    filename = validate_upload(file)

    # -----------------------------------------------------
    # Read PDF
    # -----------------------------------------------------

    try:
        reader = PdfReader(file.file)

    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Could not read PDF. The file may be malformed or unsupported.",
        ) from None

    if len(reader.pages) > settings.MAX_DOCUMENT_PAGES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="PDF exceeds the configured page limit",
        )

    # -----------------------------------------------------
    # Extract text page by page
    # -----------------------------------------------------

    full_text_parts = []
    all_chunks = []
    extracted_text_bytes = 0

    for page_index, page in enumerate(
        reader.pages
    ):
        try:
            page_text = page.extract_text()

        except Exception:
            page_text = None

        if not page_text:
            continue

        page_number = page_index + 1

        page_text = page_text.strip()

        if page_text:
            extracted_text_bytes += len(page_text.encode("utf-8"))

            if extracted_text_bytes > settings.MAX_DOCUMENT_TEXT_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail="PDF contains too much extracted text",
                )

            full_text_parts.append(
                page_text
            )

        page_chunks = create_page_chunks(
            text=page_text,
            page_number=page_number,
        )

        all_chunks.extend(
            page_chunks
        )

    # -----------------------------------------------------
    # COMBINE FULL DOCUMENT TEXT
    # -----------------------------------------------------

    full_text = "\n\n".join(
        full_text_parts
    ).strip()

    # -----------------------------------------------------
    # MAKE SURE TEXT WAS EXTRACTED
    # -----------------------------------------------------

    if not full_text:
        raise HTTPException(
            status_code=400,
            detail=(
                "Could not extract text from this PDF. "
                "The PDF may contain scanned images "
                "instead of selectable text."
            ),
        )

    # -----------------------------------------------------
    # ADD CHUNK INDEXES
    # -----------------------------------------------------

    chunk_documents = []

    for index, chunk in enumerate(
        all_chunks
    ):
        chunk_documents.append(
            {
                "index": index,
                "page_number": chunk[
                    "page_number"
                ],
                "text": chunk[
                    "text"
                ],
            }
        )

    # -----------------------------------------------------
    # SAVE DOCUMENT TO MONGODB
    # -----------------------------------------------------

    document = {
        "user_id": user_id,
        "filename": filename,
        "content_type": file.content_type,
        "status": "uploaded",
        "content": full_text,
        "page_count": len(
            reader.pages
        ),
        "chunks": chunk_documents,
        "chunk_count": len(
            chunk_documents
        ),
        "uploaded_at": datetime.now(
            timezone.utc
        ),
    }

    result = document_collection.insert_one(
        document
    )

    # -----------------------------------------------------
    # GET DOCUMENT ID
    # -----------------------------------------------------

    document_id = str(
        result.inserted_id
    )

    # -----------------------------------------------------
    # SEND BACKGROUND INDEXING TASK
    # -----------------------------------------------------

    task = index_document.delay(
        document_id,
        user_id,
    )

    # -----------------------------------------------------
    # RESPONSE
    # -----------------------------------------------------

    return {
        "message": (
            "Document uploaded successfully. "
            "Indexing started in the background."
        ),
        "document_id": document_id,
        "task_id": task.id,
        "filename": filename,
        "page_count": len(
            reader.pages
        ),
        "character_count": len(
            full_text
        ),
        "chunk_count": len(
            chunk_documents
        ),
    }
