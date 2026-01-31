"""커스텀 예외 클래스"""


class StockTradingError(Exception):
    """주식 거래 시스템 기본 예외"""
    def __init__(self, message: str, original_error: Exception = None):
        self.message = message
        self.original_error = original_error
        super().__init__(self.message)


# API 관련 예외
class APIError(StockTradingError):
    """API 호출 관련 예외"""
    pass


class AuthenticationError(APIError):
    """인증 실패 예외"""
    pass


class RateLimitError(APIError):
    """Rate Limit 초과 예외"""
    def __init__(self, message: str, retry_after: int = None, original_error: Exception = None):
        super().__init__(message, original_error)
        self.retry_after = retry_after


class APITimeoutError(APIError):
    """API 타임아웃 예외"""
    pass


class APIResponseError(APIError):
    """API 응답 오류"""
    def __init__(self, message: str, status_code: int = None, response_body: str = None, original_error: Exception = None):
        super().__init__(message, original_error)
        self.status_code = status_code
        self.response_body = response_body


# 주문 관련 예외
class OrderError(StockTradingError):
    """주문 처리 관련 예외"""
    pass


class InsufficientFundsError(OrderError):
    """잔고 부족 예외"""
    pass


class InvalidOrderError(OrderError):
    """잘못된 주문 요청"""
    pass


class OrderRejectedError(OrderError):
    """주문 거부"""
    def __init__(self, message: str, reject_code: str = None, original_error: Exception = None):
        super().__init__(message, original_error)
        self.reject_code = reject_code


# 데이터 관련 예외
class DataError(StockTradingError):
    """데이터 처리 관련 예외"""
    pass


class DatabaseError(DataError):
    """데이터베이스 오류"""
    pass


class DataValidationError(DataError):
    """데이터 검증 실패"""
    pass


class DataNotFoundError(DataError):
    """데이터 없음"""
    pass


# 설정 관련 예외
class ConfigurationError(StockTradingError):
    """설정 오류"""
    pass


class MissingConfigError(ConfigurationError):
    """필수 설정 누락"""
    pass


# 네트워크 관련 예외
class NetworkError(StockTradingError):
    """네트워크 오류"""
    pass


class ConnectionError(NetworkError):
    """연결 실패"""
    pass


# 전략 관련 예외
class StrategyError(StockTradingError):
    """전략 실행 오류"""
    pass


class StrategyValidationError(StrategyError):
    """전략 검증 실패"""
    pass


# URL/리소스 관련 예외
class NotFoundError(DataError):
    """리소스를 찾을 수 없음"""
    pass


# 레거시 호환용 alias (deprecated - core.exceptions 직접 사용 권장)
NotFoundUrl = NotFoundError
OrderException = OrderError
