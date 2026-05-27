from __future__ import annotations

import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

from app.config import ConfigError, load_config

# 启动时加载项目根目录 .env（PowerShell 不会自动读取 .env 文件）
_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(_ENV_FILE)
from app.consumer import RabbitMQConsumer
from app.logging_config import setup_logging

logger = logging.getLogger(__name__)


def main() -> None:
    try:
        config = load_config()
    except ConfigError as exc:
        print(f"配置错误: {exc}", file=sys.stderr)
        sys.exit(1)

    setup_logging(config.service.log_level)
    logger.info("启动 %s default_model=%s", config.service.name, config.service.default_model)

    consumer = RabbitMQConsumer(config)
    consumer.start()


if __name__ == "__main__":
    main()
