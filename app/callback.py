from __future__ import annotations

import logging

import requests

from app.config import ServiceConfig
from app.models import CallbackPayload
from app.retry import retry_call

logger = logging.getLogger(__name__)


class BackendCallbackClient:
    def __init__(self, config: ServiceConfig) -> None:
        self._config = config
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Content-Type": "application/json",
                "X-AI-Service-Token": config.callback_token,
            }
        )

    def processing(self, task_id: str) -> None:
        self._send(
            CallbackPayload(
                taskId=task_id,
                status="PROCESSING",
                aiImageUrl=None,
                errorMessage=None,
            )
        )

    def success(self, task_id: str, image_url: str) -> None:
        self._send(
            CallbackPayload(
                taskId=task_id,
                status="SUCCESS",
                aiImageUrl=image_url,
                errorMessage=None,
            )
        )

    def failed(self, task_id: str, error_message: str) -> None:
        self._send(
            CallbackPayload(
                taskId=task_id,
                status="FAILED",
                aiImageUrl=None,
                errorMessage=error_message[:2000],
            )
        )

    def _send(self, payload: CallbackPayload) -> None:
        body = payload.model_dump(mode="json")

        def _post() -> None:
            resp = self._session.post(
                self._config.callback_url,
                json=body,
                timeout=self._config.callback_timeout_seconds,
            )
            if not (200 <= resp.status_code < 300):
                raise RuntimeError(f"回调 HTTP 状态异常: {resp.status_code}, body={resp.text[:500]}")

            try:
                data = resp.json()
            except ValueError as exc:
                raise RuntimeError(f"回调响应不是 JSON: {resp.text[:500]}") from exc

            code = data.get("code")
            if code != 0:
                raise RuntimeError(f"回调业务失败: code={code}, body={data}")

        try:
            retry_call(
                _post,
                max_attempts=self._config.callback_max_retries,
                interval_seconds=self._config.callback_retry_interval_seconds,
            )
            logger.info("回调成功 taskId=%s status=%s", payload.taskId, payload.status)
        except Exception as exc:
            logger.error(
                "回调最终失败 taskId=%s status=%s error=%s",
                payload.taskId,
                payload.status,
                exc,
            )
            raise
