from __future__ import annotations

import logging
import signal
import threading
import time

import pika
from pika.adapters.blocking_connection import BlockingChannel
from pika.spec import Basic, BasicProperties

from app.callback import BackendCallbackClient
from app.config import AppConfig
from app.generator import ImageGenerator
from app.handler import MessageHandler
from app.storage import ImageStorage

logger = logging.getLogger(__name__)


class RabbitMQConsumer:
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._stop_event = threading.Event()
        self._connection: pika.BlockingConnection | None = None
        self._channel: BlockingChannel | None = None

        generator = ImageGenerator(config)
        storage = ImageStorage(config.storage)
        callback = BackendCallbackClient(config.service)
        self._handler = MessageHandler(generator, storage, callback)

    def start(self) -> None:
        signal.signal(signal.SIGINT, self._handle_stop_signal)
        signal.signal(signal.SIGTERM, self._handle_stop_signal)

        reconnect_interval = self._config.rabbitmq.reconnect_interval_seconds
        while not self._stop_event.is_set():
            try:
                self._connect_and_consume()
            except KeyboardInterrupt:
                logger.info("收到中断信号，准备退出")
                self._stop_event.set()
            except Exception as exc:
                if self._stop_event.is_set():
                    break
                logger.error("RabbitMQ 消费异常，%ds 后重连: %s", reconnect_interval, exc)
                time.sleep(reconnect_interval)
            finally:
                self._close()

        logger.info("ai-service 已停止")

    def _connect_and_consume(self) -> None:
        mq = self._config.rabbitmq
        credentials = pika.PlainCredentials(mq.username, mq.password)
        params = pika.ConnectionParameters(
            host=mq.host,
            port=mq.port,
            credentials=credentials,
            heartbeat=600,
            blocked_connection_timeout=300,
        )
        self._connection = pika.BlockingConnection(params)
        self._channel = self._connection.channel()
        self._channel.basic_qos(prefetch_count=mq.prefetch_count)

        # 队列由 Java 侧声明；不存在则 fail-fast
        self._channel.queue_declare(queue=mq.queue_name, passive=True)
        logger.info("RabbitMQ 已连接 queue=%s prefetch=%d", mq.queue_name, mq.prefetch_count)

        self._channel.basic_consume(
            queue=mq.queue_name,
            on_message_callback=self._on_message,
            auto_ack=False,
        )
        self._channel.start_consuming()

    def _on_message(
        self,
        channel: BlockingChannel,
        method: Basic.Deliver,
        _properties: BasicProperties,
        body: bytes,
    ) -> None:
        delivery_tag = method.delivery_tag
        try:
            self._handler.handle(body)
        except Exception:
            logger.exception("消息处理未捕获异常 delivery_tag=%s", delivery_tag)
            # 意外异常（非 handler 内已处理的业务错误），nack 不重入队，
            # 避免重复提交即梦任务。消息丢弃或进入 DLX，由超时扫描兜底。
            channel.basic_nack(delivery_tag=delivery_tag, requeue=False)
        else:
            channel.basic_ack(delivery_tag=delivery_tag)

    def _handle_stop_signal(self, signum: int, _frame: object) -> None:
        logger.info("收到停止信号 signum=%s", signum)
        self._stop_event.set()
        if self._channel and self._channel.is_open:
            self._channel.stop_consuming()

    def _close(self) -> None:
        if self._channel and self._channel.is_open:
            self._channel.close()
        if self._connection and self._connection.is_open:
            self._connection.close()
        self._channel = None
        self._connection = None
