from __future__ import annotations

import logging

from app.config import AppConfig
from app.errors import NonRetryableError
from app.models import GenerateMessage
from app.providers.base import ImageProvider
from app.providers.jimeng import JimengProvider

logger = logging.getLogger(__name__)

_PROVIDER_CLASSES: dict[str, type[ImageProvider]] = {
    "jimeng": JimengProvider,
}


class ImageGenerator:
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._instances: dict[str, ImageProvider] = {}

    def _get_provider_instance(self, provider_type: str) -> ImageProvider:
        if provider_type not in self._instances:
            cls = _PROVIDER_CLASSES.get(provider_type)
            if cls is None:
                raise NonRetryableError(f"不支持的 provider 类型: {provider_type}")
            self._instances[provider_type] = cls(self._config.download)
        return self._instances[provider_type]

    def generate(self, message: GenerateMessage) -> bytes:
        model, provider_cfg = self._config.get_model_with_provider(message.modelKey)
        instance = self._get_provider_instance(provider_cfg.type)
        return instance.generate(message, model, provider_cfg)
