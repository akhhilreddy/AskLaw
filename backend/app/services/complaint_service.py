"""Deterministic complaint preparation, owned storage and live source checking."""
from datetime import datetime, timezone
from hashlib import sha256
import logging

from bson import ObjectId
from fastapi import HTTPException
from pymongo import timeout
from pymongo.errors import PyMongoError

from app.db.mongodb import complaint_collection
from app.schemas.complaint import ComplaintCase
from app.services.agreement_documents import load_agreement_document

logger = logging.getLogger(__name__)
DISCLAIMER = "AskLaw provides legal information, not legal advice. This is a user-reviewed complaint preparation pack, not a filed complaint or a legal opinion."


def _id(case_id):
    try:
        return ObjectId(case_id)
    except Exception:
        raise HTTPException(404, "Complaint not found") from None


def _db(operation):
    try:
        with timeout(5):
            return operation()
    except PyMongoError:
        logger.warning("complaint_storage status=unavailable")
        raise HTTPException(503, "Complaint workspace is temporarily unavailable. Try again shortly.") from None


def _public(record):
    return {"case_id": str(record["_id"]), "revision": record["revision"],
            "data": record["data"], "updated_at": record["updated_at"]}


def get_case(case_id, user_id):
    record = _db(lambda: complaint_collection.find_one({"_id": _id(case_id), "user_id": user_id}))
    if record is None:
        raise HTTPException(404, "Complaint not found")
    return _public(record)


def list_cases(user_id):
    records = _db(lambda: list(complaint_collection.find({"user_id": user_id}, {
        "data.title": 1, "data.issue_type": 1, "updated_at": 1, "revision": 1,
    }).sort([("updated_at", -1), ("_id", -1)]).limit(50)))
    return [{"case_id": str(item["_id"]), "title": item["data"]["title"],
             "revision": item["revision"], "updated_at": item["updated_at"]} for item in records]


def resolve_evidence(data, user_id, strict=True):
    """Persist references only. Recheck source ownership/status on each pack build."""
    documents, result = {}, []
    for reference in data.evidence:
        try:
            if reference.document_id not in documents:
                documents[reference.document_id] = load_agreement_document(reference.document_id, user_id)
            document = documents[reference.document_id]
            if reference.page_number > document.page_count:
                raise HTTPException(422, "Evidence page is outside the source document")
            page = document.pages[reference.page_number - 1]
            digest = sha256(page.text.encode()).hexdigest()
            if reference.page_text_sha256 != digest:
                raise HTTPException(422, "The source page changed. Select its excerpt again before saving.")
            if reference.end > len(page.text) or not page.text[reference.start:reference.end].strip():
                raise HTTPException(422, "Select a non-empty excerpt inside the source page")
            result.append({**reference.model_dump(), "available": True, "filename": document.title,
                "quote": page.text[reference.start:reference.end],
                "page_text_sha256": digest})
        except HTTPException as exc:
            if strict or exc.status_code not in {404, 409, 422}:
                raise
            result.append({"evidence_id": reference.evidence_id, "label": reference.label,
                           "category": reference.category, "available": False})
    return result


def save_case(data, user_id, case_id=None, revision=None):
    if case_id:
        existing = get_case(case_id, user_id)
        if existing["revision"] != revision:
            raise HTTPException(409, "This complaint changed in another tab. Reload before saving.")
    _db(lambda: resolve_evidence(data, user_id))  # Bound all source checks together.
    now = datetime.now(timezone.utc)
    payload = data.model_dump()
    if case_id is None:
        record = {"user_id": user_id, "revision": 1, "data": payload, "updated_at": now, "created_at": now}
        record["_id"] = _db(lambda: complaint_collection.insert_one(record)).inserted_id
    else:
        result = _db(lambda: complaint_collection.update_one({"_id": _id(case_id), "user_id": user_id, "revision": revision},
            {"$set": {"data": payload, "updated_at": now}, "$inc": {"revision": 1}}))
        if result.matched_count != 1:
            raise HTTPException(409, "This complaint changed or was deleted. Reload before saving.")
        record = {"_id": _id(case_id), "revision": revision + 1, "data": payload, "updated_at": now}
    return _public(record)


def delete_case(case_id, user_id, revision):
    current = get_case(case_id, user_id)
    if current["revision"] != revision:
        raise HTTPException(409, "This complaint changed. Reload before deleting.")
    result = _db(lambda: complaint_collection.delete_one({"_id": _id(case_id), "user_id": user_id, "revision": revision}))
    if result.deleted_count != 1:
        raise HTTPException(409, "This complaint changed or was deleted. Reload the workspace.")
    return {"deleted": True}


