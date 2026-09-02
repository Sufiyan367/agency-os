import asyncio
import functools
import random
from typing import Callable, Any, Tuple, Type
from app.core.logging import logger

def async_retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 10.0,
    factor: float = 2.0,
    jitter: bool = True,
    exceptions: Tuple[Type[Exception], ...] = (Exception,)
) -> Callable:
    """
    Decorator for retrying async operations with exponential backoff and jitter.
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            delay = base_delay
            last_err = None
            for attempt in range(1, max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_err = e
                    if attempt == max_retries:
                        logger.error(f"[{func.__name__}] Failed after {max_retries} attempts: {e}")
                        raise
                    actual_delay = min(delay, max_delay)
                    if jitter:
                        actual_delay *= (0.75 + random.random() * 0.5)
                    logger.warning(
                        f"[{func.__name__}] Attempt {attempt}/{max_retries} failed ({e}). Retrying in {actual_delay:.2f}s..."
                    )
                    await asyncio.sleep(actual_delay)
                    delay *= factor
            raise last_err
        return wrapper
    return decorator
