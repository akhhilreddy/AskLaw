from fastapi import (
    APIRouter,
    Depends,
    File,
    UploadFile,
    HTTPException,
)

from app.core.dependencies import get_current_user
from app.services.document_service import (
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
