from datetime import datetime, timedelta, timezone

from fastapi import APIRouter
from fastapi import Response
from fastapi import Request
from app.db.mongodb import user_collection
from app.utils.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token
)
from fastapi.security import OAuth2PasswordRequestForm
from fastapi import Depends
from fastapi import HTTPException, status
from app.schemas.auth import UserLogin
from app.schemas.auth import SignUpRequest
from app.core.config import settings
from app.core.dependencies import get_current_user
from fastapi import Cookie
from jose import JWTError, jwt
from pymongo.errors import DuplicateKeyError

router = APIRouter()


REFRESH_COOKIE_NAME = "refresh_token"
REFRESH_COOKIE_PATH = "/auth"


def require_trusted_origin(request: Request):
    """Reject browser cross-origin requests to cookie session endpoints."""

    origin = request.headers.get("origin")
    api_origin = f"{request.url.scheme}://{request.url.netloc}".rstrip("/")

    # Non-browser clients may omit Origin. Browser POST requests include it,
    # and SameSite=Lax remains a second line of defense for the cookie itself.
    if origin and origin.rstrip("/") not in {
        *settings.cors_origins,
        api_origin,
    }:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Origin is not allowed",
        )


def set_refresh_cookie(response: Response, refresh_token: str):
    lifetime = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        path=REFRESH_COOKIE_PATH,
        max_age=int(lifetime.total_seconds()),
        expires=datetime.now(timezone.utc) + lifetime,
    )

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

    try:
        user_collection.insert_one(user_document)
    except DuplicateKeyError:
        # The unique email index closes the race between the lookup above and
        # insertion without exposing database details.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already exists",
        ) from None

    return{
        "message" : "User registered successfully"
    }

@router.post(
    "/login",
    dependencies=[Depends(require_trusted_origin)],
)
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
    set_refresh_cookie(response, refresh_token)
    return {
        "access_token": access_token,
        "token_type": "bearer"
    }

@router.post(
    "/token",
    dependencies=[Depends(require_trusted_origin)],
)
def login_swagger(
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
):
    existing_user = user_collection.find_one({
        "email": form_data.username
    })

    if not existing_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    if not verify_password(
        form_data.password,
        existing_user["password_hash"],
    ):
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

    set_refresh_cookie(response, refresh_token)

    return {
        "access_token": access_token,
        "token_type": "bearer",
    }


@router.post(
    "/refresh",
    dependencies=[Depends(require_trusted_origin)],
)
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
        token_type = payload.get("token_type")

        legacy_refresh = (
            token_type is None
            and settings.ALLOW_LEGACY_UNTYPED_REFRESH_TOKENS
        )

        if email is None or not (token_type == "refresh" or legacy_refresh):
            raise HTTPException(
                status_code=401,
                detail="Invalid refresh token",
            )

        if user_collection.find_one({"email": email}) is None:
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


@router.get("/me")
def get_me(current_user = Depends(get_current_user)):
    return {
        "name": current_user["name"],
        "email": current_user["email"]
    }

@router.post(
    "/logout",
    dependencies=[Depends(require_trusted_origin)],
)
def logout(response: Response):
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
    )

    return {
        "message": "Logged out successfully"
    }
