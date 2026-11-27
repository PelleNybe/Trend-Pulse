"""
Attribution: The `with_graceful_retry` logic is inspired by common exponential backoff retry patterns found in robust open-source Python network clients, utilizing the standard `functools.wraps` decorator approach.
"""
"""
Retry mechanism tool module
Provides a general network request retry function，Enhance system robustness
"""


import asyncio
import threading
import inspect
from functools import wraps
from typing import Callable, Any
from dataclasses import dataclass
import requests
from loguru import logger


@dataclass
class RetryConfig:
    """Retry configuration class"""
    max_retries: int = 3
    initial_delay: float = 1.0
    backoff_factor: float = 2.0
    max_delay: float = 60.0
    retry_on_exceptions: tuple = None

    def __post_init__(self):
        if self.retry_on_exceptions is None:
            self.retry_on_exceptions = (
                requests.exceptions.RequestException,
                requests.exceptions.ConnectionError,
                requests.exceptions.HTTPError,
                requests.exceptions.Timeout,
                requests.exceptions.TooManyRedirects,
                ConnectionError,
                TimeoutError,
                Exception
            )


DEFAULT_RETRY_CONFIG = RetryConfig()


def with_retry(config: RetryConfig = None):
    """
    Retry decorator
    
    Args:
        config: retry configuration，If not provided, the default configuration is used
    
    Returns:
        Decorator function
    """
    if config is None:
        config = DEFAULT_RETRY_CONFIG
    
    def decorator(func: Callable) -> Callable:
        if inspect.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(*args, **kwargs) -> Any:
                last_exception = None

                for attempt in range(config.max_retries + 1):
                    try:
                        result = await func(*args, **kwargs)
                        if attempt > 0:
                            logger.info(f"function {func.__name__} In the first {attempt + 1} Successful after attempts")
                        return result

                    except config.retry_on_exceptions as e:
                        last_exception = e

                        if attempt == config.max_retries:
                            logger.error(f"function {func.__name__} exist {config.max_retries + 1} Still failed after attempts")
                            logger.error(f"final error: {str(e)}")
                            raise e

                        delay = min(
                            config.initial_delay * (config.backoff_factor ** attempt),
                            config.max_delay
                        )

                        logger.warning(f"function {func.__name__} No. {attempt + 1} failed attempts: {str(e)}")
                        logger.info(f"will be in {delay:.1f} Seconds later {attempt + 2} attempts...")

                        await asyncio.sleep(delay)
                    
                    except Exception as e:
                        logger.error(f"function {func.__name__} A non-retryable exception was encountered: {str(e)}")
                        raise e

                if last_exception:
                    raise last_exception
            return async_wrapper
        else:
            @wraps(func)
            def sync_wrapper(*args, **kwargs) -> Any:
                last_exception = None

                for attempt in range(config.max_retries + 1):
                    try:
                        result = func(*args, **kwargs)
                        if attempt > 0:
                            logger.info(f"function {func.__name__} In the first {attempt + 1} Successful after attempts")
                        return result

                    except config.retry_on_exceptions as e:
                        last_exception = e

                        if attempt == config.max_retries:
                            logger.error(f"function {func.__name__} exist {config.max_retries + 1} Still failed after attempts")
                            logger.error(f"final error: {str(e)}")
                            raise e

                        delay = min(
                            config.initial_delay * (config.backoff_factor ** attempt),
                            config.max_delay
                        )

                        logger.warning(f"function {func.__name__} No. {attempt + 1} failed attempts: {str(e)}")
                        logger.info(f"will be in {delay:.1f} Seconds later {attempt + 2} attempts...")

                        threading.Event().wait(delay)
                    
                    except Exception as e:
                        logger.error(f"function {func.__name__} A non-retryable exception was encountered: {str(e)}")
                        raise e
                
                if last_exception:
                    raise last_exception
            return sync_wrapper
    return decorator

def retry_on_network_error(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0
):
    """
    A dedicated retry decorator for network errors（Simplified version）
    
    Args:
        max_retries: Maximum number of retries
        initial_delay: initial delay in seconds
        backoff_factor: backoff factor
    
    Returns:
        Decorator function
    """
    config = RetryConfig(
        max_retries=max_retries,
        initial_delay=initial_delay,
        backoff_factor=backoff_factor
    )
    return with_retry(config)

class RetryableError(Exception):
    """Custom retryable exceptions"""
    pass


