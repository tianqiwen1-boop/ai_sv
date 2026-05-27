from __future__ import annotations

import io
import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


def retry_call(
    func: Callable[[], T],
    *,
    max_attempts: int,
    interval_seconds: float,
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
) -> T:
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return func()
        except retryable_exceptions as exc:
            last_error = exc
            if attempt >= max_attempts:
                break
            time.sleep(interval_seconds)
    assert last_error is not None
    raise last_error