def _letter_event(event, references):
    """Compact, attributed chronology; full wording stays in timeline/excerpts.

    Do not paraphrase into legal conclusions or put a seller's 'we' in the
    complainant's voice. These are labelled records, not verified findings.
    """
    labels = {"purchase": "Purchase recorded", "delivery": "Delivery recorded",
              "problem": "Problem reported by me", "contact": "Contact with seller recorded",
              "response": "Seller response (as recorded)", "other": "Other event (as recorded)"}
    label = labels[event["kind"]]
    text = event["description"].strip()
    if event["kind"] in {"problem", "response", "other"} and len(text) <= 220:
        summary = f'{label}: "{text}"'
    else:
        summary = f"{label}. Full wording is in the complaint timeline."
    citations = [references[identifier] for identifier in event["evidence_ids"] if identifier in references]
    if citations:
        summary += f" Linked excerpts: {', '.join(citations)}."
    return f"- {event['occurred_on'] or 'Date not supplied'}: {summary}"


def build_pack(data: ComplaintCase, evidence):
    checklist = []
    for key, label in [("buyer_name", "Your name"), ("seller_name", "Seller/company name"),
                       ("seller_contact", "Seller contact/address"), ("product", "Product description"),
                       ("description", "What went wrong"), ("requested_resolution", "Your requested resolution")]:
        checklist.append({"key": key, "label": label, "complete": bool(getattr(data, key)), "required_for_draft": True})
    checklist.append({"key": "confirmation", "label": "You checked the facts, dates and amounts", "complete": data.facts_confirmed, "required_for_draft": True})
    for key, label in [("order_reference", "Order/reference number, if available"),
                       ("amount_inr", "Transaction amount, if known")]:
        checklist.append({"key": key, "label": label, "complete": bool(getattr(data, key)), "required_for_draft": False})
    for category, label in [("invoice", "Invoice or purchase record"), ("delivery", "Delivery/return record, if applicable"),
                            ("correspondence", "Seller correspondence, if available")]:
        checklist.append({"key": category, "label": label, "complete": any(item["available"] and item["category"] == category for item in evidence), "required_for_draft": False})
    purchase = any(event.kind == "purchase" and event.occurred_on for event in data.events)
    checklist.append({"key": "purchase_date", "label": "Purchase date recorded (do not guess)", "complete": purchase, "required_for_draft": False})
    checklist.append({"key": "seller_contact_event", "label": "Previous contact with seller recorded, if applicable",
                      "complete": any(event.kind == "contact" for event in data.events), "required_for_draft": False})
    timeline = sorted([event.model_dump() for event in data.events], key=lambda event: event["occurred_on"] or "9999-99-99")
    ready = all(item["complete"] for item in checklist if item["required_for_draft"])
    letter = None
    if ready:
        lines = [f"To: {data.seller_name}", data.seller_contact, "", f"Subject: Complaint regarding {data.product}",
                 "", f"My name is {data.buyer_name}. I am writing about {data.product}."]
        if data.order_reference:
            lines.append(f"Order/reference supplied by me: {data.order_reference}.")
        if data.amount_inr:
            lines.append(f"Transaction amount supplied by me: INR {data.amount_inr}.")
        lines.extend(["", "My account of the issue:", data.description, "", "Chronology supplied by me:"])
        references = {item["evidence_id"]: f"E{index + 1}" for index, item in enumerate(evidence) if item["available"]}
        lines.extend(_letter_event(event, references) for event in timeline)
        if not timeline:
            lines.append("No dated chronology supplied.")
        lines.extend(["", "Resolution I request:", data.requested_resolution, "", "Please respond to my complaint.", "", data.buyer_name])
        letter = data.letter_text.strip() or "\n".join(lines)
    return {"pack_version": "1", "title": data.title, "facts": data.model_dump(exclude={"letter_text"}),
            "timeline": timeline, "evidence": evidence, "checklist": checklist, "draft_ready": ready,
            "draft_letter": letter, "user_edited_draft": bool(data.letter_text.strip()), "disclaimer": DISCLAIMER,
            "notices": ["Dates, amounts, descriptions and evidence links are user-supplied, not independently verified.",
                        "An exact source quote proves text location, not that it establishes your claim.",
                        "Missing or deleted sources are omitted from the evidence excerpts; keep your own original records.",
                        "This pack does not include original PDF attachments, file a grievance, calculate legal deadlines or guarantee a refund.",
                        "Review and edit the letter before sharing. Minimize personal information and seek qualified advice for consequential issues."],
            "official_help_url": "https://consumerhelpline.gov.in/"}


def case_pack(case_id, user_id, revision):
    record = get_case(case_id, user_id)
    if record["revision"] != revision:
        raise HTTPException(409, "The saved complaint changed. Reload before building the pack.")
    data = ComplaintCase.model_validate(record["data"])
    # Bound all evidence lookups as a group, rather than 15 separate 5s waits.
    return _db(lambda: {"case_id": case_id, "revision": revision,
                       **build_pack(data, resolve_evidence(data, user_id, strict=False))})
