"""HTTP 클라이언트 공통 로직"""
import logging
import urllib.parse
from time import sleep
from typing import Dict, Optional, Tuple

import requests

from config import setting_env
from config.constants import (
    API_REQUEST_DELAY,
    DEFAULT_TIMEOUT,
    MAX_RETRY_COUNT,
    RATE_LIMIT_STATUS_CODE,
    SENSITIVE_PARAMS,
)
from config.logging_config import get_logger
from core.exceptions import (
    APIError,
    RateLimitError,
    APITimeoutError,
    APIResponseError,
    NetworkError,
)

logger = get_logger(__name__)


class HttpClient:
    """KIS API HTTP 요청을 처리하는 기본 클라이언트"""

    def __init__(
            self,
            base_url: str = None,
            request_delay: float = API_REQUEST_DELAY,
            timeout: Tuple[int, int] = DEFAULT_TIMEOUT,
            verify_ssl: bool = True
    ):
        self._base_url = base_url or setting_env.DOMAIN
        self._headers: Dict[str, str] = {}
        self._request_delay = request_delay
        self._timeout = timeout
        self._verify_ssl = verify_ssl

    def set_headers(self, headers: Dict[str, str]) -> None:
        """기본 헤더 설정"""
        self._headers = headers

    def update_headers(self, headers: Dict[str, str]) -> None:
        """기본 헤더에 추가/업데이트"""
        self._headers.update(headers)

    def get_headers(self) -> Dict[str, str]:
        """현재 헤더 반환"""
        return self._headers.copy()

    @staticmethod
    def _sanitize_url(url: str) -> str:
        """로깅용 URL에서 민감 정보를 마스킹한다."""
        parsed = urllib.parse.urlparse(url)
        if not parsed.query:
            return url

        params = urllib.parse.parse_qs(parsed.query)
        sanitized_params = {}
        for key, values in params.items():
            if key.lower() in {p.lower() for p in SENSITIVE_PARAMS}:
                sanitized_params[key] = ['***MASKED***']
            else:
                sanitized_params[key] = values

        sanitized_query = urllib.parse.urlencode(sanitized_params, doseq=True)
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{sanitized_query}"

    def _handle_rate_limit(self, response: requests.Response) -> bool:
        """
        Rate Limit 응답을 처리한다. 재시도가 필요하면 True를 반환.
        
        :raises RateLimitError: Rate Limit 초과 시
        """
        if response.status_code == RATE_LIMIT_STATUS_CODE:
            retry_after = int(response.headers.get('Retry-After', 60))
            raise RateLimitError(
                f"API Rate Limit 초과. {retry_after}초 후 재시도 가능",
                retry_after=retry_after
            )
        return False

    def get_raw(
            self,
            path: str,
            params: Dict,
            headers: Optional[Dict] = None,
            error_log_prefix: str = "HTTP GET 요청 실패"
    ) -> Optional[requests.Response]:
        """
        GET 요청을 보내고 Response 객체를 반환한다.

        :param path: API 엔드포인트 경로
        :param params: 쿼리 파라미터
        :param headers: 요청 헤더 (None이면 기본 헤더 사용)
        :param error_log_prefix: 에러 로그 접두사
        :return: Response 객체 또는 None
        """
        url = f"{self._base_url}{path}?{urllib.parse.urlencode(params)}"
        effective_headers = headers if headers is not None else self._headers

        last_exception = None
        for attempt in range(MAX_RETRY_COUNT):
            sleep(self._request_delay)
            try:
                resp = requests.get(
                    url,
                    headers=effective_headers,
                    timeout=self._timeout,
                    verify=self._verify_ssl
                )

                # Rate Limit 처리
                self._handle_rate_limit(resp)

                resp.raise_for_status()
                return resp
            except RateLimitError:
                # Rate Limit은 바로 raise (재시도 데코레이터에서 처리)
                raise
            except requests.Timeout as e:
                last_exception = APITimeoutError(
                    f"{error_log_prefix}. 타임아웃 (시도 {attempt + 1}/{MAX_RETRY_COUNT})",
                    original_error=e
                )
                logger.warning(str(last_exception))
                if attempt == MAX_RETRY_COUNT - 1:
                    raise last_exception
            except requests.ConnectionError as e:
                last_exception = NetworkError(
                    f"{error_log_prefix}. 연결 실패",
                    original_error=e
                )
                logger.warning(f"URL: {self._sanitize_url(url)}, {last_exception}")
                if attempt == MAX_RETRY_COUNT - 1:
                    raise last_exception
            except requests.HTTPError as e:
                raise APIResponseError(
                    f"{error_log_prefix}. HTTP 에러",
                    status_code=e.response.status_code if e.response else None,
                    original_error=e
                )
            except requests.RequestException as e:
                raise APIError(
                    f"{error_log_prefix}. URL: {self._sanitize_url(url)}",
                    original_error=e
                )

        if last_exception:
            raise last_exception
        return None

    def get(
            self,
            path: str,
            params: Dict,
            headers: Optional[Dict] = None,
            error_log_prefix: str = "HTTP GET 요청 실패"
    ) -> Optional[Dict]:
        """
        GET 요청을 보내고 JSON 응답을 반환한다.

        :param path: API 엔드포인트 경로
        :param params: 쿼리 파라미터
        :param headers: 요청 헤더 (None이면 기본 헤더 사용)
        :param error_log_prefix: 에러 로그 접두사
        :return: JSON 응답 딕셔너리 또는 None
        """
        raw = self.get_raw(path, params, headers, error_log_prefix)
        return raw.json() if raw else None

    def post(
            self,
            path: str,
            payload: Dict,
            headers: Optional[Dict] = None,
            error_log_prefix: str = "HTTP POST 요청 실패"
    ) -> Optional[Dict]:
        """
        POST 요청을 보내고 JSON 응답을 반환한다.

        :param path: API 엔드포인트 경로
        :param payload: JSON 페이로드
        :param headers: 요청 헤더 (None이면 기본 헤더 사용)
        :param error_log_prefix: 에러 로그 접두사
        :return: JSON 응답 딕셔너리 또는 None
        """
        full_url = f"{self._base_url}{path}"
        effective_headers = headers if headers is not None else self._headers

        last_exception = None
        for attempt in range(MAX_RETRY_COUNT):
            sleep(self._request_delay)
            try:
                response = requests.post(
                    full_url,
                    json=payload,
                    headers=effective_headers,
                    timeout=self._timeout,
                    verify=self._verify_ssl
                )

                # Rate Limit 처리
                self._handle_rate_limit(response)

                response.raise_for_status()
                return response.json()
            except RateLimitError:
                raise
            except requests.Timeout as e:
                last_exception = APITimeoutError(
                    f"{error_log_prefix}. 타임아웃 (시도 {attempt + 1}/{MAX_RETRY_COUNT})",
                    original_error=e
                )
                logger.warning(str(last_exception))
                if attempt == MAX_RETRY_COUNT - 1:
                    raise last_exception
            except requests.ConnectionError as e:
                last_exception = NetworkError(
                    f"{error_log_prefix}. 연결 실패",
                    original_error=e
                )
                logger.warning(f"URL: {path}, {last_exception}")
                if attempt == MAX_RETRY_COUNT - 1:
                    raise last_exception
            except requests.HTTPError as e:
                raise APIResponseError(
                    f"{error_log_prefix}. HTTP 에러",
                    status_code=e.response.status_code if e.response else None,
                    original_error=e
                )
            except requests.RequestException as e:
                raise APIError(
                    f"{error_log_prefix}. URL: {path}",
                    original_error=e
                )

        if last_exception:
            raise last_exception
        return None
