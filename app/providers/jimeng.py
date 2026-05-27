from __future__ import annotations

import io
import json
import logging
import os
import time
from typing import Any

import requests
from PIL import Image
from volcengine.visual.VisualService import VisualService

from app.config import AppConfig, ModelConfig
from app.errors import ConfigError, NonRetryableError
from app.models import GenerateMessage
from app.prompt import build_final_prompt
from app.retry import retry_call

logger = logging.getLogger(__name__)


class JimengProvider:
    """即梦图片生成 4.0（jimeng_t2i_v40）。"""

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._visual: VisualService | None = None

    def _get_client(self) -> VisualService:
        if self._visual is None:
            self._visual = self._build_client()
        return self._visual

    def _build_client(self) -> VisualService:
        ak = os.environ.get("VOLC_ACCESS_KEY_ID", "").strip()
        sk = os.environ.get("VOLC_SECRET_ACCESS_KEY", "").strip()
        if not ak or not sk:
            raise ConfigError("缺少 VOLC_ACCESS_KEY_ID 或 VOLC_SECRET_ACCESS_KEY")

        svc = VisualService()
        svc.set_ak(ak)
        svc.set_sk(sk)
        host = os.environ.get("VOLC_VISUAL_HOST", "visual.volcengineapi.com").strip()
        if host:
            svc.set_host(host)
        return svc

    def generate_png(self, message: GenerateMessage, model: ModelConfig) -> bytes:
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
            "调用即梦 taskId=%s modelKey=%s style=%s prompt_len=%d imageUrl=%s",
            message.taskId,
            model.key,
            message.style,
            len(prompt),
            message.imageUrl,
        )

        jimeng_task_id = self._submit_task(
            model=model,
            prompt=prompt,
            image_url=message.imageUrl.strip(),
            scale=scale,
            force_single=force_single,
            return_url=return_url,
        )
        logger.info("即梦任务已提交 taskId=%s jimeng_task_id=%s", message.taskId, jimeng_task_id)

        result = self._wait_task(
            model=model,
            jimeng_task_id=jimeng_task_id,
            poll_interval_sec=poll_interval,
            timeout_sec=timeout_seconds,
            return_url=return_url,
        )
        image_url = self._extract_image_url(result)
        raw_bytes = self._download_image(image_url)
        return self._to_png_bytes(raw_bytes)

    def _req_json(self, return_url: bool) -> str:
        return json.dumps({"return_url": return_url}, separators=(",", ":"))

    def _submit_task(
        self,
        *,
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
            "req_json": self._req_json(return_url),
            "image_urls": [image_url],
        }
        resp = self._get_client().cv_sync2async_submit_task(form)
        if resp.get("code") != 10000:
            raise NonRetryableError(f"即梦提交失败: {json.dumps(resp, ensure_ascii=False)}")
        task_id = (resp.get("data") or {}).get("task_id")
        if not task_id:
            raise NonRetryableError(f"即梦提交响应缺少 task_id: {json.dumps(resp, ensure_ascii=False)}")
        return str(task_id)

    def _wait_task(
        self,
        *,
        model: ModelConfig,
        jimeng_task_id: str,
        poll_interval_sec: float,
        timeout_sec: float,
        return_url: bool,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_sec
        last: dict[str, Any] = {}

        while time.monotonic() < deadline:
            last = self._get_client().cv_sync2async_get_result(
                {
                    "req_key": model.req_key,
                    "task_id": jimeng_task_id,
                    "req_json": self._req_json(return_url),
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
        download_cfg = self._config.download

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
