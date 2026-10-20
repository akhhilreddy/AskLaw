from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
import unittest

from evaluation import check_compact_prompt


class CompactPromptSmokeTests(unittest.IsolatedAsyncioTestCase):
    async def test_async_response_parse_is_awaited_and_no_text_or_credentials_saved(self):
        parsed = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="Review the private receipt if the owner disputes it."))],
                                 usage=SimpleNamespace(prompt_tokens=100, completion_tokens=20, total_tokens=120))
        raw = SimpleNamespace(status_code=200, parse=AsyncMock(return_value=parsed))
        client = MagicMock()
        client.with_raw_response.chat.completions.create = AsyncMock(return_value=raw)
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=client)
        context.__aexit__ = AsyncMock(return_value=False)
        with patch.object(check_compact_prompt, "AsyncGroq", return_value=context):
            report = await check_compact_prompt.check()
        raw.parse.assert_awaited_once()
        self.assertTrue(report["nonempty_answer"])
        self.assertEqual(report["usage"]["total_tokens"], 120)
        self.assertNotIn("private receipt", str(report))
        self.assertEqual(client.with_raw_response.chat.completions.create.await_count, 1)

    async def test_failure_is_retained_without_retry_or_error_body(self):
        client = MagicMock()
        client.with_raw_response.chat.completions.create = AsyncMock(side_effect=TimeoutError("private provider body"))
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=client)
        context.__aexit__ = AsyncMock(return_value=False)
        with patch.object(check_compact_prompt, "AsyncGroq", return_value=context):
            report = await check_compact_prompt.check()
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["failure"], {"category": "timeout"})
        self.assertNotIn("private", str(report))
        self.assertEqual(client.with_raw_response.chat.completions.create.await_count, 1)
