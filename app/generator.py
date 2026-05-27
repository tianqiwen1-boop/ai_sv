from __future__ import annotations

import logging

from app.config import AppConfig
from app.errors import NonRetryableError
from app.models import GenerateMessage
from app.providers.jimeng import JimengProvider

logger = logging.getLogger(__name__)


class ImageGenerator:
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._jimeng = JimengProvider(config)

    def generate(self, message: GenerateMessage) -> bytes:
        model = self._config.get_model(message.modelKey)
        provider = model.provider.strip().lower()

        if provider == "jimeng":
            return self._jimeng.generate_png(message, model)

        raise NonRetryableError(f"不支持的 provider: {provider}")
