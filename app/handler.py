from __future__ import annotations

import json
import logging
import time
from typing import TYPE_CHECKING

from pydantic import ValidationError

from app.errors import NonRetryableError
from app.grid_selector import choose_final_grid_size, resolve_grid_range
from app.models import GenerateMessage
from app.perfect_pixel_processor import PerfectPixelProcessor

if TYPE_CHECKING:
    from app.callback import BackendCallbackClient
    from app.generator import ImageGenerator
    from app.storage import ImageStorage

logger = logging.getLogger(__name__)


class MessageHandler:
    def __init__(
        self,
        generator: ImageGenerator,
        storage: ImageStorage,
        callback: BackendCallbackClient,
    ) -> None:
        self._generator = generator
        self._storage = storage
        self._callback = callback
        self._perfect_pixel = PerfectPixelProcessor()

    def handle(self, raw_body: bytes) -> None:
        started = time.monotonic()
        task_id = ""

        try:
            message = GenerateMessage.model_validate_json(raw_body)
        except (ValidationError, json.JSONDecodeError) as exc:
            logger.error("消息 JSON 解析失败: %s body=%s", exc, raw_body[:500])
            return

        task_id = message.taskId.strip()
        if not task_id:
            logger.error("消息缺少 taskId body=%s", raw_body[:500])
            return

        model_key = (message.modelKey or "").strip() or "default"
        logger.info(
            "开始处理 taskId=%s modelKey=%s style=%s createdAt=%s",
            task_id,
            model_key,
            message.style,
            message.createdAt,
        )

        try:
            if not message.imageUrl.strip():
                raise NonRetryableError("imageUrl 为空")

            self._safe_processing_callback(task_id)

            image_bytes = self._generator.generate(message)
            raw_url = self._storage.upload_png(task_id, image_bytes, variant="raw")

            detected_w: int | None = None
            detected_h: int | None = None
            perfect_pixel_status = "SUCCESS"
            perfect_pixel_error: str | None = None
            result_url = raw_url

            try:
                refined = self._perfect_pixel.refine(image_bytes)
                detected_w = refined.width
                detected_h = refined.height
                result_url = self._storage.upload_png(task_id, refined.png_bytes, variant="refined")
            except Exception as exc:
                perfect_pixel_status = "FAILED"
                perfect_pixel_error = str(exc)[:1000]
                logger.warning("Perfect Pixel 澶辫触 taskId=%s error=%s", task_id, exc)

            final_grid = choose_final_grid_size(message, detected_w, detected_h)
            grid_min, grid_max = resolve_grid_range(message)
            self._callback.success(
                task_id,
                result_url,
                raw_image_url=raw_url,
                size_mode=message.sizeMode,
                grid_min=grid_min,
                grid_max=grid_max,
                detected_grid_width=detected_w,
                detected_grid_height=detected_h,
                final_grid_width=final_grid,
                final_grid_height=final_grid,
                perfect_pixel_status=perfect_pixel_status,
                perfect_pixel_error=perfect_pixel_error,
            )

            elapsed = time.monotonic() - started
            logger.info(
                "处理成功 taskId=%s modelKey=%s elapsed=%.2fs url=%s",
                task_id,
                model_key,
                elapsed,
                result_url,
            )
        except NonRetryableError as exc:
            elapsed = time.monotonic() - started
            logger.warning("处理失败 taskId=%s elapsed=%.2fs error=%s", task_id, elapsed, exc)
            self._safe_failed_callback(task_id, str(exc))
        except Exception as exc:
            elapsed = time.monotonic() - started
            logger.exception("处理异常 taskId=%s elapsed=%.2fs", task_id, elapsed)
            self._safe_failed_callback(task_id, str(exc))

    def _safe_processing_callback(self, task_id: str) -> None:
        try:
            self._callback.processing(task_id)
        except Exception as exc:
            logger.error("PROCESSING 回调失败 taskId=%s error=%s", task_id, exc)

    def _safe_failed_callback(self, task_id: str, error_message: str) -> None:
        try:
            self._callback.failed(task_id, error_message)
        except Exception as exc:
            logger.critical("FAILED 回调最终失败 taskId=%s error=%s callback_error=%s", task_id, error_message, exc)
