from fastapi import APIRouter

from app.schemas.auth import SignUpRequest

router = APIRouter()

@router.post("/signup")
def signup(user : SignUpRequest):
    return {
        "name" : user.name,
        "email" : user.email,
        "message" : "SignUp endpoint reached successfully"
    }