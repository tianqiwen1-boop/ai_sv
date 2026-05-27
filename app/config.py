from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from app.errors import ConfigError, NonRetryableError

_ENV_PATTERN = re.compile(r"\$\{([^}:]+)(?::([^}]*))?\}")


@dataclass
class ServiceConfig:
    name: str
    log_level: str
    callback_url: str
    callback_token: str
    callback_timeout_seconds: int
    callback_max_retries: int
    callback_retry_interval_seconds: int
    default_model: str


@dataclass
class RabbitMQConfig:
    host: str
    port: int
    username: str
    password: str
    queue_name: str
    prefetch_count: int
    reconnect_interval_seconds: int


@dataclass
class StorageConfig:
    endpoint: str
    access_key: str
    secret_key: str
    bucket: str
    region: str
    public_base_url: str
    key_prefix: str
    path_style_access: bool
    url_include_bucket: bool
    upload_max_retries: int
    upload_retry_interval_seconds: int


@dataclass
class DownloadConfig:
    max_retries: int
    retry_interval_seconds: int
    timeout_seconds: int


@dataclass
class ModelConfig:
    key: str
    provider: str
    enabled: bool
    req_key: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class AppConfig:
    service: ServiceConfig
    rabbitmq: RabbitMQConfig
    storage: StorageConfig
    download: DownloadConfig
    models: dict[str, ModelConfig]

    def get_model(self, model_key: str | None) -> ModelConfig:
        key = (model_key or "").strip() or self.service.default_model
        model = self.models.get(key)
        if model is None:
            raise NonRetryableError(f"modelKey 不存在: {key}")
        if not model.enabled:
            raise NonRetryableError(f"modelKey 已禁用: {key}")
        return model


def _substitute_env(value: str) -> str:
    def replacer(match: re.Match[str]) -> str:
        var_name = match.group(1)
        default = match.group(2)
        env_val = os.environ.get(var_name)
        if env_val is not None and env_val != "":
            return env_val
        if default is not None:
            return default
        raise ConfigError(f"缺少环境变量: {var_name}")

    if not isinstance(value, str):
        return value
    return _ENV_PATTERN.sub(replacer, value)


def _resolve_values(data: Any) -> Any:
    if isinstance(data, dict):
        return {k: _resolve_values(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_resolve_values(item) for item in data]
    if isinstance(data, str):
        return _substitute_env(data)
    return data


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def load_config(config_path: str | None = None) -> AppConfig:
    path = Path(config_path or os.environ.get("AI_SERVICE_CONFIG", "config/config.yaml"))
    if not path.is_file():
        raise ConfigError(f"配置文件不存在: {path}")

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    data = _resolve_values(raw)

    service_raw = data.get("service") or {}
    rabbit_raw = data.get("rabbitmq") or {}
    storage_raw = data.get("storage") or {}
    download_raw = data.get("download") or {}
    models_raw = data.get("models") or {}

    service = ServiceConfig(
        name=str(service_raw.get("name", "ai-service")),
        log_level=str(service_raw.get("log_level", "INFO")),
        callback_url=str(service_raw.get("callback_url", "")).strip(),
        callback_token=str(service_raw.get("callback_token", "")).strip(),
        callback_timeout_seconds=int(service_raw.get("callback_timeout_seconds", 15)),
        callback_max_retries=int(service_raw.get("callback_max_retries", 3)),
        callback_retry_interval_seconds=int(service_raw.get("callback_retry_interval_seconds", 3)),
        default_model=str(service_raw.get("default_model", "jimeng-t2i-v40")),
    )
    rabbitmq = RabbitMQConfig(
        host=str(rabbit_raw.get("host", "localhost")),
        port=int(rabbit_raw.get("port", 5672)),
        username=str(rabbit_raw.get("username", "guest")),
        password=str(rabbit_raw.get("password", "guest")),
        queue_name=str(rabbit_raw.get("queue_name", "ai.generate.request")),
        prefetch_count=int(rabbit_raw.get("prefetch_count", 1)),
        reconnect_interval_seconds=int(rabbit_raw.get("reconnect_interval_seconds", 5)),
    )
    storage = StorageConfig(
        endpoint=str(storage_raw.get("endpoint", "")).strip(),
        access_key=str(storage_raw.get("access_key", "")).strip(),
        secret_key=str(storage_raw.get("secret_key", "")).strip(),
        bucket=str(storage_raw.get("bucket", "")).strip(),
        region=str(storage_raw.get("region", "ap-guangzhou")),
        public_base_url=str(storage_raw.get("public_base_url", "")).rstrip("/"),
        key_prefix=str(storage_raw.get("key_prefix", "ai-results/")).strip() or "ai-results/",
        path_style_access=_as_bool(storage_raw.get("path_style_access"), False),
        url_include_bucket=_as_bool(storage_raw.get("url_include_bucket"), False),
        upload_max_retries=int(storage_raw.get("upload_max_retries", 3)),
        upload_retry_interval_seconds=int(storage_raw.get("upload_retry_interval_seconds", 2)),
    )
    download = DownloadConfig(
        max_retries=int(download_raw.get("max_retries", 3)),
        retry_interval_seconds=int(download_raw.get("retry_interval_seconds", 2)),
        timeout_seconds=int(download_raw.get("timeout_seconds", 60)),
    )

    models: dict[str, ModelConfig] = {}
    for key, model_raw in models_raw.items():
        if not isinstance(model_raw, dict):
            continue
        models[key] = ModelConfig(
            key=key,
            provider=str(model_raw.get("provider", "")),
            enabled=_as_bool(model_raw.get("enabled"), True),
            req_key=str(model_raw.get("req_key", "")),
            extra=dict(model_raw.get("extra") or {}),
        )

    config = AppConfig(
        service=service,
        rabbitmq=rabbitmq,
        storage=storage,
        download=download,
        models=models,
    )
    validate_config(config)
    return config


def validate_config(config: AppConfig) -> None:
    missing: list[str] = []
    if not config.service.callback_url:
        missing.append("service.callback_url / CALLBACK_URL")
    if not config.service.callback_token:
        missing.append("service.callback_token / AI_CALLBACK_TOKEN")
    if not config.storage.access_key:
        missing.append("storage.access_key / S3_ACCESS_KEY")
    if not config.storage.secret_key:
        missing.append("storage.secret_key / S3_SECRET_KEY")
    if not config.storage.bucket:
        missing.append("storage.bucket / S3_BUCKET")
    if not config.storage.public_base_url:
        missing.append("storage.public_base_url / S3_PUBLIC_BASE_URL")
    if not config.models:
        missing.append("models（至少配置一个模型）")
    if config.service.default_model not in config.models:
        missing.append(f"default_model 未配置: {config.service.default_model}")

    if missing:
        raise ConfigError("配置校验失败: " + ", ".join(missing))

    logging.getLogger(__name__).debug("配置校验通过，已加载 %d 个模型", len(config.models))
