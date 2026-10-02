import os
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("ALGORITHM", "HS256")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "15")
os.environ.setdefault("REFRESH_TOKEN_EXPIRE_DAYS", "7")
os.environ.setdefault("GROQ_API_KEY", "test-groq-key")

from bson import ObjectId
from fastapi import HTTPException, Response
from pydantic import ValidationError

from app.api import auth
from app.schemas.auth import (
    EmailRequest,
    ResetPasswordRequest,
    SignUpRequest,
    UserLogin,
    VerifyEmailRequest,
)
from app.services import auth_code_service, email_service
from app.core.config import Settings
from app.core import dependencies


class EmailAuthenticationRouteTests(unittest.TestCase):
    def test_production_requires_transactional_email_configuration(self):
        with self.assertRaisesRegex(ValidationError, "RESEND_API_KEY"):
            Settings(
                APP_ENV="production",
                SECRET_KEY="x" * 32,
                ALGORITHM="HS256",
                ACCESS_TOKEN_EXPIRE_MINUTES=15,
                REFRESH_TOKEN_EXPIRE_DAYS=7,
                COOKIE_SECURE=True,
                CORS_ORIGINS="https://asklaw.example",
                SEARXNG_URL="https://search.example.com/search",
                FRONTEND_URL="https://asklaw.example",
                RESEND_API_KEY="",
                EMAIL_FROM="",
                _env_file=None,
            )

    def test_signup_creates_pending_user_and_sends_verification_code(self):
        users = Mock()
        users.find_one.return_value = None
        users.insert_one.return_value = SimpleNamespace(inserted_id=ObjectId())

        with patch.object(auth, "user_collection", users), patch.object(
            auth, "hash_password", return_value="hashed"
        ), patch.object(auth, "issue_code", return_value=True) as issue:
            result = auth.signup(
                SignUpRequest(
                    name="Person",
                    email="person@example.com",
                    password="secret123",
                )
            )

        inserted = users.insert_one.call_args.args[0]
        self.assertEqual(result["message"], "Verification code sent")
        self.assertFalse(inserted["email_verified"])
        self.assertEqual(inserted["auth_version"], 0)
        self.assertNotIn("password", inserted)
        issue.assert_called_once_with("person@example.com", auth.VERIFY_EMAIL)

    def test_pending_user_cannot_login(self):
        users = Mock()
        users.find_one.return_value = {
            "_id": ObjectId(),
            "email": "person@example.com",
            "password_hash": "hash",
            "email_verified": False,
            "auth_version": 0,
        }

        with patch.object(auth, "user_collection", users), patch.object(
            auth, "verify_password", return_value=True
        ):
            with self.assertRaises(HTTPException) as caught:
                auth.login(
                    UserLogin(email="person@example.com", password="secret123"),
                    Response(),
                )

        self.assertEqual(caught.exception.status_code, 403)
        self.assertEqual(caught.exception.detail, "Verify your email before signing in")

    def test_repeated_pending_signup_does_not_replace_password_during_cooldown(self):
        user_id = ObjectId()
        users = Mock()
        users.find_one.return_value = {
            "_id": user_id,
            "email": "person@example.com",
            "password_hash": "original-hash",
            "email_verified": False,
        }

        with patch.object(auth, "user_collection", users), patch.object(
            auth, "hash_password", return_value="attacker-hash"
        ), patch.object(auth, "issue_code", return_value=False):
            with self.assertRaises(HTTPException) as caught:
                auth.signup(
                    SignUpRequest(
                        name="Replacement",
                        email="person@example.com",
                        password="replacement123",
                    )
                )

        self.assertEqual(caught.exception.status_code, 429)
        users.update_one.assert_not_called()

    def test_verify_email_consumes_code_and_marks_user_verified(self):
        user_id = ObjectId()
        users = Mock()
        users.find_one.return_value = {
            "_id": user_id,
            "email": "person@example.com",
            "email_verified": False,
        }

        with patch.object(auth, "user_collection", users), patch.object(
            auth, "consume_code", return_value=True
        ) as consume:
            result = auth.verify_email(
                VerifyEmailRequest(email="person@example.com", code="123456")
            )

        self.assertEqual(result["message"], "Email verified successfully")
        consume.assert_called_once_with(
            "person@example.com", auth.VERIFY_EMAIL, "123456"
        )
        update = users.update_one.call_args.args[1]["$set"]
        self.assertTrue(update["email_verified"])
        self.assertIn("email_verified_at", update)

    def test_forgot_password_does_not_reveal_unknown_email(self):
        users = Mock()
        users.find_one.return_value = None

        with patch.object(auth, "user_collection", users), patch.object(
            auth, "issue_code"
        ) as issue:
            result = auth.forgot_password(
                EmailRequest(email="missing@example.com")
            )

        self.assertEqual(
            result["message"],
            "If an account exists, a password reset code has been sent",
        )
        issue.assert_not_called()

    def test_reset_password_hashes_password_and_invalidates_sessions(self):
        user_id = ObjectId()
        users = Mock()
        users.find_one.return_value = {
            "_id": user_id,
            "email": "person@example.com",
            "email_verified": True,
            "auth_version": 3,
        }

        with patch.object(auth, "user_collection", users), patch.object(
            auth, "consume_code", return_value=True
        ), patch.object(auth, "hash_password", return_value="new-hash"):
            result = auth.reset_password(
                ResetPasswordRequest(
                    email="person@example.com",
                    code="123456",
                    new_password="newsecret123",
                )
            )

        self.assertEqual(result["message"], "Password reset successfully")
        update = users.update_one.call_args.args[1]
        self.assertEqual(update["$set"]["password_hash"], "new-hash")
        self.assertEqual(update["$inc"], {"auth_version": 1})

    def test_auth_version_rejects_tokens_issued_before_password_reset(self):
        users = Mock()
        users.find_one.return_value = {
            "_id": ObjectId(),
            "email": "person@example.com",
            "email_verified": True,
            "auth_version": 2,
        }

        with patch.object(
            dependencies, "user_collection", users
        ), patch.object(
            dependencies.jwt,
            "decode",
            return_value={
                "sub": "person@example.com",
                "token_type": "access",
                "auth_version": 1,
            },
        ):
            with self.assertRaises(HTTPException) as caught:
                dependencies.get_current_user("old-access-token")

        self.assertEqual(caught.exception.status_code, 401)


