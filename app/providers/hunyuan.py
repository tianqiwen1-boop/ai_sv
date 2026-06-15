from __future__ import annotations

import io
import logging
import time
from typing import Any

import requests
from PIL import Image

from app.config import DownloadConfig, ModelConfig, ProviderConfig
from app.errors import ConfigError, NonRetryableError
from app.models import GenerateMessage
from app.prompt import build_final_prompt, build_negative_prompt
from app.providers.base import ImageProvider
from app.retry import retry_call

logger = logging.getLogger(__name__)


class HunyuanProvider(ImageProvider):
    """Tencent Hunyuan Image 3.0 provider via TokenHub image submit/query APIs."""

    DEFAULT_BASE_URL = "https://tokenhub.tencentmaas.com/v1/api/image"

    def __init__(self, download_config: DownloadConfig) -> None:
        super().__init__(download_config)
        self._session = requests.Session()

    def generate(
        self,
        message: GenerateMessage,
        model: ModelConfig,
        provider: ProviderConfig,
    ) -> bytes:
        if not provider.api_key.strip():
            raise ConfigError(f"provider {provider.name}: missing api_key")

        prompt = build_final_prompt(message.promptTemplate, message.userPrompt)
        negative_prompt = build_negative_prompt(message.negativePromptTemplate)
        extra = model.extra
        poll_interval = float(extra.get("poll_interval_seconds", 2))
        timeout_seconds = float(extra.get("timeout_seconds", 300))

        job_id = self._submit_job(
            provider=provider,
            model=model,
            prompt=prompt,
            negative_prompt=negative_prompt,
            image_url=message.imageUrl.strip(),
            size=str(extra.get("size", "1024:1024")),
            seed=extra.get("seed"),
            revise=extra.get("revise"),
            logo_add=extra.get("logo_add", 0),
            negative_prompt_field=str(extra.get("negative_prompt_field", "negative_prompt")),
            extra_body=extra.get("extra_body"),
        )
        image_url = self._wait_job(
            provider=provider,
            model=model,
            job_id=job_id,
            poll_interval_sec=poll_interval,
            timeout_sec=timeout_seconds,
        )
        image_bytes = self._download_image(image_url)
        return self._to_png_bytes(image_bytes)

    def _submit_job(
        self,
        *,
        provider: ProviderConfig,
        model: ModelConfig,
        prompt: str,
        negative_prompt: str,
        image_url: str,
        size: str,
        seed: Any,
        revise: Any,
        logo_add: Any,
        negative_prompt_field: str,
        extra_body: Any,
    ) -> str:
        payload: dict[str, Any] = {
            "model": model.req_key or model.key,
            "prompt": prompt,
            "size": size,
        }
        if image_url:
            payload["images"] = [image_url]
        if negative_prompt:
            payload[negative_prompt_field or "negative_prompt"] = negative_prompt
        if seed is not None and str(seed).strip().lower() not in {"", "random"}:
            payload["seed"] = int(seed)
        if revise is not None and str(revise).strip() != "":
            payload["revise"] = int(revise)
        if logo_add is not None and str(logo_add).strip() != "":
            payload["logo_add"] = int(logo_add)
        if isinstance(extra_body, dict):
            payload.update(extra_body)

        logger.info(
            "calling Hunyuan modelKey=%s reqKey=%s prompt_len=%d imageUrl=%s",
            model.key,
            model.req_key,
            len(prompt),
            image_url,
        )
        data = self._post_json(self._submit_endpoint(provider), provider.api_key, payload)
        job_id = str(data.get("id") or data.get("job_id") or "").strip()
        if not job_id:
            raise NonRetryableError(f"Hunyuan submit response missing id: {data}")
        return job_id

    def _wait_job(
        self,
        *,
        provider: ProviderConfig,
        model: ModelConfig,
        job_id: str,
        poll_interval_sec: float,
        timeout_sec: float,
    ) -> str:
        deadline = time.monotonic() + timeout_sec
        last: dict[str, Any] = {}

        while time.monotonic() < deadline:
            last = self._post_json(
                self._query_endpoint(provider),
                provider.api_key,
                {"model": model.req_key or model.key, "id": job_id},
            )
            status = str(last.get("status") or "").strip().lower()
            if status in {"completed", "done", "succeeded", "success", "5"}:
                return self._extract_image_url(last)
            if status in {"failed", "error", "canceled", "cancelled", "expired"}:
                raise NonRetryableError(f"Hunyuan job failed: {last}")
            time.sleep(poll_interval_sec)

        raise NonRetryableError(f"Hunyuan job timed out: {last}")

    def _post_json(self, endpoint: str, api_key: str, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        try:
            resp = self._session.post(
                endpoint,
                json=payload,
                headers=headers,
                timeout=self._download_config.timeout_seconds,
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            raise NonRetryableError(f"Hunyuan request failed: {exc}") from exc
        except ValueError as exc:
            raise NonRetryableError(f"Hunyuan response is not JSON: {exc}") from exc

        error = data.get("error")
        if error:
            raise NonRetryableError(f"Hunyuan API error: {error}")
        return data

    @classmethod
    def _submit_endpoint(cls, provider: ProviderConfig) -> str:
        base_url = (provider.base_url or cls.DEFAULT_BASE_URL).rstrip("/")
        if base_url.endswith("/submit"):
            return base_url
        return f"{base_url}/submit"

    @classmethod
    def _query_endpoint(cls, provider: ProviderConfig) -> str:
        query_url = str(provider.extra.get("query_url") or "").strip()
        if query_url:
            return query_url
        base_url = (provider.base_url or cls.DEFAULT_BASE_URL).rstrip("/")
        if base_url.endswith("/submit"):
            return f"{base_url[:-7]}/query"
        if base_url.endswith("/query"):
            return base_url
        return f"{base_url}/query"

    @staticmethod
    def _extract_image_url(payload: dict[str, Any]) -> str:
        data = payload.get("data")
        if isinstance(data, list):
            for item in data:
                if not isinstance(item, dict):
                    continue
                url = str(item.get("url") or "").strip()
                if url:
                    return url

        url = str(payload.get("url") or "").strip()
        if url:
            return url

        raise NonRetryableError(f"Hunyuan response missing image URL: {payload}")

    def _download_image(self, url: str) -> bytes:
        def _do_download() -> bytes:
            resp = self._session.get(url, timeout=self._download_config.timeout_seconds)
            resp.raise_for_status()
            if not resp.content:
                raise NonRetryableError("downloaded Hunyuan image is empty")
            return resp.content

        try:
            return retry_call(
                _do_download,
                max_attempts=self._download_config.max_retries,
                interval_seconds=self._download_config.retry_interval_seconds,
                retryable_exceptions=(requests.RequestException, NonRetryableError),
            )
        except Exception as exc:
            raise NonRetryableError(f"failed to download Hunyuan image: {exc}") from exc

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
                f"failed to convert Hunyuan image to PNG: {exc}"
            ) from exc
