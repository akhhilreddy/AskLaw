import asyncio
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("ALGORITHM", "HS256")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "15")
os.environ.setdefault("REFRESH_TOKEN_EXPIRE_DAYS", "7")
from fastapi import HTTPException
from redis import Redis
from redis.exceptions import ConnectionError
from redis.retry import Retry
from redis.backoff import NoBackoff
from starlette.requests import Request
from app.core import rate_limit, proxy


class ProxyTests(unittest.TestCase):
    def run_proxy(self, header, hops, peer="127.0.0.1"):
        seen = []
        async def app(scope, _receive, _send):
            seen.append(scope)
        scope = {"type": "http", "path": "/health", "scheme": "http", "client": (peer, 42),
                 "headers": [(b"x-forwarded-for", header.encode()), (b"x-forwarded-proto", b"https")]}
        with patch.object(proxy.settings, "TRUSTED_PROXY_HOPS", hops):
            asyncio.run(proxy.ProxyHopMiddleware(app)(scope, None, None))
        return seen[0]

    def test_right_hand_hop_not_forged_leftmost(self):
        result = self.run_proxy("203.0.113.123, 198.51.100.9, 10.0.0.1", 2)
        self.assertEqual(result["client"][0], "198.51.100.9")
        self.assertEqual(result["scheme"], "https")

    def test_render_three_hops_preserve_client_when_leftmost_is_forged(self):
        chain = "198.51.100.9, 10.0.0.1, 10.0.0.2"
        baseline = self.run_proxy(chain, 3)
        forged = self.run_proxy("203.0.113.123, " + chain, 3)
        self.assertEqual(baseline["client"], ("198.51.100.9", 0))
        self.assertEqual(forged["client"], baseline["client"])
        self.assertEqual(forged["scheme"], "https")

    def test_default_zero_and_malformed_or_short_headers_use_peer(self):
        for header, hops in [("198.51.100.9", 0), ("garbage", 1), ("", 1), ("198.51.100.9", 2), ("bad, 198.51.100.9", 1)]:
            self.assertEqual(self.run_proxy(header, hops)["client"], ("127.0.0.1", 42))


class RedisFailureTests(unittest.TestCase):
    def test_redis_down_fails_open_and_logs_no_exception_details(self):
        with patch.object(rate_limit, "redis_client") as client, self.assertLogs(rate_limit.logger, "WARNING") as logs:
            client.eval.side_effect = ConnectionError("secret-url")
            self.assertIsNone(rate_limit.admit([("test", 1, 60)], active_key="lease", concurrency=1))
            client.zrem.side_effect = ConnectionError("secret-url")
            rate_limit.release(("lease", "token"))
        self.assertNotIn("secret-url", str(logs.output))

    def test_yield_dependency_releases_after_completion_or_exception(self):
        for dependency in [rate_limit.limit_chat, rate_limit.limit_upload]:
            with patch.object(rate_limit, "admit", return_value=("active", "id")), patch.object(rate_limit, "release") as release:
                generator = dependency({"_id": "user"})
                next(generator)
                generator.close()
                release.assert_called_once_with(("active", "id"))

    def test_auth_and_guest_policy_wiring(self):
        request = Mock(spec=Request)
        request.client = Mock(host="198.51.100.9")
        request.url = Mock(path="/auth/login")
        async def body():
            return {"email": "PERSON@example.com"}
        request.json = body
        with patch.object(rate_limit, "admit") as admit:
            asyncio.run(rate_limit.limit_login(request))
            self.assertEqual([(r[1], r[2]) for r in admit.call_args.args[0]], [(5, 300), (20, 60)])
            asyncio.run(rate_limit.limit_signup(request))
            self.assertEqual([(r[1], r[2]) for r in admit.call_args.args[0]], [(3, 3600), (10, 3600)])
            rate_limit.limit_guest(request)
            self.assertEqual([(r[1], r[2]) for r in admit.call_args.args[0]], [(10, 3600)])
        self.assertNotIn("person", rate_limit.bucket("email", "PERSON@example.com"))


@unittest.skipUnless(shutil.which("redis-server"), "Local Redis executable required for atomic Lua tests")
class AtomicRedisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(dir="/tmp")
        cls.socket = cls.directory.name + "/redis.sock"
        cls.process = subprocess.Popen([shutil.which("redis-server"), "--port", "0", "--unixsocket", cls.socket,
                                       "--save", "", "--appendonly", "no"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cls.redis = Redis(unix_socket_path=cls.socket, socket_connect_timeout=.2, socket_timeout=.2,
                          retry=Retry(NoBackoff(), 0))
        for _ in range(100):
            try:
                cls.redis.ping()
                return
            except ConnectionError:
                time.sleep(.02)
        cls.process.terminate()
        cls.process.wait(timeout=5)
        cls.directory.cleanup()
        raise RuntimeError("Local test Redis did not start")

    @classmethod
    def tearDownClass(cls):
        cls.redis.close()
        cls.process.terminate()
        cls.process.wait(timeout=5)
        cls.directory.cleanup()

    def setUp(self):
        self.redis.flushdb()  # Isolated ephemeral Redis, never the application URL.
        self.patch = patch.object(rate_limit, "redis_client", self.redis)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_each_approved_window_rejects_next_request_and_expires(self):
        for name, limit, seconds in [("login-email", 5, 300), ("login-ip", 20, 60), ("signup-email", 3, 3600),
                                      ("signup-ip", 10, 3600), ("guest-ip", 10, 3600), ("chat-minute", 10, 60),
                                      ("chat-day", 100, 86400), ("upload-hour", 5, 3600)]:
            with self.subTest(name=name):
                for _ in range(limit):
                    rate_limit.admit([(name, limit, seconds)])
                with self.assertRaises(HTTPException) as failure:
                    rate_limit.admit([(name, limit, seconds)])
                self.assertEqual(failure.exception.status_code, 429)
                self.assertGreater(int(failure.exception.headers["Retry-After"]), 0)
                self.assertGreater(self.redis.ttl(name), 0)

    def test_concurrency_shared_across_clients_release_and_stale_recovery(self):
        for limit in [1, 2]:
            key = f"active-{limit}"
            leases = [rate_limit.admit([], active_key=key, concurrency=limit) for _ in range(limit)]
            with self.assertRaises(HTTPException):
                rate_limit.admit([], active_key=key, concurrency=limit)
            rate_limit.release(leases[0])
            replacement = rate_limit.admit([], active_key=key, concurrency=limit)
            self.assertGreater(self.redis.ttl(key), 0)
            self.redis.zadd(key, {replacement[1]: 1})
            self.assertIsNotNone(rate_limit.admit([], active_key=key, concurrency=limit))

    def test_rejected_bucket_does_not_charge_other_counters(self):
        self.redis.set("full", 1, ex=60)
        with self.assertRaises(HTTPException):
            rate_limit.admit([("empty", 5, 300), ("full", 1, 60)])
        self.assertIsNone(self.redis.get("empty"))