def with_graceful_retry(config: RetryConfig = None, default_return=None):
    """
    Graceful retry decorator - for non-critical API calls
    No exception will be thrown on failure，Instead, return the default value，Ensure the system continues to operate
    
    Args:
        config: retry configuration，If not provided, the default configuration is used
        default_return: The default value returned after all failed retries
    
    Returns:
        Decorator function
    """
    if config is None:
        config = SEARCH_API_RETRY_CONFIG
    
    def decorator(func: Callable) -> Callable:
        if inspect.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(*args, **kwargs) -> Any:
                last_exception = None

                for attempt in range(config.max_retries + 1):
                    try:
                        result = await func(*args, **kwargs)
                        if attempt > 0:
                            logger.info(f"non-criticalAPI {func.__name__} In the first {attempt + 1} Successful after attempts")
                        return result

                    except config.retry_on_exceptions as e:
                        last_exception = e

                        if attempt == config.max_retries:
                            logger.warning(f"non-criticalAPI {func.__name__} exist {config.max_retries + 1} Still failed after attempts")
                            logger.warning(f"final error: {str(e)}")
                            logger.info(f"Return to default values ​​to ensure the system continues to operate: {default_return}")
                            return default_return

                        delay = min(
                            config.initial_delay * (config.backoff_factor ** attempt),
                            config.max_delay
                        )

                        logger.warning(f"non-criticalAPI {func.__name__} No. {attempt + 1} failed attempts: {str(e)}")
                        logger.info(f"will be in {delay:.1f} Seconds later {attempt + 2} attempts...")

                        await asyncio.sleep(delay)
                    
                    except Exception as e:
                        logger.warning(f"non-criticalAPI {func.__name__} A non-retryable exception was encountered: {str(e)}")
                        logger.info(f"Return to default values ​​to ensure the system continues to operate: {default_return}")
                        return default_return

                return default_return
            return async_wrapper
        else:
            @wraps(func)
            def sync_wrapper(*args, **kwargs) -> Any:
                last_exception = None

                for attempt in range(config.max_retries + 1):
                    try:
                        result = func(*args, **kwargs)
                        if attempt > 0:
                            logger.info(f"non-criticalAPI {func.__name__} In the first {attempt + 1} Successful after attempts")
                        return result

                    except config.retry_on_exceptions as e:
                        last_exception = e

                        if attempt == config.max_retries:
                            logger.warning(f"non-criticalAPI {func.__name__} exist {config.max_retries + 1} Still failed after attempts")
                            logger.warning(f"final error: {str(e)}")
                            logger.info(f"Return to default values ​​to ensure the system continues to operate: {default_return}")
                            return default_return

                        delay = min(
                            config.initial_delay * (config.backoff_factor ** attempt),
                            config.max_delay
                        )

                        logger.warning(f"non-criticalAPI {func.__name__} No. {attempt + 1} failed attempts: {str(e)}")
                        logger.info(f"will be in {delay:.1f} Seconds later {attempt + 2} attempts...")

                        threading.Event().wait(delay)
                    
                    except Exception as e:
                        logger.warning(f"non-criticalAPI {func.__name__} A non-retryable exception was encountered: {str(e)}")
                        logger.info(f"Return to default values ​​to ensure the system continues to operate: {default_return}")
                        return default_return
                
                return default_return
            return sync_wrapper
    return decorator

def make_retryable_request(
    request_func: Callable,
    *args,
    max_retries: int = 5,
    **kwargs
) -> Any:
    """
    Directly execute retryable requests（Don't use decorators）
    
    Args:
        request_func: request function to execute
        *args: Positional parameters passed to the request function
        max_retries: Maximum number of retries
        **kwargs: Keyword arguments passed to the request function
    
    Returns:
        The return value of the request function
    """
    config = RetryConfig(max_retries=max_retries)
    
    @with_retry(config)
    def _execute():
        return request_func(*args, **kwargs)
    
    return _execute()


LLM_RETRY_CONFIG = RetryConfig(
    max_retries=6,
    initial_delay=60.0,
    backoff_factor=2.0,
    max_delay=600.0
)

SEARCH_API_RETRY_CONFIG = RetryConfig(
    max_retries=5,
    initial_delay=2.0,
    backoff_factor=1.6,
    max_delay=25.0
)

DB_RETRY_CONFIG = RetryConfig(
    max_retries=5,
    initial_delay=1.0,
    backoff_factor=1.5,
    max_delay=10.0
)
