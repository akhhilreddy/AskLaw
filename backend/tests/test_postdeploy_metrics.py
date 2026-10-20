import unittest
from unittest.mock import AsyncMock, patch

from evaluation import measure_postdeploy, measure_resume, diagnose_stream


class PostdeployMetricsTests(unittest.IsolatedAsyncioTestCase):
    async def test_observer_keeps_original_scoring_and_discards_untrusted_status_text(self):
        observation = measure_postdeploy.ObservedStream()
        observation.consume({"type": "progress", "code": "provider_retrying", "message": "private"}, 1)
        observation.consume({"type": "progress", "code": "private"}, 2)
        observation.consume({"type": "token", "content": "partial"}, 3)
        observation.consume({"type": "error", "code": "generation_busy", "message": "private"}, 4)
        result = observation.result(5, 200)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["first_answer_seconds"], 3)
        self.assertEqual(result["progress_codes"], {"provider_retrying": 1})
        self.assertEqual(result["error_codes"], {"generation_busy": 1})
        self.assertNotIn("private", str(result))

    async def test_patches_restore_and_only_web_measurement_is_requested(self):
        original_request = measure_resume.web_request
        original_observer = diagnose_stream.StreamObservation
        with patch.object(measure_resume, "measure", new=AsyncMock(return_value={})) as benchmark:
            result = await measure_postdeploy.measure()
        benchmark.assert_awaited_once_with(True, web_only=True, health_timeout_seconds=100)
        self.assertIs(measure_resume.web_request, original_request)
        self.assertIs(diagnose_stream.StreamObservation, original_observer)
        self.assertIn("entrypoint_sha256", result["instrumentation"])
