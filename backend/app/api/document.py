from fastapi import (
    APIRouter,
    Depends,
    File,
    UploadFile,
    HTTPException,
)

from app.core.dependencies import get_current_user
from app.services.document_service import (
    delete_owned_document,
    get_user_documents,
    save_uploaded_document,
)


router = APIRouter()


@router.get("")
def list_documents(
    current_user=Depends(get_current_user),
):
    return get_user_documents(
        user_id=str(current_user["_id"]),
    )


@router.delete("/{document_id}")
def delete_document(
    document_id: str,
    current_user=Depends(get_current_user),
):
    result = delete_owned_document(
        document_id=document_id,
        user_id=str(current_user["_id"]),
    )

    if not result:
        raise HTTPException(
            status_code=404,
            detail="Document not found",
        )

    return result


@router.post("/upload")
def upload_document(
    file: UploadFile = File(...),
    current_user=Depends(get_current_user),
):
    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="File name is required",
        )

    if file.content_type != "application/pdf":
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are supported",
        )

    result = save_uploaded_document(
        file=file,
        user_id=str(current_user["_id"]),
    )

    return result
