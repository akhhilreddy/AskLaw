from fastapi import APIRouter
from fastapi import Response
from app.db.mongodb import user_collection
from app.utils.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token
)
from fastapi import HTTPException, status
from app.schemas.auth import UserLogin
from app.schemas.auth import SignUpRequest
from app.core.config import Settings
from fastapi import Cookie
settings = Settings()
from jose import JWTError, jwt

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
def login(user: UserLogin,response : Response):

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
    data={"sub": existing_user["email"]}
    )
    refresh_token = create_refresh_token(
    data={"sub": existing_user["email"]}
    )
    response.set_cookie(
    key="refresh_token",
    value=refresh_token,
    httponly=True,
    secure=False,      # Change to True in production (HTTPS)
    samesite="lax",
    max_age=60 * 60 * 24 * settings.REFRESH_TOKEN_EXPIRE_DAYS,
)
    return {
        "access_token": access_token,
        "token_type": "bearer"
    }


@router.post("/refresh")
def refresh_access_token(
    refresh_token: str | None = Cookie(default=None),
):
    if refresh_token is None:
        raise HTTPException(
            status_code=401,
            detail="Refresh token missing",
        )

    try:
        payload = jwt.decode(
            refresh_token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )

        email = payload.get("sub")

        if email is None:
            raise HTTPException(
                status_code=401,
                detail="Invalid refresh token",
            )

    except JWTError:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired refresh token",
        )

    new_access_token = create_access_token(
        data={"sub": email}
    )

    return {
        "access_token": new_access_token,
        "token_type": "bearer",
    }


from fastapi import Depends
from app.core.dependencies import get_current_user

@router.get("/me")
def get_me(current_user = Depends(get_current_user)):
    return {
        "name": current_user["name"],
        "email": current_user["email"]
    }