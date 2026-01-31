"""데코레이터 모음"""
import functools
import logging
import time
from typing import Callable, Type, Tuple, Optional

from config.logging_config import get_logger
from core.exceptions import APIError, RateLimitError, APITimeoutError, NetworkError

logger = get_logger(__name__)


def retry_on_error(
        max_attempts: int = 3,
        delay: float = 1.0,
        backoff: float = 2.0,
        exceptions: Tuple[Type[Exception], ...] = (APIError, NetworkError),
        exclude_exceptions: Tuple[Type[Exception], ...] = (),
        on_retry: Optional[Callable] = None
):
    """
    에러 발생 시 재시도하는 데코레이터

    :param max_attempts: 최대 시도 횟수
    :param delay: 첫 재시도 대기 시간 (초)
    :param backoff: 재시도마다 delay에 곱할 배수 (exponential backoff)
    :param exceptions: 재시도할 예외 튜플
    :param exclude_exceptions: 재시도하지 않을 예외 튜플
    :param on_retry: 재시도 전 실행할 콜백 함수
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            current_delay = delay
            last_exception = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exclude_exceptions as e:
                    # 제외된 예외는 즉시 raise
                    logger.error(f"{func.__name__} 재시도 제외 예외 발생: {type(e).__name__}: {e}")
                    raise
                except exceptions as e:
                    last_exception = e
                    if attempt == max_attempts:
                        logger.error(f"{func.__name__} 최대 재시도 횟수({max_attempts}) 도달. 실패.")
                        raise
                    
                    # RateLimitError의 경우 retry_after 사용
                    if isinstance(e, RateLimitError) and e.retry_after:
                        wait_time = e.retry_after
                    else:
                        wait_time = current_delay

                    logger.warning(
                        f"{func.__name__} 실패 (시도 {attempt}/{max_attempts}): "
                        f"{type(e).__name__}: {e}. {wait_time:.1f}초 후 재시도"
                    )

                    # 콜백 실행
                    if on_retry:
                        on_retry(attempt, e)

                    time.sleep(wait_time)
                    current_delay *= backoff

            # 이 지점에 도달하면 모든 시도 실패
            if last_exception:
                raise last_exception

        return wrapper
    return decorator


def log_execution(level: int = logging.INFO, include_args: bool = False):
    """
    함수 실행을 로깅하는 데코레이터

    :param level: 로깅 레벨
    :param include_args: 인자 포함 여부
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            func_name = func.__name__
            
            if include_args:
                args_repr = [repr(a) for a in args]
                kwargs_repr = [f"{k}={v!r}" for k, v in kwargs.items()]
                signature = ", ".join(args_repr + kwargs_repr)
                logger.log(level, f"{func_name}({signature}) 시작")
            else:
                logger.log(level, f"{func_name} 시작")

            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                elapsed = time.time() - start_time
                logger.log(level, f"{func_name} 완료 ({elapsed:.2f}초)")
                return result
            except Exception as e:
                elapsed = time.time() - start_time
                logger.error(f"{func_name} 실패 ({elapsed:.2f}초): {type(e).__name__}: {e}")
                raise

        return wrapper
    return decorator


def measure_time(func: Callable) -> Callable:
    """함수 실행 시간을 측정하는 데코레이터"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        elapsed = time.time() - start_time
        logger.debug(f"{func.__name__} 실행 시간: {elapsed:.4f}초")
        return result
    return wrapper


def suppress_errors(default_return=None, log_level: int = logging.ERROR):
    """
    에러를 억제하고 기본값을 반환하는 데코레이터 (주의해서 사용)

    :param default_return: 에러 발생 시 반환할 기본값
    :param log_level: 로깅 레벨
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.log(
                    log_level,
                    f"{func.__name__} 에러 억제됨: {type(e).__name__}: {e}"
                )
                return default_return

        return wrapper
    return decorator
