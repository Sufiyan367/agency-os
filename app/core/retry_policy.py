"""
Retry and Transient Error Handling Policy.
Distinguishes between retryable transient network/server failures (HTTP 429, 502, 503, timeouts)
and permanent deterministic business/syntax errors (HTTP 400, 401, 404, invalid format, hard bounce).
"""
import asyncio
import logging
from typing import Callable, Any, TypeVar, Coroutine, Dict, Tuple
import httpx

logger = logging.getLogger(__name__)

T = TypeVar("T")

TRANSIENT_STATUS_CODES = {408, 429, 500, 502, 503, 504}
PERMANENT_STATUS_CODES = {400, 401, 403, 404, 405, 422}


def is_transient_error(exc: Exception) -> bool:
    """Returns True if the exception represents a transient failure eligible for retry."""
    if isinstance(exc, (httpx.TimeoutException, httpx.NetworkError, ConnectionResetError, TimeoutError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in TRANSIENT_STATUS_CODES
    err_msg = str(exc).lower()
    return any(marker in err_msg for marker in ["rate limit", "timeout", "temporarily unavailable", "connection reset"])


def is_permanent_error(exc: Exception) -> bool:
    """Returns True if the exception represents a permanent failure that should not be retried."""
    if isinstance(exc, (ValueError, TypeError, KeyError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in PERMANENT_STATUS_CODES
    return False


async def execute_with_retry(
    coro_func: Callable[[], Coroutine[Any, Any, T]],
    max_retries: int = 3,
    initial_delay: float = 0.5,
    backoff_factor: float = 2.0,
    operation_name: str = "Outbound Operation"
) -> Tuple[bool, Any, int]:
    """
    Executes an asynchronous operation with exponential backoff for transient errors.
    Returns (success: bool, result_or_error: Any, attempts_made: int).
    """
    delay = initial_delay
    attempts = 0

    while attempts < max_retries:
        attempts += 1
        try:
            res = await coro_func()
            return True, res, attempts
        except Exception as e:
            if is_permanent_error(e) or attempts >= max_retries:
                logger.error(f"[{operation_name}] Permanent failure on attempt {attempts}: {e}")
                return False, str(e), attempts

            if is_transient_error(e):
                logger.warning(
                    f"[{operation_name}] Transient error on attempt {attempts}/{max_retries} ({e}). "
                    f"Retrying in {delay:.2f}s..."
                )
                await asyncio.sleep(delay)
                delay *= backoff_factor
            else:
                # Unknown error type: treat as non-retryable to prevent cascading failures
                logger.error(f"[{operation_name}] Non-retryable error on attempt {attempts}: {e}")
                return False, str(e), attempts

    return False, "Max retries exceeded.", attempts
