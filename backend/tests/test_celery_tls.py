import os
import ssl
import unittest
import warnings


os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("ALGORITHM", "HS256")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "15")
os.environ.setdefault("REFRESH_TOKEN_EXPIRE_DAYS", "7")
os.environ.setdefault("GROQ_API_KEY", "test-groq-key")


from app.core.celery_app import create_celery_app


class CeleryRedisTlsTests(unittest.TestCase):
    def test_local_redis_urls_do_not_enable_tls(self):
        app = create_celery_app(
            broker_url="redis://localhost:6379/0",
            result_backend="redis://localhost:6379/1",
        )

        self.assertFalse(app.conf.broker_use_ssl)
        self.assertIsNone(app.conf.redis_backend_use_ssl)

    def test_rediss_urls_require_verified_certificates(self):
        secure_url = (
            "rediss://default:test-password@example.upstash.io:6379/0"
        )

        with warnings.catch_warnings(record=True) as caught_warnings:
            warnings.simplefilter("always")
            app = create_celery_app(
                broker_url=secure_url,
                result_backend=secure_url,
            )
            broker_connection = app.connection_for_write()
            backend = app.backend

        self.assertEqual(
            app.conf.broker_use_ssl,
            {"ssl_cert_reqs": ssl.CERT_REQUIRED},
        )
        self.assertEqual(
            app.conf.redis_backend_use_ssl,
            {"ssl_cert_reqs": ssl.CERT_REQUIRED},
        )
        self.assertEqual(
            broker_connection.ssl["ssl_cert_reqs"],
            ssl.CERT_REQUIRED,
        )
        self.assertEqual(
            backend.connparams["ssl_cert_reqs"],
            ssl.CERT_REQUIRED,
        )
        self.assertFalse(
            any(
                "Secure redis scheme specified (rediss) with no ssl options"
                in str(warning.message)
                for warning in caught_warnings
            )
        )


if __name__ == "__main__":
    unittest.main()
