from __future__ import annotations

import io
import json
import logging
import time
from typing import Any

import requests
from PIL import Image
from volcengine.visual.VisualService import VisualService

from app.config import DownloadConfig, ModelConfig, ProviderConfig
from app.errors import ConfigError, NonRetryableError
from app.models import GenerateMessage
from app.prompt import build_final_prompt
from app.providers.base import ImageProvider
from app.retry import retry_call

logger = logging.getLogger(__name__)


class JimengProvider(ImageProvider):
    """即梦图片生成 4.0（jimeng_t2i_v40）。"""

    def __init__(self, download_config: DownloadConfig) -> None:
        super().__init__(download_config)
        self._visual_cache: dict[str, VisualService] = {}

    def _get_client(self, provider: ProviderConfig) -> VisualService:
        if provider.name not in self._visual_cache:
            self._visual_cache[provider.name] = self._build_client(provider)
        return self._visual_cache[provider.name]

    @staticmethod
    def _build_client(provider: ProviderConfig) -> VisualService:
        ak = provider.api_key
        sk = provider.api_secret
        if not ak or not sk:
            raise ConfigError(
                f"provider {provider.name}: 缺少 api_key（AK）或 api_secret（SK）"
            )

        svc = VisualService()
        svc.set_ak(ak)
        svc.set_sk(sk)
        if provider.base_url:
            svc.set_host(provider.base_url)
        return svc

    def generate(
        self,
        message: GenerateMessage,
        model: ModelConfig,
        provider: ProviderConfig,
    ) -> bytes:
        if not message.imageUrl.strip():
            raise NonRetryableError("imageUrl 为空")

        prompt = build_final_prompt(message.promptTemplate, message.userPrompt)
        extra = model.extra
        scale = float(extra.get("scale", 0.5))
        force_single = int(extra.get("force_single", 1))
        poll_interval = float(extra.get("poll_interval_seconds", 2))
        timeout_seconds = float(extra.get("timeout_seconds", 300))
        return_url = bool(extra.get("return_url", True))

        logger.info(
            "调用即梦 taskId=%s modelKey=%s provider=%s style=%s prompt_len=%d imageUrl=%s",
            message.taskId,
            model.key,
            provider.name,
            message.style,
            len(prompt),
            message.imageUrl,
        )

        client = self._get_client(provider)
        jimeng_task_id = self._submit_task(
            client=client,
            model=model,
            prompt=prompt,
            image_url=message.imageUrl.strip(),
            scale=scale,
            force_single=force_single,
            return_url=return_url,
        )
        logger.info("即梦任务已提交 taskId=%s jimeng_task_id=%s", message.taskId, jimeng_task_id)

        result = self._wait_task(
            client=client,
            model=model,
            jimeng_task_id=jimeng_task_id,
            poll_interval_sec=poll_interval,
            timeout_sec=timeout_seconds,
            return_url=return_url,
        )
        image_url = self._extract_image_url(result)
        raw_bytes = self._download_image(image_url)
        return self._to_png_bytes(raw_bytes)

    @staticmethod
    def _req_json(return_url: bool) -> str:
        return json.dumps({"return_url": return_url}, separators=(",", ":"))

    @staticmethod
    def _submit_task(
        *,
        client: VisualService,
        model: ModelConfig,
        prompt: str,
        image_url: str,
        scale: float,
        force_single: int,
        return_url: bool,
    ) -> str:
        form: dict[str, Any] = {
            "req_key": model.req_key,
            "prompt": prompt,
            "scale": scale,
            "force_single": force_single,
            "req_json": JimengProvider._req_json(return_url),
            "image_urls": [image_url],
        }
        resp = client.cv_sync2async_submit_task(form)
        if resp.get("code") != 10000:
            raise NonRetryableError(f"即梦提交失败: {json.dumps(resp, ensure_ascii=False)}")
        task_id = (resp.get("data") or {}).get("task_id")
        if not task_id:
            raise NonRetryableError(f"即梦提交响应缺少 task_id: {json.dumps(resp, ensure_ascii=False)}")
        return str(task_id)

    @staticmethod
    def _wait_task(
        *,
        client: VisualService,
        model: ModelConfig,
        jimeng_task_id: str,
        poll_interval_sec: float,
        timeout_sec: float,
        return_url: bool,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_sec
        last: dict[str, Any] = {}

        while time.monotonic() < deadline:
            last = client.cv_sync2async_get_result(
                {
                    "req_key": model.req_key,
                    "task_id": jimeng_task_id,
                    "req_json": JimengProvider._req_json(return_url),
                }
            )
            if last.get("code") != 10000:
                raise NonRetryableError(f"即梦查询失败: {json.dumps(last, ensure_ascii=False)}")

            status = (last.get("data") or {}).get("status")
            if status == "done":
                return last
            if status in ("not_found", "expired"):
                raise NonRetryableError(f"即梦任务异常结束: {json.dumps(last, ensure_ascii=False)}")
            time.sleep(poll_interval_sec)

        raise NonRetryableError(f"即梦任务超时: {json.dumps(last, ensure_ascii=False)}")

    @staticmethod
    def _extract_image_url(result: dict[str, Any]) -> str:
        data = result.get("data") or {}
        urls = data.get("image_urls") or []
        for item in urls:
            if isinstance(item, str) and item.strip() and not item.startswith("data:image/"):
                return item.strip()

        for item in data.get("binary_data_base64") or []:
            if isinstance(item, str) and item.startswith("http"):
                return item.strip()

        raise NonRetryableError("即梦结果中未找到可下载的图片 URL")

    def _download_image(self, url: str) -> bytes:
        download_cfg = self._download_config

        def _do_download() -> bytes:
            resp = requests.get(url, timeout=download_cfg.timeout_seconds)
            resp.raise_for_status()
            if not resp.content:
                raise NonRetryableError("下载即梦结果图为空")
            return resp.content

        try:
            return retry_call(
                _do_download,
                max_attempts=download_cfg.max_retries,
                interval_seconds=download_cfg.retry_interval_seconds,
                retryable_exceptions=(requests.RequestException, NonRetryableError),
            )
        except Exception as exc:
            raise NonRetryableError(f"下载即梦结果图失败: {exc}") from exc

    @staticmethod
    def _to_png_bytes(raw_bytes: bytes) -> bytes:
        try:
            with Image.open(io.BytesIO(raw_bytes)) as img:
                if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
                    converted = img.convert("RGBA")
                else:
                    converted = img.convert("RGB")
                buf = io.BytesIO()
                converted.save(buf, format="PNG")
                return buf.getvalue()
        except Exception as exc:
            raise NonRetryableError(f"转换 PNG 失败: {exc}") from exc
