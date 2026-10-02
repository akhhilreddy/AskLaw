import base64
import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("ALGORITHM", "HS256")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "15")
os.environ.setdefault("REFRESH_TOKEN_EXPIRE_DAYS", "7")
os.environ.setdefault("GROQ_API_KEY", "test-groq-key")

from bson import ObjectId
from fastapi import Response
from pydantic import ValidationError

from app.api import auth
from app.core.config import Settings
from app.schemas.auth import PasskeyAuthenticationVerifyRequest
from app.services import passkey_service


def encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


class PasskeyConfigurationTests(unittest.TestCase):
    def test_local_passkey_settings_are_derived_from_frontend(self):
        configured = Settings(
            SECRET_KEY="test-secret-key",
            ALGORITHM="HS256",
            ACCESS_TOKEN_EXPIRE_MINUTES=15,
            REFRESH_TOKEN_EXPIRE_DAYS=7,
            FRONTEND_URL="http://localhost:5173",
            CORS_ORIGINS="http://localhost:5173",
            _env_file=None,
        )

        self.assertEqual(configured.webauthn_origin, "http://localhost:5173")
        self.assertEqual(configured.webauthn_rp_id, "localhost")

    def test_passkey_rp_id_must_match_origin(self):
        with self.assertRaisesRegex(ValidationError, "WEBAUTHN_RP_ID"):
            Settings(
                SECRET_KEY="test-secret-key",
                ALGORITHM="HS256",
                ACCESS_TOKEN_EXPIRE_MINUTES=15,
                REFRESH_TOKEN_EXPIRE_DAYS=7,
                FRONTEND_URL="https://asklaw.example",
                CORS_ORIGINS="https://asklaw.example",
                WEBAUTHN_ORIGIN="https://asklaw.example",
                WEBAUTHN_RP_ID="attacker.example",
                _env_file=None,
            )

    def test_production_passkey_origin_requires_https(self):
        with self.assertRaisesRegex(ValidationError, "must use HTTPS"):
            Settings(
                APP_ENV="production",
                SECRET_KEY="x" * 32,
                ALGORITHM="HS256",
                ACCESS_TOKEN_EXPIRE_MINUTES=15,
                REFRESH_TOKEN_EXPIRE_DAYS=7,
                COOKIE_SECURE=True,
                CORS_ORIGINS="http://asklaw.example",
                FRONTEND_URL="http://asklaw.example",
                SEARXNG_URL="https://search.example.com/search",
                RESEND_API_KEY="resend-key",
                EMAIL_FROM="AskLAW <auth@asklaw.example>",
                _env_file=None,
            )


