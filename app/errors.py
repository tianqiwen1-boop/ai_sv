class AiServiceError(Exception):
    """业务异常基类。"""


class NonRetryableError(AiServiceError):
    """不可恢复错误，应回调 FAILED 并 ack。"""


class ConfigError(AiServiceError):
    """配置错误。"""
