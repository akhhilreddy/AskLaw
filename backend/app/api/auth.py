from fastapi import APIRouter
from app.db.mongodb import user_collection
from app.utils.security import (
    hash_password,
    verify_password,
    create_access_token
)
from fastapi import HTTPException, status
from app.schemas.auth import UserLogin
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

@router.post("/login")
def login(user: UserLogin):

    existing_user = user_collection.find_one({
        "email": user.email
    })

    if not existing_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    
    if not verify_password(
        user.password,
    existing_user["password_hash"]):
        
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
    )


    access_token = create_access_token(
    data={
        "sub": existing_user["email"]
        }
    )
    return {
        "access_token": access_token,
        "token_type": "bearer"
    }

from fastapi import Depends
from app.core.dependencies import get_current_user

@router.get("/me")
def get_me(current_user = Depends(get_current_user)):
    return {
        "name": current_user["name"],
        "email": current_user["email"]
    }