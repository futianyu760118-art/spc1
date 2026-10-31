"""异步重试装饰器 — 指数退避策略"""

import asyncio
import functools
import logging
from typing import Any, Callable, Optional, Tuple, Type, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class RetryConfig:
    def __init__(
        self,
        enabled: bool = True,
        max_retries: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 30.0,
        exponential_base: float = 2.0,
        retryable_exceptions: Tuple[Type[Exception], ...] = (Exception,),
    ):
        self.enabled = enabled
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.retryable_exceptions = retryable_exceptions

    def calculate_delay(self, attempt: int) -> float:
        delay = self.initial_delay * (self.exponential_base ** attempt)
        return min(delay, self.max_delay)


class RetryExhaustedError(Exception):
    def __init__(self, last_exception: Exception, attempts: int):
        self.last_exception = last_exception
        self.attempts = attempts
        super().__init__(f"重试 {attempts} 次后仍失败，最后错误: {str(last_exception)}")


def async_retry(
    config: Optional[RetryConfig] = None,
    on_retry: Optional[Callable[[Exception, int], None]] = None,
) -> Callable:
    if config is None:
        config = RetryConfig()

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            if not config.enabled:
                return await func(*args, **kwargs)

            last_exception: Optional[Exception] = None
            for attempt in range(config.max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except config.retryable_exceptions as e:
                    last_exception = e
                    if attempt >= config.max_retries:
                        logger.error(
                            f"函数 {func.__name__} 重试 {config.max_retries} 次后仍失败: {e}"
                        )
                        raise RetryExhaustedError(e, attempt + 1)

                    delay = config.calculate_delay(attempt)
                    logger.warning(
                        f"函数 {func.__name__} 第 {attempt + 1} 次调用失败: {e}, "
                        f"将于 {delay:.2f}s 后重试 (第 {attempt + 2} 次)"
                    )
                    if on_retry:
                        try:
                            on_retry(e, attempt + 1)
                        except Exception:
                            pass
                    await asyncio.sleep(delay)

            if last_exception:
                raise last_exception
            raise RuntimeError("async_retry: 未知错误")

        return wrapper

    return decorator
