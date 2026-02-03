"""로깅 설정"""
import logging
import os
import sys
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from pathlib import Path
from typing import Optional

from config import setting_env


class LogLevel:
    """로그 레벨 상수"""
    DEBUG = logging.DEBUG
    INFO = logging.INFO
    WARNING = logging.WARNING
    ERROR = logging.ERROR
    CRITICAL = logging.CRITICAL


class LogConfig:
    """로깅 설정"""
    
    # 환경별 기본 로그 레벨
    ENVIRONMENT = os.getenv("ENVIRONMENT", "production")
    
    LOG_LEVEL_MAP = {
        "development": LogLevel.DEBUG,
        "staging": LogLevel.INFO,
        "production": LogLevel.WARNING,
    }
    
    DEFAULT_LOG_LEVEL = LOG_LEVEL_MAP.get(ENVIRONMENT, LogLevel.INFO)
    
    # 로그 파일 설정
    LOG_DIR = Path("logs")
    LOG_DIR.mkdir(exist_ok=True)
    
    APP_LOG_FILE = LOG_DIR / "app.log"
    ERROR_LOG_FILE = LOG_DIR / "error.log"
    TRADING_LOG_FILE = LOG_DIR / "trading.log"
    API_LOG_FILE = LOG_DIR / "api.log"
    
    # 로그 포맷
    SIMPLE_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
    DETAILED_FORMAT = (
        "%(asctime)s [%(levelname)s] "
        "%(name)s.%(funcName)s:%(lineno)d - %(message)s"
    )
    JSON_FORMAT = (
        '{"time": "%(asctime)s", "level": "%(levelname)s", '
        '"logger": "%(name)s", "function": "%(funcName)s", '
        '"line": %(lineno)d, "message": "%(message)s"}'
    )
    
    # 파일 회전 설정
    MAX_BYTES = 10 * 1024 * 1024  # 10MB
    BACKUP_COUNT = 5
    
    # 모듈별 로그 레벨 오버라이드
    MODULE_LOG_LEVELS = {
        "core.http_client": LogLevel.INFO,
        "core.auth": LogLevel.INFO,
        "clients.kis": LogLevel.INFO,
        "services.trading": LogLevel.DEBUG if ENVIRONMENT == "development" else LogLevel.INFO,
        "services.workflows": LogLevel.INFO,
        "repositories": LogLevel.WARNING,
        "urllib3": LogLevel.WARNING,  # requests 라이브러리 로그 줄이기
        "requests": LogLevel.WARNING,
    }


def get_console_handler(use_colors: bool = True) -> logging.StreamHandler:
    """콘솔 핸들러 생성"""
    handler = logging.StreamHandler(sys.stdout)
    
    if use_colors and LogConfig.ENVIRONMENT == "development":
        formatter = ColoredFormatter(LogConfig.DETAILED_FORMAT)
    else:
        formatter = logging.Formatter(LogConfig.DETAILED_FORMAT)
    
    handler.setFormatter(formatter)
    return handler


def get_file_handler(
        filename: Path,
        level: int = logging.INFO,
        use_json: bool = False
) -> RotatingFileHandler:
    """파일 핸들러 생성"""
    handler = RotatingFileHandler(
        filename,
        maxBytes=LogConfig.MAX_BYTES,
        backupCount=LogConfig.BACKUP_COUNT,
        encoding="utf-8"
    )
    handler.setLevel(level)
    
    format_str = LogConfig.JSON_FORMAT if use_json else LogConfig.DETAILED_FORMAT
    formatter = logging.Formatter(format_str)
    handler.setFormatter(formatter)
    
    return handler


def get_timed_file_handler(
        filename: Path,
        when: str = "midnight",
        interval: int = 1,
        backup_count: int = 30
) -> TimedRotatingFileHandler:
    """시간 기반 파일 핸들러 생성 (일별 로그)"""
    handler = TimedRotatingFileHandler(
        filename,
        when=when,
        interval=interval,
        backupCount=backup_count,
        encoding="utf-8"
    )
    formatter = logging.Formatter(LogConfig.DETAILED_FORMAT)
    handler.setFormatter(formatter)
    return handler


class ColoredFormatter(logging.Formatter):
    """컬러 출력을 위한 포매터"""
    
    COLORS = {
        'DEBUG': '\033[36m',      # Cyan
        'INFO': '\033[32m',       # Green
        'WARNING': '\033[33m',    # Yellow
        'ERROR': '\033[31m',      # Red
        'CRITICAL': '\033[35m',   # Magenta
    }
    RESET = '\033[0m'
    
    def format(self, record):
        log_color = self.COLORS.get(record.levelname, self.RESET)
        record.levelname = f"{log_color}{record.levelname}{self.RESET}"
        return super().format(record)


