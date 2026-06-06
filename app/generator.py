from __future__ import annotations

import importlib
import logging

from app.config import AppConfig
from app.errors import NonRetryableError
from app.models import GenerateMessage
from app.providers.base import ImageProvider

logger = logging.getLogger(__name__)

_PROVIDER_IMPORTS: dict[str, tuple[str, str]] = {
    "jimeng": ("app.providers.jimeng", "JimengProvider"),
    "seedream": ("app.providers.seedream", "SeedreamProvider"),
}


class ImageGenerator:
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._instances: dict[str, ImageProvider] = {}

    def _get_provider_instance(self, provider_type: str) -> ImageProvider:
        if provider_type not in self._instances:
            target = _PROVIDER_IMPORTS.get(provider_type)
            if target is None:
                raise NonRetryableError(f"unsupported provider type: {provider_type}")

            module_name, class_name = target
            try:
                module = importlib.import_module(module_name)
                provider_cls = getattr(module, class_name)
            except Exception as exc:
                raise NonRetryableError(f"failed to load provider {provider_type}: {exc}") from exc

            self._instances[provider_type] = provider_cls(self._config.download)
        return self._instances[provider_type]

    def generate(self, message: GenerateMessage) -> bytes:
        model, provider_cfg = self._config.get_model_with_provider(message.modelKey)
        instance = self._get_provider_instance(provider_cfg.type)
        return instance.generate(message, model, provider_cfg)
