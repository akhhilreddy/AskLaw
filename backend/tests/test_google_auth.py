import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlparse

os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("ALGORITHM", "HS256")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "15")
os.environ.setdefault("REFRESH_TOKEN_EXPIRE_DAYS", "7")
os.environ.setdefault("GROQ_API_KEY", "test-groq-key")

from bson import ObjectId
from fastapi import HTTPException, Response
from pydantic import ValidationError

from app.api import auth
from app.core.config import Settings
from app.schemas.auth import GoogleExchangeRequest
from app.services import google_oauth_service


class GoogleOAuthConfigurationTests(unittest.TestCase):
    def test_google_credentials_must_be_configured_together(self):
        with self.assertRaisesRegex(ValidationError, "configured together"):
            Settings(
                SECRET_KEY="test-secret-key",
                ALGORITHM="HS256",
                ACCESS_TOKEN_EXPIRE_MINUTES=15,
                REFRESH_TOKEN_EXPIRE_DAYS=7,
                GOOGLE_CLIENT_ID="client-id",
                GOOGLE_CLIENT_SECRET="",
                GOOGLE_REDIRECT_URI="",
                _env_file=None,
            )

    def test_authorization_url_contains_expected_google_parameters(self):
        with patch.object(
            google_oauth_service.settings, "GOOGLE_CLIENT_ID", "client-id"
        ), patch.object(
            google_oauth_service.settings,
            "GOOGLE_REDIRECT_URI",
            "https://api.example.com/auth/google/callback",
        ):
            url = google_oauth_service.build_authorization_url("signed-state")

        parsed = urlparse(url)
        parameters = parse_qs(parsed.query)
        self.assertEqual(parsed.netloc, "accounts.google.com")
        self.assertEqual(parameters["client_id"], ["client-id"])
        self.assertEqual(parameters["state"], ["signed-state"])
        self.assertEqual(parameters["scope"], ["openid email profile"])


class GoogleOAuthServiceTests(unittest.TestCase):
    def test_google_code_exchange_requires_verified_email(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"id_token": "encoded-token"}
        claims = {
            "sub": "google-user-1",
            "email": "person@example.com",
            "email_verified": True,
            "name": "Person",
        }

        with patch.object(
            google_oauth_service.httpx, "post", return_value=response
        ), patch.object(
            google_oauth_service.google_id_token,
            "verify_oauth2_token",
            return_value=claims,
        ):
            profile = google_oauth_service.exchange_google_code("google-code")

        self.assertEqual(profile["google_sub"], "google-user-1")
        self.assertEqual(profile["email"], "person@example.com")

    def test_pending_email_link_removes_unverified_password(self):
        user_id = ObjectId()
        pending = {
            "_id": user_id,
            "email": "person@example.com",
            "password_hash": "unverified-hash",
            "email_verified": False,
            "auth_version": 0,
        }
        updated = {
            "_id": user_id,
            "email": "person@example.com",
            "google_sub": "google-user-1",
            "email_verified": True,
            "auth_version": 1,
        }
        users = Mock()
        users.find_one.side_effect = [None, pending, updated]

        with patch.object(google_oauth_service, "user_collection", users):
            user = google_oauth_service.find_or_create_google_user(
                {
                    "email": "person@example.com",
                    "google_sub": "google-user-1",
                    "name": "Person",
                }
            )

        update = users.update_one.call_args.args[1]
        self.assertEqual(update["$unset"], {"password_hash": ""})
        self.assertEqual(update["$inc"], {"auth_version": 1})
        self.assertEqual(user["google_sub"], "google-user-1")

    def test_new_google_user_has_no_password(self):
        users = Mock()
        users.find_one.return_value = None
        users.insert_one.return_value = SimpleNamespace(inserted_id=ObjectId())

        with patch.object(google_oauth_service, "user_collection", users):
            user = google_oauth_service.find_or_create_google_user(
                {
                    "email": "person@example.com",
                    "google_sub": "google-user-1",
                    "name": "Person",
                }
            )

        inserted = users.insert_one.call_args.args[0]
        self.assertNotIn("password_hash", inserted)
        self.assertTrue(inserted["email_verified"])
        self.assertEqual(user["google_sub"], "google-user-1")

    def test_exchange_code_is_one_time_and_expiring(self):
        user_id = ObjectId()
        exchanges = Mock()
        users = Mock()
        exchanges.find_one_and_delete.return_value = {"user_id": user_id}
        users.find_one.return_value = {"_id": user_id, "email": "person@example.com"}

        with patch.object(
            google_oauth_service, "oauth_exchange_collection", exchanges
        ), patch.object(google_oauth_service, "user_collection", users):
            user = google_oauth_service.consume_exchange_code("x" * 43)

        self.assertEqual(user["email"], "person@example.com")
        query = exchanges.find_one_and_delete.call_args.args[0]
        self.assertIn("$gt", query["expires_at"])


