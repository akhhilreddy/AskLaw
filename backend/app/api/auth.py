from fastapi import APIRouter
from app.db.mongodb import user_collection
from app.utils.security import hash_password
from fastapi import HTTPException, status

from app.schemas.auth import SignUpRequest

router = APIRouter()

@router.post("/signup",
             status_code=status.HTTP_201_CREATED)
def signup(user : SignUpRequest):
    existing_user = user_collection.find_one({"email" : user.email})
    if existing_user:
        raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Email already exists"
    )
    hashed_password = hash_password(user.password)

    user_document = {
        "name" : user.name,
        "email" : user.email,
        "password_hash" : hashed_password
    }

    user_collection.insert_one(user_document)

    return{
        "message" : "User registered successfully"
    }
    