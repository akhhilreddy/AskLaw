import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token as google_id_token
from pymongo.errors import DuplicateKeyError

from app.core.config import settings
from app.db.mongodb import oauth_exchange_collection, user_collection


GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"


class GoogleOAuthError(RuntimeError):
    """Raised when the Google identity flow cannot be completed safely."""


def build_authorization_url(state: str) -> str:
    parameters = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "prompt": "select_account",
    }
    return f"{GOOGLE_AUTHORIZE_URL}?{urlencode(parameters)}"


def exchange_google_code(code: str) -> dict:
    try:
        response = httpx.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uri": settings.GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
            timeout=10.0,
        )
        response.raise_for_status()
        token_payload = response.json()
        encoded_id_token = token_payload.get("id_token")
        if not encoded_id_token:
            raise GoogleOAuthError("Google did not return an identity token")

        claims = google_id_token.verify_oauth2_token(
            encoded_id_token,
            GoogleRequest(),
            settings.GOOGLE_CLIENT_ID,
        )
    except (httpx.HTTPError, GoogleAuthError, ValueError) as exc:
        raise GoogleOAuthError("Google authentication failed") from exc

    email = claims.get("email")
    google_sub = claims.get("sub")
    if not email or not google_sub or claims.get("email_verified") is not True:
        raise GoogleOAuthError("Google did not return a verified email")

    return {
        "email": str(email),
        "google_sub": str(google_sub),
        "name": str(claims.get("name") or email.split("@", 1)[0])[:120],
    }


def find_or_create_google_user(profile: dict) -> dict:
    email = profile["email"]
    google_sub = profile["google_sub"]
    user = user_collection.find_one({"google_sub": google_sub})
    if user:
        return user

    user = user_collection.find_one({"email": email})
    now = datetime.now(timezone.utc)
    if user:
        existing_google_sub = user.get("google_sub")
        if existing_google_sub and existing_google_sub != google_sub:
            raise GoogleOAuthError("This email is linked to another Google account")

        update = {
            "$set": {
                "google_sub": google_sub,
                "email_verified": True,
                "email_verified_at": now,
            },
            "$addToSet": {"auth_providers": "google"},
        }
        if user.get("email_verified") is False:
            # A Google-verified owner may claim a pending email, but must not
            # inherit a password chosen before ownership was established.
            update["$unset"] = {"password_hash": ""}
            update["$inc"] = {"auth_version": 1}

        try:
            user_collection.update_one({"_id": user["_id"]}, update)
        except DuplicateKeyError as exc:
            raise GoogleOAuthError("Google account linking conflict") from exc
        return user_collection.find_one({"_id": user["_id"]})

    document = {
        "name": profile["name"],
        "email": email,
        "google_sub": google_sub,
        "auth_providers": ["google"],
        "email_verified": True,
        "email_verified_at": now,
        "auth_version": 0,
        "created_at": now,
    }
    try:
        result = user_collection.insert_one(document)
    except DuplicateKeyError as exc:
        raise GoogleOAuthError("Google account linking conflict") from exc
    document["_id"] = result.inserted_id
    return document


def _hash_exchange_code(code: str) -> str:
    return hmac.new(
        settings.email_otp_secret.encode("utf-8"),
        code.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def create_exchange_code(user_id) -> str:
    code = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    oauth_exchange_collection.insert_one(
        {
            "code_hash": _hash_exchange_code(code),
            "user_id": user_id,
            "created_at": now,
            "expires_at": now
            + timedelta(minutes=settings.GOOGLE_OAUTH_EXCHANGE_EXPIRE_MINUTES),
        }
    )
    return code


def consume_exchange_code(code: str) -> dict | None:
    exchange = oauth_exchange_collection.find_one_and_delete(
        {
            "code_hash": _hash_exchange_code(code),
            "expires_at": {"$gt": datetime.now(timezone.utc)},
        }
    )
    if not exchange:
        return None
    return user_collection.find_one({"_id": exchange["user_id"]})