def setup_logging(
        level: Optional[int] = None,
        enable_file_logging: bool = True,
        enable_json_logging: bool = False
) -> None:
    """
    로깅 시스템 초기화
    
    :param level: 로그 레벨 (None이면 환경별 기본값 사용)
    :param enable_file_logging: 파일 로깅 활성화
    :param enable_json_logging: JSON 형식 로깅 활성화
    """
    log_level = level or LogConfig.DEFAULT_LOG_LEVEL
    
    # 루트 로거 설정
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # 기존 핸들러 제거
    root_logger.handlers.clear()
    
    # 콘솔 핸들러 추가
    console_handler = get_console_handler(use_colors=True)
    console_handler.setLevel(log_level)
    root_logger.addHandler(console_handler)
    
    if enable_file_logging:
        # 일반 로그 파일
        app_handler = get_file_handler(
            LogConfig.APP_LOG_FILE,
            level=log_level,
            use_json=enable_json_logging
        )
        root_logger.addHandler(app_handler)
        
        # 에러 로그 파일 (ERROR 이상만)
        error_handler = get_file_handler(
            LogConfig.ERROR_LOG_FILE,
            level=logging.ERROR,
            use_json=enable_json_logging
        )
        root_logger.addHandler(error_handler)
        
        # 트레이딩 전용 로그 (일별)
        trading_handler = get_timed_file_handler(
            LogConfig.TRADING_LOG_FILE,
            when="midnight",
            backup_count=90  # 90일 보관
        )
        trading_handler.addFilter(TradingLogFilter())
        root_logger.addHandler(trading_handler)
    
    # 모듈별 로그 레벨 설정
    for module_name, module_level in LogConfig.MODULE_LOG_LEVELS.items():
        logging.getLogger(module_name).setLevel(module_level)
    
    # Uvicorn access 로그에서 /health 엔드포인트 필터링
    uvicorn_access_logger = logging.getLogger("uvicorn.access")
    uvicorn_access_logger.addFilter(HealthCheckFilter())
    
    # Discord 핸들러 등록 (기존)
    try:
        from utils.discord import register_discord_critical_handler
        register_discord_critical_handler()
    except ImportError:
        pass
    
    logging.info(f"로깅 시스템 초기화 완료 (환경: {LogConfig.ENVIRONMENT}, 레벨: {logging.getLevelName(log_level)})")


class HealthCheckFilter(logging.Filter):
    """헬스체크 엔드포인트 로그 필터링 (제외)"""
    
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        return "/health" not in message


class TradingLogFilter(logging.Filter):
    """트레이딩 관련 로그만 필터링"""
    
    TRADING_KEYWORDS = [
        "매수", "매도", "주문", "거래", "trading", "order", "buy", "sell",
        "전략", "strategy", "workflow"
    ]
    
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage().lower()
        return any(keyword in message for keyword in self.TRADING_KEYWORDS)


class StructuredLogger:
    """구조화된 로깅을 위한 래퍼"""
    
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
    
    def _log(self, level: int, message: str, **kwargs):
        """구조화된 로그 출력"""
        if kwargs:
            extra_str = ", ".join(f"{k}={v}" for k, v in kwargs.items())
            full_message = f"{message} [{extra_str}]"
        else:
            full_message = message
        
        self.logger.log(level, full_message, extra=kwargs)
    
    def log(self, level: int, message: str, **kwargs):
        """표준 로그 메서드 (데코레이터 호환성)"""
        self._log(level, message, **kwargs)
    
    def debug(self, message: str, **kwargs):
        self._log(logging.DEBUG, message, **kwargs)
    
    def info(self, message: str, **kwargs):
        self._log(logging.INFO, message, **kwargs)
    
    def warning(self, message: str, **kwargs):
        self._log(logging.WARNING, message, **kwargs)
    
    def warn(self, message: str, **kwargs):
        """warning의 별칭 (표준 logging 호환)"""
        self.warning(message, **kwargs)
    
    def error(self, message: str, **kwargs):
        self._log(logging.ERROR, message, **kwargs)
    
    def critical(self, message: str, **kwargs):
        self._log(logging.CRITICAL, message, **kwargs)
    
    def exception(self, message: str, **kwargs):
        """예외 정보를 포함한 에러 로그 (표준 logging 호환)"""
        self.logger.exception(message, extra=kwargs)
    
    def setLevel(self, level: int):
        """로그 레벨 설정 (표준 logging 호환)"""
        self.logger.setLevel(level)
    
    def getEffectiveLevel(self) -> int:
        """유효 로그 레벨 반환 (표준 logging 호환)"""
        return self.logger.getEffectiveLevel()
    
    def isEnabledFor(self, level: int) -> bool:
        """특정 레벨이 활성화되어 있는지 확인 (표준 logging 호환)"""
        return self.logger.isEnabledFor(level)
    
    def trading(self, action: str, symbol: str, price: float = None, volume: int = None, **kwargs):
        """트레이딩 전용 로그"""
        log_data = {
            "action": action,
            "symbol": symbol,
        }
        if price is not None:
            log_data["price"] = price
        if volume is not None:
            log_data["volume"] = volume
        log_data.update(kwargs)
        
        self.info(f"[거래] {action}: {symbol}", **log_data)


def get_logger(name: str) -> StructuredLogger:
    """구조화된 로거 인스턴스 반환"""
    return StructuredLogger(name)
