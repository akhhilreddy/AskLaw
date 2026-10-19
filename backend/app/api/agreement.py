"""Additive text-only feature. Existing chat/retrieval/auth are not invoked or altered."""
from fastapi import APIRouter, Depends, HTTPException

from app.core.dependencies import get_current_user
from app.core.rate_limit import limit_chat
from app.schemas.agreement import AgreementCompareRequest, AgreementReviewRequest, AgreementText
from app.services.agreement_analysis import compare_agreements, review_agreement
from app.services.agreement_documents import list_agreement_documents, load_agreement_document
from app.services.guest_service import require_registered_user

router = APIRouter()


def agreement_user(user=Depends(get_current_user)):
    require_registered_user(user)
    return str(user["_id"])


@router.get("/documents")
def documents(user_id=Depends(agreement_user)):
    return list_agreement_documents(user_id)


def bounded_analysis(operation, *documents):
    try:
        return operation(*documents)
    except ValueError:
        raise HTTPException(422, "Too many text passages for this review. Use a shorter agreement.") from None


@router.post("/review", dependencies=[Depends(limit_chat)])
def review(body: AgreementReviewRequest, user_id=Depends(agreement_user)):
    return bounded_analysis(review_agreement, load_agreement_document(body.document_id, user_id))


@router.post("/compare", dependencies=[Depends(limit_chat)])
def compare(body: AgreementCompareRequest, user_id=Depends(agreement_user)):
    # Both lookups enforce ownership independently, even if the first succeeds.
    before = load_agreement_document(body.before_id, user_id)
    after = load_agreement_document(body.after_id, user_id)
    return bounded_analysis(compare_agreements, before, after)


@router.get("/demo", dependencies=[Depends(limit_chat)])
def demo(_user=Depends(get_current_user)):
    # Static synthetic data, not a legal template. No user document or database read.
    before = AgreementText(document_id="sample-before", title="Sample rental agreement — original",
        page_count=1, pages=[{"page_number": 1, "text": (
            "SYNTHETIC SAMPLE — NOT A LEGAL TEMPLATE\n\n"
            "Monthly rent: INR 12,000.\n\nSecurity deposit: INR 10,000.\n\n"
            "Either party may terminate with 30 days notice.\n\nRenewal requires mutual written consent.")}])
    after = before.model_copy(update={"document_id": "sample-after", "title": "Sample rental agreement — revised",
        "pages": [before.pages[0].model_copy(update={"text": before.pages[0].text.replace(
            "INR 10,000", "INR 15,000").replace("30 days", "90 days")})]})
    return {"sample": True, "review": review_agreement(after), "comparison": compare_agreements(before, after)}
