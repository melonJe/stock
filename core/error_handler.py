"""중앙화된 에러 핸들러"""
import logging
import traceback
from typing import Optional, Callable, Dict, Any

from config.logging_config import get_logger
from core.exceptions import (
    StockTradingError,
    APIError,
    AuthenticationError,
    RateLimitError,
    OrderError,
    DatabaseError,
)

logger = get_logger(__name__)


def _default_alert_callback(message: str, error: Exception) -> None:
    """기본 알림 콜백 - Discord로 에러 메시지 전송"""
    try:
        from utils.discord import error_message
        error_message(f"🚨 **CRITICAL ERROR**\n{message}")
    except Exception as e:
        logger.error(f"Discord 알림 전송 실패: {e}", extra={"skip_discord": True})


class ErrorHandler:
    """중앙화된 에러 핸들러"""

    def __init__(self, alert_callback: Optional[Callable[[str, Exception], None]] = None):
        """
        :param alert_callback: 심각한 에러 발생 시 호출할 알림 함수 (None이면 Discord 기본 사용)
        """
        self.alert_callback = alert_callback or _default_alert_callback
        self._error_counts: Dict[str, int] = {}

    def handle_error(
            self,
            error: Exception,
            context: str = "",
            critical: bool = False,
            should_raise: bool = True,
            metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        에러를 처리한다.

        :param error: 발생한 예외
        :param context: 에러 발생 컨텍스트 (함수명, 작업 설명 등)
        :param critical: 심각한 에러 여부 (알림 발송)
        :param should_raise: 에러를 다시 raise할지 여부
        :param metadata: 추가 메타데이터
        """
        error_type = type(error).__name__
        error_key = f"{context}:{error_type}"

        # 에러 카운트 증가
        self._error_counts[error_key] = self._error_counts.get(error_key, 0) + 1

        # 로깅
        log_message = self._format_error_message(error, context, metadata)
        
        if critical or isinstance(error, (AuthenticationError, DatabaseError)):
            logger.critical(log_message)
            if self.alert_callback:
                self.alert_callback(log_message, error)
        elif isinstance(error, (OrderError, APIError)):
            logger.error(log_message)
        else:
            logger.warning(log_message)

        # 상세 트레이스 (DEBUG 레벨)
        if logging.getLogger().isEnabledFor(logging.DEBUG):
            logger.debug(f"에러 상세 트레이스:\n{traceback.format_exc()}")

        # 에러 재발생
        if should_raise:
            raise error

    def _format_error_message(
            self,
            error: Exception,
            context: str,
            metadata: Optional[Dict[str, Any]]
    ) -> str:
        """에러 메시지 포맷팅"""
        error_type = type(error).__name__
        error_msg = str(error)

        parts = [f"[{error_type}]"]
        
        if context:
            parts.append(f"컨텍스트: {context}")
        
        parts.append(f"메시지: {error_msg}")

        # 커스텀 예외의 추가 정보
        if isinstance(error, StockTradingError) and error.original_error:
            parts.append(f"원본 에러: {type(error.original_error).__name__}")

        if isinstance(error, RateLimitError) and error.retry_after:
            parts.append(f"재시도 대기: {error.retry_after}초")

        if metadata:
            parts.append(f"메타데이터: {metadata}")

        return " | ".join(parts)

    def get_error_stats(self) -> Dict[str, int]:
        """에러 통계 반환"""
        return self._error_counts.copy()

    def reset_error_stats(self) -> None:
        """에러 통계 초기화"""
        self._error_counts.clear()


# 전역 에러 핸들러 인스턴스
_global_error_handler: Optional[ErrorHandler] = None


def get_error_handler() -> ErrorHandler:
    """전역 에러 핸들러 인스턴스를 반환한다."""
    global _global_error_handler
    if _global_error_handler is None:
        _global_error_handler = ErrorHandler()
    return _global_error_handler


def set_error_handler(handler: ErrorHandler) -> None:
    """전역 에러 핸들러를 설정한다."""
    global _global_error_handler
    _global_error_handler = handler


def handle_error(
        error: Exception,
        context: str = "",
        critical: bool = False,
        should_raise: bool = True,
        metadata: Optional[Dict[str, Any]] = None
) -> None:
    """전역 에러 핸들러의 편의 함수"""
    get_error_handler().handle_error(error, context, critical, should_raise, metadata)
