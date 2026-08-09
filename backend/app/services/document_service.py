from datetime import datetime, timezone

from fastapi import UploadFile, HTTPException
from pypdf import PdfReader

from app.db.mongodb import document_collection


# =========================================================
# CHUNK SETTINGS
# =========================================================

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150


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
    # -----------------------------------------------------
    # Read PDF
    # -----------------------------------------------------

    try:
        reader = PdfReader(file.file)

    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Could not read PDF: {str(e)}",
        )

    # -----------------------------------------------------
    # Extract text page by page
    # -----------------------------------------------------

    full_text_parts = []
    all_chunks = []

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
    # Combine full document text
    # -----------------------------------------------------

    full_text = "\n\n".join(
        full_text_parts
    ).strip()

    # -----------------------------------------------------
    # Make sure text was extracted
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
    # Add chunk indexes
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
    # Save document
    # -----------------------------------------------------

    document = {
        "user_id": user_id,
        "filename": file.filename,
        "content_type": file.content_type,
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
    # Response
    # -----------------------------------------------------

    return {
        "message": "Document uploaded successfully",
        "document_id": str(
            result.inserted_id
        ),
        "filename": file.filename,
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