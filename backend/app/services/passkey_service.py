import base64
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone

from pymongo.errors import DuplicateKeyError
from webauthn import (
    base64url_to_bytes,
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers.exceptions import WebAuthnException
from webauthn.helpers.structs import (
    AuthenticatorAttachment,
    AuthenticatorSelectionCriteria,
    AuthenticatorTransport,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from app.core.config import settings
from app.db.mongodb import (
    passkey_challenge_collection,
    passkey_collection,
    user_collection,
)


REGISTER = "register"
AUTHENTICATE = "authenticate"


class PasskeyError(Exception):
    """Raised when a passkey ceremony cannot be completed safely."""


def _bytes_to_base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _store_challenge(
    purpose: str,
    challenge: bytes,
    user_id=None,
) -> str:
    flow_id = secrets.token_urlsafe(32)
    document = {
        "flow_id": flow_id,
        "purpose": purpose,
        "challenge": challenge,
        "created_at": _now(),
        "expires_at": _now()
        + timedelta(minutes=settings.WEBAUTHN_CHALLENGE_EXPIRE_MINUTES),
    }
    if user_id is not None:
        document["user_id"] = user_id
    passkey_challenge_collection.insert_one(document)
    return flow_id


def _consume_challenge(flow_id: str, purpose: str, user_id=None) -> bytes:
    query = {
        "flow_id": flow_id,
        "purpose": purpose,
        "expires_at": {"$gt": _now()},
    }
    if user_id is not None:
        query["user_id"] = user_id

    challenge = passkey_challenge_collection.find_one_and_delete(query)
    if challenge is None:
        raise PasskeyError("Passkey request expired or has already been used")
    return bytes(challenge["challenge"])


def _credential_transports(record: dict) -> list[AuthenticatorTransport]:
    transports = []
    for value in record.get("transports", []):
        try:
            transports.append(AuthenticatorTransport(value))
        except ValueError:
            continue
    return transports


def begin_registration(user: dict) -> dict:
    existing = list(passkey_collection.find({"user_id": user["_id"]}))
    exclude_credentials = [
        PublicKeyCredentialDescriptor(
            id=base64url_to_bytes(record["credential_id"]),
            transports=_credential_transports(record) or None,
        )
        for record in existing
    ]
    options = generate_registration_options(
        rp_id=settings.webauthn_rp_id,
        rp_name=settings.WEBAUTHN_RP_NAME,
        user_id=str(user["_id"]).encode("utf-8"),
        user_name=user["email"],
        user_display_name=user.get("name") or user["email"],
        timeout=60_000,
        authenticator_selection=AuthenticatorSelectionCriteria(
            authenticator_attachment=AuthenticatorAttachment.PLATFORM,
            resident_key=ResidentKeyRequirement.REQUIRED,
            require_resident_key=True,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        exclude_credentials=exclude_credentials,
    )
    flow_id = _store_challenge(REGISTER, options.challenge, user["_id"])
    return {
        "flow_id": flow_id,
        "options": json.loads(options_to_json(options)),
    }


def complete_registration(
    user: dict,
    flow_id: str,
    credential: dict,
    name: str,
) -> dict:
    challenge = _consume_challenge(flow_id, REGISTER, user["_id"])
    try:
        verification = verify_registration_response(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=settings.webauthn_rp_id,
            expected_origin=settings.webauthn_origin,
            require_user_verification=True,
        )
    except (WebAuthnException, ValueError, TypeError) as exc:
        raise PasskeyError("Passkey registration could not be verified") from exc

    credential_id = _bytes_to_base64url(verification.credential_id)
    transports = credential.get("response", {}).get("transports", [])
    if not isinstance(transports, list):
        transports = []
    transports = [
        value
        for value in transports
        if isinstance(value, str)
        and value in {transport.value for transport in AuthenticatorTransport}
    ]

    now = _now()
    document = {
        "user_id": user["_id"],
        "credential_id": credential_id,
        "credential_public_key": verification.credential_public_key,
        "sign_count": verification.sign_count,
        "name": name,
        "transports": transports,
        "device_type": verification.credential_device_type.value,
        "backed_up": verification.credential_backed_up,
        "created_at": now,
        "last_used_at": None,
    }
    try:
        passkey_collection.insert_one(document)
    except DuplicateKeyError as exc:
        raise PasskeyError("This passkey is already registered") from exc

    return _public_passkey(document)


def begin_authentication() -> dict:
    options = generate_authentication_options(
        rp_id=settings.webauthn_rp_id,
        timeout=60_000,
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    flow_id = _store_challenge(AUTHENTICATE, options.challenge)
    return {
        "flow_id": flow_id,
        "options": json.loads(options_to_json(options)),
    }


def complete_authentication(flow_id: str, credential: dict) -> dict:
    challenge = _consume_challenge(flow_id, AUTHENTICATE)
    credential_id = credential.get("id")
    if not isinstance(credential_id, str) or not 1 <= len(credential_id) <= 1024:
        raise PasskeyError("Passkey sign-in could not be verified")

    record = passkey_collection.find_one({"credential_id": credential_id})
    if record is None:
        raise PasskeyError("Passkey sign-in could not be verified")

    user = user_collection.find_one({"_id": record["user_id"]})
    if user is None or user.get("email_verified") is False:
        raise PasskeyError("Passkey sign-in could not be verified")

    user_handle = credential.get("response", {}).get("userHandle")
    if not isinstance(user_handle, str):
        raise PasskeyError("Passkey sign-in could not be verified")
    try:
        supplied_user_id = base64url_to_bytes(user_handle)
    except ValueError as exc:
        raise PasskeyError("Passkey sign-in could not be verified") from exc
    if not hmac.compare_digest(
        supplied_user_id,
        str(user["_id"]).encode("utf-8"),
    ):
        raise PasskeyError("Passkey sign-in could not be verified")

    current_sign_count = int(record.get("sign_count", 0))
    try:
        verification = verify_authentication_response(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=settings.webauthn_rp_id,
            expected_origin=settings.webauthn_origin,
            credential_public_key=bytes(record["credential_public_key"]),
            credential_current_sign_count=current_sign_count,
            require_user_verification=True,
        )
    except (WebAuthnException, ValueError, TypeError) as exc:
        raise PasskeyError("Passkey sign-in could not be verified") from exc

    update_filter = {"_id": record["_id"]}
    if current_sign_count:
        update_filter["sign_count"] = current_sign_count
    update_result = passkey_collection.update_one(
        update_filter,
        {
            "$set": {
                "sign_count": verification.new_sign_count,
                "device_type": verification.credential_device_type.value,
                "backed_up": verification.credential_backed_up,
                "last_used_at": _now(),
            }
        },
    )
    if update_result.matched_count != 1:
        raise PasskeyError("Passkey sign-in could not be verified")

    return user


def _public_passkey(record: dict) -> dict:
    return {
        "id": record["credential_id"],
        "name": record.get("name") or "Passkey",
        "device_type": record.get("device_type"),
        "backed_up": bool(record.get("backed_up")),
        "created_at": record.get("created_at"),
        "last_used_at": record.get("last_used_at"),
    }


def list_passkeys(user: dict) -> list[dict]:
    records = passkey_collection.find({"user_id": user["_id"]}).sort(
        "created_at", -1
    )
    return [_public_passkey(record) for record in records]


def delete_passkey(user: dict, credential_id: str) -> bool:
    result = passkey_collection.delete_one(
        {"credential_id": credential_id, "user_id": user["_id"]}
    )
    return result.deleted_count == 1
