from __future__ import annotations

import io
import logging
from typing import Any

import requests
from PIL import Image

from app.config import DownloadConfig, ModelConfig, ProviderConfig
from app.errors import ConfigError, NonRetryableError
from app.models import GenerateMessage
from app.prompt import build_final_prompt
from app.providers.base import ImageProvider
from app.retry import retry_call

logger = logging.getLogger(__name__)


class SeedreamProvider(ImageProvider):
    """Volcano Ark Seedream image generation provider."""

    DEFAULT_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"

    def __init__(self, download_config: DownloadConfig) -> None:
        super().__init__(download_config)
        self._session = requests.Session()

    def generate(
        self,
        message: GenerateMessage,
        model: ModelConfig,
        provider: ProviderConfig,
    ) -> bytes:
        if not message.imageUrl.strip():
            raise NonRetryableError("imageUrl is empty")
        if not provider.api_key.strip():
            raise ConfigError(f"provider {provider.name}: missing api_key")

        prompt = build_final_prompt(message.promptTemplate, message.userPrompt)
        extra = model.extra
        output_url = self._generate_image_url(
            provider=provider,
            model=model,
            prompt=prompt,
            image_url=message.imageUrl.strip(),
            size=str(extra.get("size", "2K")),
            output_format=str(extra.get("output_format", "png")),
            response_format=str(extra.get("response_format", "url")),
            watermark=bool(extra.get("watermark", False)),
            sequential_image_generation=str(
                extra.get("sequential_image_generation", "disabled")
            ),
            optimize_prompt_options=extra.get("optimize_prompt_options"),
            seed=extra.get("seed"),
        )
        image_bytes = self._download_image(output_url)
        return self._to_png_bytes(image_bytes)

    def _generate_image_url(
        self,
        *,
        provider: ProviderConfig,
        model: ModelConfig,
        prompt: str,
        image_url: str,
        size: str,
        output_format: str,
        response_format: str,
        watermark: bool,
        sequential_image_generation: str,
        optimize_prompt_options: Any,
        seed: Any,
    ) -> str:
        endpoint = self._endpoint(provider)
        payload: dict[str, Any] = {
            "model": model.req_key or model.key,
            "prompt": prompt,
            "image": image_url,
            "size": size,
            "response_format": response_format,
            "output_format": output_format,
            "watermark": watermark,
            "sequential_image_generation": sequential_image_generation,
            "stream": False,
        }
        if optimize_prompt_options is not None:
            payload["optimize_prompt_options"] = optimize_prompt_options
        if seed is not None and str(seed).strip().lower() not in {"", "random"}:
            payload["seed"] = int(seed)

        headers = {
            "Authorization": f"Bearer {provider.api_key}",
            "Content-Type": "application/json",
        }

        logger.info(
            "calling Seedream modelKey=%s reqKey=%s prompt_len=%d imageUrl=%s",
            model.key,
            model.req_key,
            len(prompt),
            image_url,
        )

        try:
            resp = self._session.post(
                endpoint,
                json=payload,
                headers=headers,
                timeout=float(
                    model.extra.get(
                        "timeout_seconds",
                        self._download_config.timeout_seconds,
                    )
                ),
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            raise NonRetryableError(f"Seedream request failed: {exc}") from exc
        except ValueError as exc:
            raise NonRetryableError(f"Seedream response is not JSON: {exc}") from exc

        return self._extract_image_url(data)

    @classmethod
    def _endpoint(cls, provider: ProviderConfig) -> str:
        base_url = (provider.base_url or cls.DEFAULT_BASE_URL).rstrip("/")
        return f"{base_url}/images/generations"

    @staticmethod
    def _extract_image_url(payload: dict[str, Any]) -> str:
        error = payload.get("error")
        if error:
            raise NonRetryableError(f"Seedream generation failed: {error}")

        data = payload.get("data")
        if not isinstance(data, list) or not data:
            raise NonRetryableError(f"Seedream response missing data: {payload}")

        for item in data:
            if not isinstance(item, dict):
                continue
            item_error = item.get("error")
            if item_error:
                raise NonRetryableError(
                    f"Seedream image generation failed: {item_error}"
                )
            url = str(item.get("url") or "").strip()
            if url:
                return url

        raise NonRetryableError(f"Seedream response missing image URL: {payload}")

    def _download_image(self, url: str) -> bytes:
        def _do_download() -> bytes:
            resp = self._session.get(url, timeout=self._download_config.timeout_seconds)
            resp.raise_for_status()
            if not resp.content:
                raise NonRetryableError("downloaded Seedream image is empty")
            return resp.content

        try:
            return retry_call(
                _do_download,
                max_attempts=self._download_config.max_retries,
                interval_seconds=self._download_config.retry_interval_seconds,
                retryable_exceptions=(requests.RequestException, NonRetryableError),
            )
        except Exception as exc:
            raise NonRetryableError(f"failed to download Seedream image: {exc}") from exc

    @staticmethod
    def _to_png_bytes(raw_bytes: bytes) -> bytes:
        try:
            with Image.open(io.BytesIO(raw_bytes)) as img:
                converted = (
                    img.convert("RGBA")
                    if img.mode in ("RGBA", "LA")
                    else img.convert("RGB")
                )
                buf = io.BytesIO()
                converted.save(buf, format="PNG")
                return buf.getvalue()
        except Exception as exc:
            raise NonRetryableError(
                f"failed to convert Seedream image to PNG: {exc}"
            ) from exc
