"""비동기 HTTP 클라이언트"""
import urllib.parse
from typing import Dict, Optional, Tuple
import asyncio

import httpx

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


class AsyncHttpClient:
    """비동기 HTTP 클라이언트"""

    def __init__(
            self,
            base_url: str = None,
            headers: Optional[Dict[str, str]] = None,
            request_delay: float = API_REQUEST_DELAY,
            timeout: Tuple[int, int] = DEFAULT_TIMEOUT,
            verify_ssl: bool = True
    ):
        """
        :param base_url: API 기본 URL
        :param headers: 기본 헤더
        :param request_delay: API 요청 간 대기 시간 (초)
        :param timeout: (connect_timeout, read_timeout)
        :param verify_ssl: SSL 인증서 검증 여부
        """
        self._base_url = base_url or setting_env.DOMAIN
        self._headers = headers or {}
        self._request_delay = request_delay
        self._timeout = httpx.Timeout(timeout[0], read=timeout[1])
        self._verify_ssl = verify_ssl
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        """컨텍스트 매니저 진입"""
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=self._timeout,
            verify=self._verify_ssl,
            http2=True  # HTTP/2 지원
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """컨텍스트 매니저 종료"""
        if self._client:
            await self._client.aclose()

    def set_headers(self, headers: Dict[str, str]) -> None:
        """헤더 설정"""
        self._headers = headers

    def update_headers(self, headers: Dict[str, str]) -> None:
        """헤더 업데이트"""
        self._headers.update(headers)

    def get_headers(self) -> Dict[str, str]:
        """현재 헤더 반환"""
        return self._headers.copy()

    def _sanitize_url(self, url: str) -> str:
        """민감한 정보를 마스킹한 URL 반환"""
        parsed = urllib.parse.urlparse(url)
        query_params = urllib.parse.parse_qs(parsed.query)

        sanitized_params = {}
        for key, values in query_params.items():
            if key.lower() in {p.lower() for p in SENSITIVE_PARAMS}:
                sanitized_params[key] = ['***MASKED***']
            else:
                sanitized_params[key] = values

        sanitized_query = urllib.parse.urlencode(sanitized_params, doseq=True)
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{sanitized_query}"

    def _handle_rate_limit(self, response: httpx.Response) -> None:
        """Rate Limit 응답 처리"""
        if response.status_code == RATE_LIMIT_STATUS_CODE:
            retry_after = int(response.headers.get('Retry-After', 60))
            raise RateLimitError(
                f"API Rate Limit 초과. {retry_after}초 후 재시도 가능",
                retry_after=retry_after
            )

    async def get_raw(
            self,
            path: str,
            params: Dict,
            headers: Optional[Dict] = None,
            error_log_prefix: str = "HTTP GET 요청 실패"
    ) -> Optional[httpx.Response]:
        """
        비동기 GET 요청 (Response 객체 반환)

        :param path: API 엔드포인트 경로
        :param params: 쿼리 파라미터
        :param headers: 요청 헤더
        :param error_log_prefix: 에러 로그 접두사
        :return: Response 객체 또는 None
        """
        url = f"{self._base_url}{path}"
        effective_headers = headers if headers is not None else self._headers

        if not self._client:
            self._client = httpx.AsyncClient(
                timeout=self._timeout,
                verify=self._verify_ssl,
                http2=True
            )

        last_exception = None
        for attempt in range(MAX_RETRY_COUNT):
            await asyncio.sleep(self._request_delay)
            try:
                resp = await self._client.get(
                    url,
                    params=params,
                    headers=effective_headers
                )

                self._handle_rate_limit(resp)
                resp.raise_for_status()
                return resp

            except RateLimitError:
                raise
            except httpx.TimeoutException as e:
                last_exception = APITimeoutError(
                    f"{error_log_prefix}. 타임아웃 (시도 {attempt + 1}/{MAX_RETRY_COUNT})",
                    original_error=e
                )
                logger.warning(str(last_exception))
                if attempt == MAX_RETRY_COUNT - 1:
                    raise last_exception
            except httpx.ConnectError as e:
                last_exception = NetworkError(
                    f"{error_log_prefix}. 연결 실패",
                    original_error=e
                )
                logger.warning(f"URL: {self._sanitize_url(url)}, {last_exception}")
                if attempt == MAX_RETRY_COUNT - 1:
                    raise last_exception
            except httpx.HTTPStatusError as e:
                raise APIResponseError(
                    f"{error_log_prefix}. HTTP 에러",
                    status_code=e.response.status_code if e.response else None,
                    original_error=e
                )
            except httpx.HTTPError as e:
                raise APIError(
                    f"{error_log_prefix}. URL: {self._sanitize_url(url)}",
                    original_error=e
                )

        if last_exception:
            raise last_exception
        return None

    async def get(
            self,
            path: str,
            params: Dict,
            headers: Optional[Dict] = None,
            error_log_prefix: str = "HTTP GET 요청 실패"
    ) -> Optional[Dict]:
        """
        비동기 GET 요청 (JSON 딕셔너리 반환)

        :param path: API 엔드포인트 경로
        :param params: 쿼리 파라미터
        :param headers: 요청 헤더
        :param error_log_prefix: 에러 로그 접두사
        :return: JSON 응답 딕셔너리 또는 None
        """
        raw = await self.get_raw(path, params, headers, error_log_prefix)
        return raw.json() if raw else None

    async def post(
            self,
            path: str,
            payload: Dict,
            headers: Optional[Dict] = None,
            error_log_prefix: str = "HTTP POST 요청 실패"
    ) -> Optional[Dict]:
        """
        비동기 POST 요청

        :param path: API 엔드포인트 경로
        :param payload: JSON 페이로드
        :param headers: 요청 헤더
        :param error_log_prefix: 에러 로그 접두사
        :return: JSON 응답 딕셔너리 또는 None
        """
        full_url = f"{self._base_url}{path}"
        effective_headers = headers if headers is not None else self._headers

        if not self._client:
            self._client = httpx.AsyncClient(
                timeout=self._timeout,
                verify=self._verify_ssl,
                http2=True
            )

        last_exception = None
        for attempt in range(MAX_RETRY_COUNT):
            await asyncio.sleep(self._request_delay)
            try:
                response = await self._client.post(
                    full_url,
                    json=payload,
                    headers=effective_headers
                )

                self._handle_rate_limit(response)
                response.raise_for_status()
                return response.json()

            except RateLimitError:
                raise
            except httpx.TimeoutException as e:
                last_exception = APITimeoutError(
                    f"{error_log_prefix}. 타임아웃 (시도 {attempt + 1}/{MAX_RETRY_COUNT})",
                    original_error=e
                )
                logger.warning(str(last_exception))
                if attempt == MAX_RETRY_COUNT - 1:
                    raise last_exception
            except httpx.ConnectError as e:
                last_exception = NetworkError(
                    f"{error_log_prefix}. 연결 실패",
                    original_error=e
                )
                logger.warning(f"URL: {path}, {last_exception}")
                if attempt == MAX_RETRY_COUNT - 1:
                    raise last_exception
            except httpx.HTTPStatusError as e:
                raise APIResponseError(
                    f"{error_log_prefix}. HTTP 에러",
                    status_code=e.response.status_code if e.response else None,
                    original_error=e
                )
            except httpx.HTTPError as e:
                raise APIError(
                    f"{error_log_prefix}. URL: {path}",
                    original_error=e
                )

        if last_exception:
            raise last_exception
        return None

    async def close(self):
        """클라이언트 종료"""
        if self._client:
            await self._client.aclose()
            self._client = None
