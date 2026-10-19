from hashlib import sha256

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.dependencies import get_current_user
from app.core.rate_limit import limit_chat
from app.schemas.complaint import ComplaintCase, ComplaintUpdate, PackRequest, ImportRequest, IntakeRequest
from app.services.complaint_intake import prepare_intake
from app.services.complaint_import import suggest_from_documents
from app.services import complaint_service as service
from app.services.agreement_documents import list_agreement_documents, load_agreement_document
from app.services.guest_service import require_registered_user

router = APIRouter()


def registered_user(user=Depends(get_current_user)):
    require_registered_user(user)
    return str(user["_id"])


@router.get("")
def cases(user_id=Depends(registered_user)):
    return service.list_cases(user_id)


@router.get("/documents")
def documents(user_id=Depends(registered_user)):
    return list_agreement_documents(user_id)


@router.get("/documents/{document_id}/pages/{page_number}")
def source_page(document_id: str, page_number: int, user_id=Depends(registered_user)):
    document = load_agreement_document(document_id, user_id)
    if not 1 <= page_number <= document.page_count:
        raise HTTPException(404, "Source page not found")
    page = document.pages[page_number - 1]
    return {"document_id": document.document_id, "filename": document.title,
            "page_count": document.page_count, "page_text_sha256": sha256(page.text.encode()).hexdigest(),
            **page.model_dump()}


@router.post("", dependencies=[Depends(limit_chat)])
def create(data: ComplaintCase, user_id=Depends(registered_user)):
    return service.save_case(data, user_id)


@router.post("/import", dependencies=[Depends(limit_chat)])
def import_records(body: ImportRequest, user_id=Depends(registered_user)):
    # Reuse owner/status/readability checks; never accept page text from the client.
    documents = [load_agreement_document(identifier, user_id) for identifier in body.document_ids]
    return suggest_from_documents(documents)


@router.get("/{case_id}")
def read(case_id: str, user_id=Depends(registered_user)):
    return service.get_case(case_id, user_id)


@router.post("/intake", dependencies=[Depends(limit_chat)])
async def intake(body: IntakeRequest, user_id=Depends(registered_user)):
    return await prepare_intake(body.description)


@router.put("/{case_id}", dependencies=[Depends(limit_chat)])
def update(case_id: str, body: ComplaintUpdate, user_id=Depends(registered_user)):
    return service.save_case(body.data, user_id, case_id, body.revision)


@router.delete("/{case_id}", dependencies=[Depends(limit_chat)])
def delete(case_id: str, revision: int = Query(ge=1), user_id=Depends(registered_user)):
    return service.delete_case(case_id, user_id, revision)


@router.post("/{case_id}/pack", dependencies=[Depends(limit_chat)])
def pack(case_id: str, body: PackRequest, user_id=Depends(registered_user)):
    return service.case_pack(case_id, user_id, body.revision)