class AuthCodeServiceTests(unittest.TestCase):
    def test_issue_code_stores_only_hash_and_sends_code(self):
        codes = Mock()
        codes.find_one.return_value = None

        with patch.object(
            auth_code_service, "auth_code_collection", codes
        ), patch.object(
            auth_code_service.secrets, "randbelow", return_value=123
        ), patch.object(auth_code_service, "send_auth_code") as send:
            sent = auth_code_service.issue_code(
                "person@example.com", auth_code_service.VERIFY_EMAIL
            )

        self.assertTrue(sent)
        stored = codes.replace_one.call_args.args[1]
        self.assertNotEqual(stored["code_hash"], "000123")
        self.assertNotIn("code", stored)
        send.assert_called_once_with(
            "person@example.com", "000123", auth_code_service.VERIFY_EMAIL
        )

    def test_issue_code_honors_resend_cooldown(self):
        codes = Mock()
        codes.find_one.return_value = {"created_at": datetime.now(timezone.utc)}

        with patch.object(
            auth_code_service, "auth_code_collection", codes
        ), patch.object(auth_code_service, "send_auth_code") as send:
            sent = auth_code_service.issue_code(
                "person@example.com", auth_code_service.VERIFY_EMAIL
            )

        self.assertFalse(sent)
        codes.replace_one.assert_not_called()
        send.assert_not_called()

    def test_invalid_code_increments_attempt_count(self):
        codes = Mock()
        codes.find_one_and_delete.return_value = None

        with patch.object(auth_code_service, "auth_code_collection", codes):
            valid = auth_code_service.consume_code(
                "person@example.com",
                auth_code_service.RESET_PASSWORD,
                "123456",
            )

        self.assertFalse(valid)
        self.assertEqual(
            codes.update_one.call_args.args[1], {"$inc": {"attempts": 1}}
        )


class EmailServiceTests(unittest.TestCase):
    def test_resend_request_contains_code_without_exposing_configuration(self):
        response = Mock()
        response.raise_for_status.return_value = None

        with patch.object(
            email_service.settings, "RESEND_API_KEY", "test-resend-key"
        ), patch.object(
            email_service.settings,
            "EMAIL_FROM",
            "AskLAW <auth@example.com>",
        ), patch.object(email_service.httpx, "post", return_value=response) as post:
            email_service.send_auth_code(
                "person@example.com", "123456", auth_code_service.VERIFY_EMAIL
            )

        request = post.call_args
        self.assertEqual(request.args[0], "https://api.resend.com/emails")
        self.assertEqual(request.kwargs["json"]["to"], ["person@example.com"])
        self.assertIn("123456", request.kwargs["json"]["html"])
        self.assertEqual(
            request.kwargs["headers"]["Authorization"],
            "Bearer test-resend-key",
        )


if __name__ == "__main__":
    unittest.main()
