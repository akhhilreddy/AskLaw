import hmac
import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

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
from fastapi.responses import RedirectResponse
from app.schemas.auth import (
    EmailRequest,
    GoogleExchangeRequest,
    PasskeyAuthenticationVerifyRequest,
    PasskeyRegistrationVerifyRequest,
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
from app.services.google_oauth_service import (
    GoogleOAuthError,
    build_authorization_url,
    consume_exchange_code,
    create_exchange_code,
    exchange_google_code,
    find_or_create_google_user,
)
from app.services.passkey_service import (
    PasskeyError,
    begin_authentication as begin_passkey_authentication,
    begin_registration as begin_passkey_registration,
    complete_authentication as complete_passkey_authentication,
    complete_registration as complete_passkey_registration,
    delete_passkey as delete_user_passkey,
    list_passkeys as list_user_passkeys,
)
from app.utils.security import create_token

router = APIRouter()
logger = logging.getLogger(__name__)


REFRESH_COOKIE_NAME = "refresh_token"
REFRESH_COOKIE_PATH = "/auth"
GOOGLE_STATE_COOKIE_NAME = "google_oauth_state"
GOOGLE_STATE_COOKIE_PATH = "/auth/google"


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


def _google_frontend_redirect(**parameters: str) -> str:
    base_url = f"{settings.FRONTEND_URL.rstrip('/')}/auth/google/callback"
    return f"{base_url}?{urlencode(parameters)}"


@router.get("/providers")
def auth_providers():
    return {
        "google": settings.google_oauth_enabled,
        "passkey": True,
    }


@router.get("/google/start")
def google_start():
    if not settings.google_oauth_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google sign-in is not configured",
        )

    state_token = create_token(
        {"token_type": "google_oauth_state"},
        timedelta(minutes=settings.GOOGLE_OAUTH_STATE_EXPIRE_MINUTES),
    )
    response = RedirectResponse(
        build_authorization_url(state_token),
        status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    )
    response.set_cookie(
        key=GOOGLE_STATE_COOKIE_NAME,
        value=state_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        path=GOOGLE_STATE_COOKIE_PATH,
        max_age=settings.GOOGLE_OAUTH_STATE_EXPIRE_MINUTES * 60,
    )
    return response


@router.get("/google/callback")
def google_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    google_state_cookie: str | None = Cookie(
        default=None,
        alias=GOOGLE_STATE_COOKIE_NAME,
    ),
):
    if error or not code or not state or not google_state_cookie:
        destination = _google_frontend_redirect(error="google_auth_failed")
    else:
        try:
            if not hmac.compare_digest(state, google_state_cookie):
                raise GoogleOAuthError("OAuth state mismatch")
            state_payload = jwt.decode(
                state,
                settings.SECRET_KEY,
                algorithms=[settings.ALGORITHM],
            )
            if state_payload.get("token_type") != "google_oauth_state":
                raise GoogleOAuthError("Invalid OAuth state")

            profile = exchange_google_code(code)
            user = find_or_create_google_user(profile)
            exchange_code = create_exchange_code(user["_id"])
            destination = _google_frontend_redirect(code=exchange_code)
        except (JWTError, GoogleOAuthError):
            destination = _google_frontend_redirect(error="google_auth_failed")

    response = RedirectResponse(
        destination,
        status_code=status.HTTP_303_SEE_OTHER,
    )
    response.delete_cookie(
        key=GOOGLE_STATE_COOKIE_NAME,
        path=GOOGLE_STATE_COOKIE_PATH,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
    )
    return response


@router.post(
    "/google/exchange",
    dependencies=[Depends(require_trusted_origin)],
)
def google_exchange(payload: GoogleExchangeRequest, response: Response):
    user = consume_exchange_code(payload.code)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired Google sign-in code",
        )

    token_payload = _token_payload(user)
    access_token = create_access_token(data=token_payload)
    refresh_token = create_refresh_token(data=token_payload)
    set_refresh_cookie(response, refresh_token)
    return {"access_token": access_token, "token_type": "bearer"}


@router.post(
    "/passkeys/register/options",
    dependencies=[Depends(require_trusted_origin)],
)
def passkey_registration_options(current_user=Depends(get_current_user)):
    return begin_passkey_registration(current_user)


@router.post(
    "/passkeys/register/verify",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_trusted_origin)],
)
def passkey_registration_verify(
    payload: PasskeyRegistrationVerifyRequest,
    current_user=Depends(get_current_user),
):
    try:
        return complete_passkey_registration(
            current_user,
            payload.flow_id,
            payload.credential,
            payload.name,
        )
    except PasskeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post(
    "/passkeys/authenticate/options",
    dependencies=[Depends(require_trusted_origin)],
)
def passkey_authentication_options():
    return begin_passkey_authentication()


@router.post(
    "/passkeys/authenticate/verify",
    dependencies=[Depends(require_trusted_origin)],
)
def passkey_authentication_verify(
    payload: PasskeyAuthenticationVerifyRequest,
    response: Response,
):
    try:
        user = complete_passkey_authentication(
            payload.flow_id,
            payload.credential,
        )
    except PasskeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc

    token_payload = _token_payload(user)
    access_token = create_access_token(data=token_payload)
    refresh_token = create_refresh_token(data=token_payload)
    set_refresh_cookie(response, refresh_token)
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/passkeys")
def passkeys(current_user=Depends(get_current_user)):
    return list_user_passkeys(current_user)


@router.delete(
    "/passkeys/{credential_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_trusted_origin)],
)
def delete_passkey(
    credential_id: str,
    current_user=Depends(get_current_user),
):
    if not 1 <= len(credential_id) <= 1024 or not delete_user_passkey(
        current_user,
        credential_id,
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Passkey not found",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
