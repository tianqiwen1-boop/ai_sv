from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta

import boto3
from botocore.config import Config as BotoConfig

from app.config import StorageConfig
from app.errors import NonRetryableError
from app.retry import retry_call

logger = logging.getLogger(__name__)
SHANGHAI_TZ = timezone(timedelta(hours=8))


@dataclass(frozen=True)
class StoredImage:
    url: str
    key: str


class ImageStorage:
    def __init__(self, config: StorageConfig) -> None:
        self._config = config
        self._client = boto3.client(
            "s3",
            endpoint_url=config.endpoint or None,
            aws_access_key_id=config.access_key,
            aws_secret_access_key=config.secret_key,
            region_name=config.region,
            config=BotoConfig(s3={"addressing_style": "path" if config.path_style_access else "virtual"}),
        )

    def upload_png(self, task_id: str, image_bytes: bytes, variant: str | None = None) -> StoredImage:
        key = self._build_object_key(task_id, variant)

        def _upload() -> None:
            self._client.put_object(
                Bucket=self._config.bucket,
                Key=key,
                Body=image_bytes,
                ContentType="image/png",
                ACL="public-read",
            )

        try:
            retry_call(
                _upload,
                max_attempts=self._config.upload_max_retries,
                interval_seconds=self._config.upload_retry_interval_seconds,
            )
        except Exception as exc:
            raise NonRetryableError(f"上传 COS 失败: {exc}") from exc

        url = self._build_public_url(key)
        logger.info("上传成功 taskId=%s key=%s url=%s", task_id, key, url)
        return StoredImage(url=url, key=key)

    def _build_object_key(self, task_id: str, variant: str | None = None) -> str:
        now = datetime.now(SHANGHAI_TZ)
        prefix = self._config.key_prefix.strip("/")
        if prefix:
            prefix = f"{prefix}/"
        suffix = f"_{variant}" if variant else ""
        return f"{prefix}{now:%Y/%m/%d}/{task_id}{suffix}.png"

    def _build_public_url(self, key: str) -> str:
        base = self._config.public_base_url.rstrip("/")
        if self._config.url_include_bucket:
            return f"{base}/{self._config.bucket}/{key}"
        return f"{base}/{key}"
