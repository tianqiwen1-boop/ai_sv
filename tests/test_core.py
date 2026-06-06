import os
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.callback import BackendCallbackClient
from app.config import load_config
from app.errors import NonRetryableError
from app.grid_selector import choose_final_grid_size, resolve_candidate_grids
from app.models import GenerateMessage
from app.perfect_pixel_processor import PerfectPixelProcessor
from app.prompt import build_final_prompt


class PromptTest(unittest.TestCase):
    def test_template_only(self) -> None:
        self.assertEqual(build_final_prompt("template", ""), "template")

    def test_template_and_user(self) -> None:
        self.assertEqual(build_final_prompt("template", "extra"), "template extra")

    def test_empty_template_raises(self) -> None:
        with self.assertRaises(NonRetryableError):
            build_final_prompt("", "extra")


class MessageTest(unittest.TestCase):
    def test_parse_message(self) -> None:
        raw = {
            "taskId": "AI123",
            "imageUrl": "https://example.com/a.png",
            "userPrompt": "hello",
            "style": "portrait",
            "promptTemplate": "template",
            "modelKey": "jimeng-t2i-v40",
            "sizeMode": "default",
            "gridMin": 30,
            "gridMax": 80,
            "candidateGrids": [32, 36, 40, 44, 48, 56, 64, 72, 80],
            "createdAt": "2026-05-25 12:00:00",
        }
        msg = GenerateMessage.model_validate(raw)
        self.assertEqual(msg.taskId, "AI123")
        self.assertEqual(msg.modelKey, "jimeng-t2i-v40")
        self.assertEqual(msg.gridMin, 30)


class GridSelectorTest(unittest.TestCase):
    def test_default_candidates_snap_detected(self) -> None:
        msg = GenerateMessage(
            taskId="AI123",
            imageUrl="https://example.com/a.png",
            style="portrait",
            promptTemplate="template",
            sizeMode="default",
            gridMin=30,
            gridMax=80,
        )
        self.assertEqual(resolve_candidate_grids(msg), [32, 36, 40, 44, 48, 56, 64, 72, 80])
        self.assertEqual(choose_final_grid_size(msg, 46, 46), 48)

    def test_small_fallback(self) -> None:
        msg = GenerateMessage(
            taskId="AI123",
            imageUrl="https://example.com/a.png",
            style="portrait",
            promptTemplate="template",
            sizeMode="small",
        )
        self.assertEqual(choose_final_grid_size(msg, None, None), 32)


class PerfectPixelProcessorTest(unittest.TestCase):
    def test_detects_center_cross_seam(self) -> None:
        import numpy as np

        image = np.full((48, 48, 3), [80, 60, 70], dtype=np.uint8)
        image[24, :, :] = 255
        image[:, 24, :] = 255

        self.assertTrue(PerfectPixelProcessor._has_center_cross_seam(image))

    def test_allows_plain_white_background(self) -> None:
        import numpy as np

        image = np.full((48, 48, 3), 255, dtype=np.uint8)
        image[12:36, 12:36, :] = [80, 60, 70]

        self.assertFalse(PerfectPixelProcessor._has_center_cross_seam(image))


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
            "VOLC_ACCESS_KEY_ID": "test-ak",
            "VOLC_SECRET_ACCESS_KEY": "test-sk",
            "ARK_API_KEY": "test-ark-key",
        }
        with patch.dict(os.environ, env, clear=False):
            config = load_config(str(example))
            self.assertEqual(config.service.default_model, "seedream-5-lite")
            model = config.get_model("jimeng-t2i-v40")
            self.assertEqual(model.provider, "jimeng")
            self.assertEqual(model.extra["poll_interval_seconds"], 2)
            seedream_model = config.models["seedream-5-lite"]
            self.assertEqual(seedream_model.provider, "seedream")
            self.assertTrue(seedream_model.enabled)


class SeedreamProviderTest(unittest.TestCase):
    def test_extract_image_url(self) -> None:
        from app.providers.seedream import SeedreamProvider

        payload = {
            "data": [
                {
                    "url": "https://example.com/result.png",
                    "size": "2048x2048",
                }
            ]
        }
        self.assertEqual(
            SeedreamProvider._extract_image_url(payload),
            "https://example.com/result.png",
        )

    def test_extract_image_url_raises_on_error(self) -> None:
        from app.providers.seedream import SeedreamProvider

        with self.assertRaises(NonRetryableError):
            SeedreamProvider._extract_image_url({"error": {"message": "bad request"}})

    def test_generate_image_url_payload(self) -> None:
        from app.config import DownloadConfig, ModelConfig, ProviderConfig
        from app.providers.seedream import SeedreamProvider

        provider = SeedreamProvider(
            DownloadConfig(max_retries=1, retry_interval_seconds=0, timeout_seconds=5)
        )
        provider_cfg = ProviderConfig(
            name="seedream",
            type="seedream",
            base_url="https://ark.example.com/api/v3",
            api_key="test-key",
        )
        model = ModelConfig(
            key="seedream-5-lite",
            provider="seedream",
            enabled=True,
            req_key="doubao-seedream-5-0-260128",
            extra={"timeout_seconds": 5},
        )

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "data": [{"url": "https://example.com/output.png"}]
        }
        mock_resp.raise_for_status.return_value = None

        with patch.object(provider._session, "post", return_value=mock_resp) as post:
            url = provider._generate_image_url(
                provider=provider_cfg,
                model=model,
                prompt="pixel prompt",
                image_url="https://example.com/input.png",
                size="2K",
                output_format="png",
                response_format="url",
                watermark=False,
                sequential_image_generation="disabled",
                optimize_prompt_options=None,
                seed=None,
            )

        self.assertEqual(url, "https://example.com/output.png")
        post.assert_called_once()
        self.assertEqual(
            post.call_args.args[0],
            "https://ark.example.com/api/v3/images/generations",
        )
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer test-key")
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["model"], "doubao-seedream-5-0-260128")
        self.assertEqual(payload["prompt"], "pixel prompt")
        self.assertEqual(payload["image"], "https://example.com/input.png")
        self.assertEqual(payload["response_format"], "url")
        self.assertEqual(payload["output_format"], "png")
        self.assertFalse(payload["watermark"])
        self.assertEqual(payload["sequential_image_generation"], "disabled")


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
            client.success(
                "AI123",
                "https://example.com/refined.png",
                image_key="ai-results/dev/refined.png",
                raw_image_url="https://example.com/raw.png",
                raw_image_key="ai-results/dev/raw.png",
                size_mode="default",
                grid_min=30,
                grid_max=80,
                detected_grid_width=46,
                detected_grid_height=46,
                final_grid_width=48,
                final_grid_height=48,
                perfect_pixel_status="SUCCESS",
            )
            post.assert_called_once()
            payload = post.call_args.kwargs["json"]
            self.assertEqual(payload["status"], "SUCCESS")
            self.assertEqual(payload["aiImageUrl"], "https://example.com/refined.png")
            self.assertEqual(payload["aiImageKey"], "ai-results/dev/refined.png")
            self.assertEqual(payload["rawAiImageUrl"], "https://example.com/raw.png")
            self.assertEqual(payload["rawAiImageKey"], "ai-results/dev/raw.png")
            self.assertEqual(payload["finalGridWidth"], 48)
            self.assertIsNone(payload["errorMessage"])


if __name__ == "__main__":
    unittest.main()
