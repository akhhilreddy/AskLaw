"""Owner-scoped adapter; never reconstruct page citations from overlapping chunks."""
import logging

from bson import ObjectId
from fastapi import HTTPException
from pydantic import ValidationError
from pymongo import timeout
from pymongo.errors import PyMongoError

from app.db.mongodb import document_collection
from app.schemas.agreement import AgreementText

logger = logging.getLogger(__name__)


def capture_pages(title, page_count, pages):
    """Additive upload metadata only; unsupported input still follows normal RAG."""
    try:
        document = AgreementText(document_id="pending", title=title,
                                 page_count=page_count, pages=pages)
    except ValidationError:
        return {"agreement_text_version": 1, "agreement_review_available": False}
    return {"agreement_text_version": 1, "agreement_review_available": True,
            "agreement_pages": [page.model_dump() for page in document.pages]}


def unavailable_reason(record):
    if record.get("status") != "indexed":
        return "Wait for indexing to finish; failed uploads must be uploaded again."
    if record.get("agreement_text_version") != 1:
        return "Re-upload this PDF to preserve exact page references for agreement review."
    if not record.get("agreement_review_available"):
        return "Needs readable text on every page, at most 50 pages and 100,000 characters. Scanned PDFs are unsupported."
    return None


def list_agreement_documents(user_id):
    try:
        with timeout(5):
            records = list(document_collection.find({"user_id": user_id}, {
                "filename": 1, "status": 1, "page_count": 1,
                "agreement_text_version": 1, "agreement_review_available": 1,
            }).sort([("uploaded_at", -1), ("_id", -1)]).limit(100))
    except PyMongoError:
        logger.warning("agreement_documents status=unavailable")
        raise HTTPException(503, "Document library is temporarily unavailable. Try again shortly.") from None
    return [{"document_id": str(record["_id"]), "filename": record.get("filename", "PDF"),
             "page_count": record.get("page_count"), "unavailable_reason": unavailable_reason(record)}
            for record in records]


def load_agreement_document(document_id, user_id):
    try:
        object_id = ObjectId(document_id)
    except Exception:
        raise HTTPException(404, "Document not found") from None
    try:
        with timeout(5):
            record = document_collection.find_one({"_id": object_id, "user_id": user_id}, {
                "filename": 1, "status": 1, "page_count": 1,
                "agreement_text_version": 1, "agreement_review_available": 1, "agreement_pages": 1,
            })
    except PyMongoError:
        logger.warning("agreement_document status=unavailable")
        raise HTTPException(503, "Document library is temporarily unavailable. Try again shortly.") from None
    if record is None:
        raise HTTPException(404, "Document not found")
    reason = unavailable_reason(record)
    if reason:
        raise HTTPException(409, reason)
    try:
        return AgreementText(document_id=str(object_id), title=record["filename"],
                             page_count=record["page_count"], pages=record.get("agreement_pages", []))
    except (ValidationError, KeyError):
        raise HTTPException(409, "Page text is incomplete or unsupported. Re-upload a text-based PDF.") from None
