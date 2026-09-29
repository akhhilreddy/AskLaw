import logging
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
from app.schemas.auth import (
    EmailRequest,
    ResetPasswordRequest,
    SignUpRequest,
    UserLogin,
    VerifyEmailRequest,
)
from app.core.config import settings
from app.core.dependencies import get_current_user
from fastapi import Cookie
from jose import JWTError, jwt
from pymongo.errors import DuplicateKeyError
from app.services.auth_code_service import (
    RESET_PASSWORD,
    VERIFY_EMAIL,
    consume_code,
    issue_code,
)
from app.services.email_service import EmailDeliveryError

router = APIRouter()
logger = logging.getLogger(__name__)


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


def _token_payload(user: dict) -> dict:
    payload = {"sub": user["email"]}
    if "auth_version" in user:
        payload["auth_version"] = user["auth_version"]
    return payload


def _ensure_verified(user: dict) -> None:
    # Users created before email verification was introduced have no flag and
    # remain valid. Only explicitly pending users are blocked.
    if user.get("email_verified") is False:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Verify your email before signing in",
        )

@router.post("/signup", status_code=status.HTTP_201_CREATED)
def signup(user: SignUpRequest):
    email = str(user.email)
    existing_user = user_collection.find_one({"email": email})
    if existing_user and existing_user.get("email_verified") is not False:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already exists",
        )

    hashed_password = hash_password(user.password)
    user_document = {
        "name": user.name,
        "email": email,
        "password_hash": hashed_password,
        "email_verified": False,
        "auth_version": 0,
        "created_at": datetime.now(timezone.utc),
    }
    if existing_user:
        try:
            code_sent = issue_code(email, VERIFY_EMAIL)
        except EmailDeliveryError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Verification email could not be sent. Please try again.",
            ) from exc

        if not code_sent:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Please wait before requesting another verification code",
            )

        user_collection.update_one(
            {"_id": existing_user["_id"], "email_verified": False},
            {
                "$set": {
                    "name": user.name,
                    "password_hash": hashed_password,
                }
            },
        )
    else:
        try:
            inserted_user_id = user_collection.insert_one(user_document).inserted_id
        except DuplicateKeyError:
            # The unique email index closes the race between the lookup above
            # and insertion without exposing database details.
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already exists",
            ) from None

        try:
            issue_code(email, VERIFY_EMAIL)
        except EmailDeliveryError as exc:
            user_collection.delete_one(
                {"_id": inserted_user_id, "email_verified": False}
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Verification email could not be sent. Please try again.",
            ) from exc

    return {
        "message": "Verification code sent",
        "email": email,
    }


@router.post("/verify-email", dependencies=[Depends(require_trusted_origin)])
def verify_email(payload: VerifyEmailRequest):
    email = str(payload.email)
    pending_user = user_collection.find_one(
        {"email": email, "email_verified": False}
    )
    if pending_user is None or not consume_code(
        email, VERIFY_EMAIL, payload.code
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification code",
        )

    user_collection.update_one(
        {"_id": pending_user["_id"], "email_verified": False},
        {
            "$set": {
                "email_verified": True,
                "email_verified_at": datetime.now(timezone.utc),
            }
        },
    )
    return {"message": "Email verified successfully"}


@router.post(
    "/resend-verification",
    dependencies=[Depends(require_trusted_origin)],
)
def resend_verification(payload: EmailRequest):
    email = str(payload.email)
    pending_user = user_collection.find_one(
        {"email": email, "email_verified": False}
    )
    if pending_user:
        try:
            issue_code(email, VERIFY_EMAIL)
        except EmailDeliveryError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Verification email could not be sent. Please try again.",
            ) from exc

    return {
        "message": "If the account is awaiting verification, a code has been sent"
    }


@router.post(
    "/forgot-password",
    dependencies=[Depends(require_trusted_origin)],
)
def forgot_password(payload: EmailRequest):
    email = str(payload.email)
    existing_user = user_collection.find_one({"email": email})
    if existing_user and existing_user.get("email_verified") is not False:
        try:
            issue_code(email, RESET_PASSWORD)
        except EmailDeliveryError:
            # Keep the response identical for registered and unknown emails.
            logger.warning("Password reset email delivery failed")

    return {
        "message": "If an account exists, a password reset code has been sent"
    }


@router.post(
    "/reset-password",
    dependencies=[Depends(require_trusted_origin)],
)
def reset_password(payload: ResetPasswordRequest):
    email = str(payload.email)
    existing_user = user_collection.find_one({"email": email})
    if (
        existing_user is None
        or existing_user.get("email_verified") is False
        or not consume_code(email, RESET_PASSWORD, payload.code)
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired password reset code",
        )

    user_collection.update_one(
        {"_id": existing_user["_id"]},
        {
            "$set": {
                "password_hash": hash_password(payload.new_password),
                "password_changed_at": datetime.now(timezone.utc),
            },
            "$inc": {"auth_version": 1},
        },
    )
    return {"message": "Password reset successfully"}

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

    password_hash = existing_user.get("password_hash")
    if not password_hash or not verify_password(
        user.password,
        password_hash,
    ):
        
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
    )


    _ensure_verified(existing_user)
    token_payload = _token_payload(existing_user)
    access_token = create_access_token(data=token_payload)
    refresh_token = create_refresh_token(data=token_payload)
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

    password_hash = existing_user.get("password_hash")
    if not password_hash or not verify_password(
        form_data.password,
        password_hash,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    _ensure_verified(existing_user)
    token_payload = _token_payload(existing_user)
    access_token = create_access_token(data=token_payload)
    refresh_token = create_refresh_token(data=token_payload)

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

        existing_user = user_collection.find_one({"email": email})
        if existing_user is None:
            raise HTTPException(
                status_code=401,
                detail="Invalid refresh token",
            )

        _ensure_verified(existing_user)
        user_auth_version = existing_user.get("auth_version")
        if (
            user_auth_version is not None
            and payload.get("auth_version") != user_auth_version
        ):
            raise HTTPException(
                status_code=401,
                detail="Invalid refresh token",
            )

    except JWTError:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired refresh token",
        )

    new_access_token = create_access_token(data=_token_payload(existing_user))

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