class PasskeyServiceTests(unittest.TestCase):
    def test_registration_requests_platform_authenticator(self):
        user_id = ObjectId()
        challenges = Mock()
        credentials = Mock()
        credentials.find.return_value = []

        with patch.object(
            passkey_service, "passkey_challenge_collection", challenges
        ), patch.object(
            passkey_service, "passkey_collection", credentials
        ):
            result = passkey_service.begin_registration(
                {
                    "_id": user_id,
                    "email": "person@example.com",
                    "name": "Person",
                }
            )

        selection = result["options"]["authenticatorSelection"]
        self.assertEqual(selection["authenticatorAttachment"], "platform")
        self.assertEqual(selection["residentKey"], "required")
        self.assertEqual(selection["userVerification"], "required")

    def test_registration_challenge_is_single_use_and_user_scoped(self):
        user_id = ObjectId()
        challenges = Mock()
        challenges.find_one_and_delete.return_value = {"challenge": b"challenge"}
        credentials = Mock()
        verification = SimpleNamespace(
            credential_id=b"credential-id",
            credential_public_key=b"public-key",
            sign_count=0,
            credential_device_type=SimpleNamespace(value="multi_device"),
            credential_backed_up=True,
        )
        credential = {
            "id": "credential-id",
            "response": {"transports": ["internal", "hybrid"]},
        }

        with patch.object(
            passkey_service, "passkey_challenge_collection", challenges
        ), patch.object(
            passkey_service, "passkey_collection", credentials
        ), patch.object(
            passkey_service,
            "verify_registration_response",
            return_value=verification,
        ) as verify:
            result = passkey_service.complete_registration(
                {"_id": user_id, "email": "person@example.com"},
                "f" * 43,
                credential,
                "MacBook Touch ID",
            )

        challenge_query = challenges.find_one_and_delete.call_args.args[0]
        self.assertEqual(challenge_query["purpose"], passkey_service.REGISTER)
        self.assertEqual(challenge_query["user_id"], user_id)
        self.assertIn("$gt", challenge_query["expires_at"])
        verify.assert_called_once()
        inserted = credentials.insert_one.call_args.args[0]
        self.assertEqual(inserted["user_id"], user_id)
        self.assertEqual(inserted["credential_public_key"], b"public-key")
        self.assertEqual(result["name"], "MacBook Touch ID")
        self.assertNotIn("credential_public_key", result)

    def test_authentication_uses_credential_owner_and_updates_counter(self):
        user_id = ObjectId()
        credential_record_id = ObjectId()
        credential_id = "credential-id"
        challenges = Mock()
        challenges.find_one_and_delete.return_value = {"challenge": b"challenge"}
        credentials = Mock()
        credentials.find_one.return_value = {
            "_id": credential_record_id,
            "credential_id": credential_id,
            "credential_public_key": b"public-key",
            "user_id": user_id,
            "sign_count": 2,
        }
        credentials.update_one.return_value = SimpleNamespace(matched_count=1)
        users = Mock()
        users.find_one.return_value = {
            "_id": user_id,
            "email": "person@example.com",
            "email_verified": True,
            "auth_version": 0,
        }
        verification = SimpleNamespace(
            new_sign_count=3,
            credential_device_type=SimpleNamespace(value="single_device"),
            credential_backed_up=False,
        )
        credential = {
            "id": credential_id,
            "response": {"userHandle": encode(str(user_id).encode("utf-8"))},
        }

        with patch.object(
            passkey_service, "passkey_challenge_collection", challenges
        ), patch.object(
            passkey_service, "passkey_collection", credentials
        ), patch.object(
            passkey_service, "user_collection", users
        ), patch.object(
            passkey_service,
            "verify_authentication_response",
            return_value=verification,
        ) as verify:
            user = passkey_service.complete_authentication("f" * 43, credential)

        self.assertEqual(user["_id"], user_id)
        users.find_one.assert_called_once_with({"_id": user_id})
        verify.assert_called_once()
        update_filter = credentials.update_one.call_args.args[0]
        self.assertEqual(
            update_filter,
            {"_id": credential_record_id, "sign_count": 2},
        )
        updated = credentials.update_one.call_args.args[1]["$set"]
        self.assertEqual(updated["sign_count"], 3)

    def test_authentication_rejects_mismatched_user_handle(self):
        user_id = ObjectId()
        challenges = Mock()
        challenges.find_one_and_delete.return_value = {"challenge": b"challenge"}
        credentials = Mock()
        credentials.find_one.return_value = {
            "_id": ObjectId(),
            "credential_id": "credential-id",
            "credential_public_key": b"public-key",
            "user_id": user_id,
            "sign_count": 0,
        }
        users = Mock()
        users.find_one.return_value = {
            "_id": user_id,
            "email": "person@example.com",
            "email_verified": True,
        }
        credential = {
            "id": "credential-id",
            "response": {"userHandle": encode(b"another-user")},
        }

        with patch.object(
            passkey_service, "passkey_challenge_collection", challenges
        ), patch.object(
            passkey_service, "passkey_collection", credentials
        ), patch.object(
            passkey_service, "user_collection", users
        ), patch.object(
            passkey_service, "verify_authentication_response"
        ) as verify:
            with self.assertRaisesRegex(
                passkey_service.PasskeyError,
                "could not be verified",
            ):
                passkey_service.complete_authentication("f" * 43, credential)

        verify.assert_not_called()

    def test_delete_is_scoped_to_authenticated_user(self):
        user_id = ObjectId()
        credentials = Mock()
        credentials.delete_one.return_value = SimpleNamespace(deleted_count=1)

        with patch.object(passkey_service, "passkey_collection", credentials):
            deleted = passkey_service.delete_passkey(
                {"_id": user_id},
                "credential-id",
            )

        self.assertTrue(deleted)
        credentials.delete_one.assert_called_once_with(
            {"credential_id": "credential-id", "user_id": user_id}
        )


class PasskeyRouteTests(unittest.TestCase):
    def test_passkey_login_issues_existing_asklaw_session(self):
        user = {
            "_id": ObjectId(),
            "email": "person@example.com",
            "email_verified": True,
            "auth_version": 4,
        }
        response = Response()
        payload = PasskeyAuthenticationVerifyRequest(
            flow_id="f" * 43,
            credential={"id": "credential-id", "response": {}},
        )

        with patch.object(
            auth, "complete_passkey_authentication", return_value=user
        ), patch.object(
            auth, "create_access_token", return_value="access-token"
        ), patch.object(
            auth, "create_refresh_token", return_value="refresh-token"
        ):
            result = auth.passkey_authentication_verify(payload, response)

        self.assertEqual(result["access_token"], "access-token")
        self.assertIn("refresh_token=refresh-token", response.headers["set-cookie"])

    def test_provider_discovery_advertises_passkeys(self):
        self.assertTrue(auth.auth_providers()["passkey"])


if __name__ == "__main__":
    unittest.main()
