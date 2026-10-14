import os
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("ALGORITHM", "HS256")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "15")
os.environ.setdefault("REFRESH_TOKEN_EXPIRE_DAYS", "7")
os.environ.setdefault("GROQ_API_KEY", "test-groq-key")

from bson import ObjectId
from fastapi import HTTPException, Response
from jose import jwt
from app.api import auth, document, conversation
from app.core import dependencies
from app.core.config import settings
from app.services import guest_service, conversation_service


class GuestDemoTests(unittest.TestCase):
    def guest(self, count=0):
        return {"_id": ObjectId(), "name": "Guest", "email": "demo@guest.asklaw.invalid",
                "is_guest": True, "email_verified": True, "auth_version": 0,
                "guest_chat_count": count,
                "guest_expires_at": datetime.now(timezone.utc) + timedelta(hours=1)}

    def test_creates_temporary_account_and_normal_session(self):
        users = Mock()
        users.insert_one.return_value = SimpleNamespace(inserted_id=ObjectId())
        response = Response()
        before = datetime.now(timezone.utc)
        with patch.object(guest_service, "user_collection", users):
            result = auth.guest_login(response, refresh_token=None)
        record = users.insert_one.call_args.args[0]
        self.assertTrue(record["is_guest"])
        self.assertNotIn("password_hash", record)
        self.assertEqual(record["guest_chat_count"], 0)
        self.assertAlmostEqual((record["guest_expires_at"] - before).total_seconds(), 3600, delta=2)
        self.assertEqual(result["questions_remaining"], 5)
        payload = jwt.decode(result["access_token"], settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        self.assertEqual(payload["token_type"], "access")
        self.assertEqual(payload["sub"], record["email"])
        self.assertIn("HttpOnly", response.headers["set-cookie"])
        self.assertRegex(response.headers["set-cookie"], r"Max-Age=359[89]")
        with patch.object(dependencies, "user_collection") as collection:
            collection.find_one.return_value = record
            self.assertEqual(dependencies.get_current_user(result["access_token"]), record)

    def test_repeat_guest_entry_reuses_quota_and_identity(self):
        guest = self.guest(4)
        token = auth.create_refresh_token(auth._token_payload(guest))
        with patch.object(auth, "user_collection") as users, patch.object(auth, "create_guest_user") as create:
            users.find_one.return_value = guest
            result = auth.guest_login(Response(), token)
        create.assert_not_called()
        self.assertEqual(result["questions_remaining"], 1)

    def test_guest_expires_for_bearer_and_refresh_even_before_ttl_cleanup(self):
        guest = self.guest()
        guest["guest_expires_at"] = datetime.now(timezone.utc) - timedelta(seconds=1)
        # A still-valid JWT cannot bypass the account's expiry.
        for module, call, token in [
            (dependencies, dependencies.get_current_user, auth.create_access_token(auth._token_payload(guest))),
            (auth, auth.refresh_access_token, auth.create_refresh_token(auth._token_payload(guest))),
        ]:
            with patch.object(module, "user_collection") as users:
                users.find_one.return_value = guest
                with self.assertRaises(HTTPException) as failure:
                    call(token)
                self.assertEqual(failure.exception.status_code, 401)

    def test_five_questions_then_quota_error_with_atomic_filter(self):
        guest = self.guest()
        users = Mock()
        users.update_one.side_effect = [SimpleNamespace(modified_count=1)] * 5 + [SimpleNamespace(modified_count=0)]
        with patch.object(guest_service, "user_collection", users):
            for _ in range(5):
                guest_service.consume_guest_question(guest)
            with self.assertRaises(HTTPException) as failure:
                guest_service.consume_guest_question(guest)
        self.assertEqual(failure.exception.status_code, 429)
        query, update = users.update_one.call_args.args
        self.assertEqual(query["_id"], guest["_id"])
        self.assertEqual(query["guest_chat_count"], {"$lt": 5})
        self.assertIn("$gt", query["guest_expires_at"])
        self.assertEqual(update, {"$inc": {"guest_chat_count": 1}})

    def test_registered_users_have_no_demo_limit(self):
        with patch.object(guest_service, "user_collection") as users:
            guest_service.consume_guest_question({"_id": ObjectId()})
            guest_service.ensure_guest_active({"_id": ObjectId()})
            users.update_one.assert_not_called()

    def test_guest_upload_and_passkey_registration_are_blocked(self):
        guest = self.guest()
        for call in [lambda: document.upload_document(Mock(), guest),
                     lambda: auth.passkey_registration_options(guest),
                     lambda: auth.passkey_registration_verify(Mock(), guest)]:
            with self.assertRaises(HTTPException) as failure:
                call()
            self.assertEqual(failure.exception.status_code, 403)

    def test_guest_conversation_has_same_expiry_and_owner(self):
        guest = self.guest()
        with patch.object(conversation, "create_conversation") as create:
            conversation.create_new_conversation(guest)
        create.assert_called_once_with(user_id=str(guest["_id"]), guest_expires_at=guest["guest_expires_at"])
        with patch.object(conversation_service, "conversation_collection") as collection:
            def insert(record):
                record["_id"] = ObjectId()
                return SimpleNamespace(inserted_id=record["_id"])
            collection.insert_one.side_effect = insert
            conversation_service.create_conversation(str(guest["_id"]), guest["guest_expires_at"])
        self.assertEqual(collection.insert_one.call_args.args[0]["guest_expires_at"], guest["guest_expires_at"])

    def test_stream_route_enforces_quota_before_starting_generation(self):
        from app.api import chat
        from app.schemas.chat import ChatRequest
        request = ChatRequest(messages=[{"role": "user", "content": "What is an affidavit?"}])
        guest = self.guest()
        with patch.object(chat, "consume_guest_question") as quota, patch.object(chat, "stream_response", return_value=iter([])) as stream:
            response = chat.chat_stream(request, guest)
            self.assertEqual(response.status_code, 200)
            quota.assert_called_once_with(guest)
            stream.assert_called_once_with(request.messages, str(guest["_id"]), None)
            stream.reset_mock()
            quota.side_effect = HTTPException(429, "Guest quota exhausted")
            with self.assertRaises(HTTPException) as failure:
                chat.chat_stream(request, guest)
            self.assertEqual(failure.exception.status_code, 429)
            stream.assert_not_called()

    def test_guest_endpoint_uses_existing_origin_protection(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        app = FastAPI()
        app.include_router(auth.router, prefix="/auth")
        with TestClient(app) as client, patch.object(auth, "create_guest_user", return_value=self.guest()) as create, patch("app.core.rate_limit.redis_client.eval", return_value=0):
            rejected = client.post("/auth/guest", headers={"Origin": "https://untrusted.example"})
            self.assertEqual(rejected.status_code, 403)
            create.assert_not_called()
            accepted = client.post("/auth/guest")
            self.assertEqual(accepted.status_code, 200)
            self.assertEqual(accepted.json()["questions_remaining"], 5)

    def test_guest_ttl_indexes_do_not_expire_normal_records(self):
        from app.db import mongodb
        with patch.object(mongodb, "user_collection") as users, patch.object(mongodb, "conversation_collection") as chats:
            # Other collection indexes are mocked too: this test never uses a database.
            with patch.object(mongodb, "document_collection"), patch.object(mongodb, "auth_code_collection"), patch.object(mongodb, "oauth_exchange_collection"), patch.object(mongodb, "passkey_collection"), patch.object(mongodb, "passkey_challenge_collection"):
                mongodb.ensure_indexes()
        users.create_index.assert_any_call("guest_expires_at", expireAfterSeconds=0, name="guest_users_expiry_ttl")
        chats.create_index.assert_any_call("guest_expires_at", expireAfterSeconds=0, name="guest_conversations_expiry_ttl")


if __name__ == "__main__":
    unittest.main()