class GoogleOAuthRouteTests(unittest.TestCase):
    def test_google_start_sets_state_cookie_and_redirects(self):
        with patch.object(auth.settings, "GOOGLE_CLIENT_ID", "client-id"), patch.object(
            auth.settings, "GOOGLE_CLIENT_SECRET", "client-secret"
        ), patch.object(
            auth.settings,
            "GOOGLE_REDIRECT_URI",
            "https://api.example.com/auth/google/callback",
        ), patch.object(auth, "create_token", return_value="signed-state"), patch.object(
            auth,
            "build_authorization_url",
            return_value="https://accounts.google.com/o/oauth2/v2/auth?state=signed-state",
        ):
            response = auth.google_start()

        self.assertEqual(response.status_code, 307)
        self.assertIn("accounts.google.com", response.headers["location"])
        self.assertIn("google_oauth_state=signed-state", response.headers["set-cookie"])
        self.assertIn("HttpOnly", response.headers["set-cookie"])

    def test_google_callback_creates_only_one_time_exchange_code(self):
        user_id = ObjectId()
        with patch.object(
            auth.jwt,
            "decode",
            return_value={"token_type": "google_oauth_state"},
        ), patch.object(
            auth,
            "exchange_google_code",
            return_value={
                "email": "person@example.com",
                "google_sub": "google-user-1",
                "name": "Person",
            },
        ), patch.object(
            auth,
            "find_or_create_google_user",
            return_value={"_id": user_id, "email": "person@example.com"},
        ), patch.object(
            auth, "create_exchange_code", return_value="x" * 43
        ):
            response = auth.google_callback(
                code="google-code",
                state="signed-state",
                google_state_cookie="signed-state",
            )

        self.assertEqual(response.status_code, 303)
        self.assertIn("/auth/google/callback?code=", response.headers["location"])
        self.assertNotIn("access_token", response.headers["location"])

    def test_google_exchange_issues_existing_asklaw_session(self):
        user = {
            "_id": ObjectId(),
            "email": "person@example.com",
            "email_verified": True,
            "auth_version": 0,
        }
        response = Response()

        with patch.object(auth, "consume_exchange_code", return_value=user), patch.object(
            auth, "create_access_token", return_value="access-token"
        ), patch.object(auth, "create_refresh_token", return_value="refresh-token"):
            result = auth.google_exchange(
                GoogleExchangeRequest(code="x" * 43), response
            )

        self.assertEqual(result["access_token"], "access-token")
        self.assertIn("refresh_token=refresh-token", response.headers["set-cookie"])

    def test_invalid_google_exchange_is_rejected(self):
        with patch.object(auth, "consume_exchange_code", return_value=None):
            with self.assertRaises(HTTPException) as caught:
                auth.google_exchange(
                    GoogleExchangeRequest(code="x" * 43), Response()
                )

        self.assertEqual(caught.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
