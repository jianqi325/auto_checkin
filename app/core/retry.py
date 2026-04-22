from __future__ import annotations

import time
from typing import Callable, TypeVar

T = TypeVar("T")


def run_with_retry(
    fn: Callable[[], T],
    attempts: int,
    backoff_seconds: int,
    should_retry: Callable[[Exception], bool],
) -> T:
    attempts = max(1, attempts)
    last_exc: Exception | None = None
    for idx in range(1, attempts + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if idx >= attempts or not should_retry(exc):
                raise
            time.sleep(max(0, backoff_seconds))
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("run_with_retry reached impossible path")
