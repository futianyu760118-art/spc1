"""retry 装饰器单元测试"""

import asyncio
import pytest

from app.services.assistant.retry import (
    RetryConfig,
    RetryExhaustedError,
    async_retry,
)


@pytest.mark.asyncio
async def test_async_retry_success_first_try():
    calls = {"n": 0}

    @async_retry(RetryConfig(max_retries=3, initial_delay=0.01))
    async def f():
        calls["n"] += 1
        return "ok"

    result = await f()
    assert result == "ok"
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_async_retry_eventually_succeeds():
    calls = {"n": 0}

    @async_retry(RetryConfig(
        max_retries=3,
        initial_delay=0.01,
        exponential_base=2.0,
        max_delay=0.1,
        retryable_exceptions=(ValueError,),
    ))
    async def f():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ValueError("transient")
        return "ok"

    result = await f()
    assert result == "ok"
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_async_retry_exhausted():
    @async_retry(RetryConfig(
        max_retries=2,
        initial_delay=0.01,
        retryable_exceptions=(ValueError,),
    ))
    async def f():
        raise ValueError("always")

    with pytest.raises(RetryExhaustedError) as exc_info:
        await f()
    assert exc_info.value.attempts == 3
    assert isinstance(exc_info.value.last_exception, ValueError)


@pytest.mark.asyncio
async def test_async_retry_non_retryable_exception_reraises():
    calls = {"n": 0}

    @async_retry(RetryConfig(
        max_retries=3,
        initial_delay=0.01,
        retryable_exceptions=(ValueError,),
    ))
    async def f():
        calls["n"] += 1
        raise TypeError("do not retry")

    with pytest.raises(TypeError):
        await f()
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_async_retry_disabled():
    calls = {"n": 0}

    @async_retry(RetryConfig(enabled=False, max_retries=3))
    async def f():
        calls["n"] += 1
        raise ValueError("no retry")

    with pytest.raises(ValueError):
        await f()
    assert calls["n"] == 1


def test_retry_config_calculate_delay_caps_at_max():
    config = RetryConfig(
        initial_delay=1.0,
        exponential_base=2.0,
        max_delay=5.0,
    )
    assert config.calculate_delay(0) == 1.0
    assert config.calculate_delay(1) == 2.0
    assert config.calculate_delay(2) == 4.0
    assert config.calculate_delay(3) == 5.0
    assert config.calculate_delay(10) == 5.0
