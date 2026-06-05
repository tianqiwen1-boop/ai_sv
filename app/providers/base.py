from __future__ import annotations

from abc import ABC, abstractmethod

from app.config import DownloadConfig, ModelConfig, ProviderConfig
from app.models import GenerateMessage


class ImageProvider(ABC):
    """图生图 provider 统一接口。"""

    def __init__(self, download_config: DownloadConfig) -> None:
        self._download_config = download_config

    @abstractmethod
    def generate(
        self,
        message: GenerateMessage,
        model: ModelConfig,
        provider: ProviderConfig,
    ) -> bytes:
        ...
