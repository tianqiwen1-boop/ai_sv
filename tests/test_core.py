import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.callback import BackendCallbackClient
from app.config import load_config
from app.errors import NonRetryableError
from app.models import GenerateMessage
from app.prompt import build_final_prompt


class PromptTest(unittest.TestCase):
    def test_template_only(self) -> None:
        self.assertEqual(build_final_prompt("固定提示词", ""), "固定提示词")

    def test_template_and_user(self) -> None:
        self.assertEqual(build_final_prompt("固定提示词", "补充说明"), "固定提示词 补充说明")

    def test_empty_template_raises(self) -> None:
        with self.assertRaises(NonRetryableError):
            build_final_prompt("", "补充")


class MessageTest(unittest.TestCase):
    def test_parse_message(self) -> None:
        raw = {
            "taskId": "AI123",
            "imageUrl": "https://example.com/a.png",
            "userPrompt": "hello",
            "style": "Q版",
            "promptTemplate": "template",
            "modelKey": "jimeng-t2i-v40",
            "createdAt": "2026-05-25 12:00:00",
        }
        msg = GenerateMessage.model_validate(raw)
        self.assertEqual(msg.taskId, "AI123")
        self.assertEqual(msg.modelKey, "jimeng-t2i-v40")


class ConfigTest(unittest.TestCase):
    def test_load_config_with_env(self) -> None:
        example = Path(__file__).resolve().parents[1] / "config" / "config.example.yaml"
        env = {
            "CALLBACK_URL": "http://localhost:8081/api/ai/task/callback",
            "AI_CALLBACK_TOKEN": "test-token",
            "S3_ACCESS_KEY": "ak",
            "S3_SECRET_KEY": "sk",
            "S3_BUCKET": "bucket",
            "S3_PUBLIC_BASE_URL": "https://example.com",
            "S3_ENDPOINT": "https://cos.example.com",
        }
        with patch.dict(os.environ, env, clear=False):
            config = load_config(str(example))
            self.assertEqual(config.service.default_model, "jimeng-t2i-v40")
            model = config.get_model("jimeng-t2i-v40")
            self.assertEqual(model.provider, "jimeng")
            self.assertEqual(model.extra["poll_interval_seconds"], 2)


class CallbackTest(unittest.TestCase):
    def test_success_callback(self) -> None:
        from app.config import ServiceConfig

        cfg = ServiceConfig(
            name="ai-service",
            log_level="INFO",
            callback_url="http://localhost/callback",
            callback_token="token",
            callback_timeout_seconds=5,
            callback_max_retries=1,
            callback_retry_interval_seconds=1,
            default_model="jimeng-t2i-v40",
        )
        client = BackendCallbackClient(cfg)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"code": 0, "message": "ok", "data": None}

        with patch.object(client._session, "post", return_value=mock_resp) as post:
            client.processing("AI123")
            post.assert_called_once()
            payload = post.call_args.kwargs["json"]
            self.assertEqual(payload["status"], "PROCESSING")
            self.assertIsNone(payload["aiImageUrl"])
            self.assertIsNone(payload["errorMessage"])


if __name__ == "__main__":
    unittest.main()
