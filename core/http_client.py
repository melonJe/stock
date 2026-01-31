"""HTTP 클라이언트 공통 로직"""
import logging
import urllib.parse
from time import sleep
from typing import Dict, Optional

import requests

from config import setting_env

# API 요청 간 대기 시간 (초) - Rate Limit 방지
API_REQUEST_DELAY = 0.5


class HttpClient:
    """KIS API HTTP 요청을 처리하는 기본 클라이언트"""

    def __init__(self, base_url: str = None, request_delay: float = API_REQUEST_DELAY):
        self._base_url = base_url or setting_env.DOMAIN
        self._headers: Dict[str, str] = {}
        self._request_delay = request_delay

    def set_headers(self, headers: Dict[str, str]) -> None:
        """기본 헤더 설정"""
        self._headers = headers

    def update_headers(self, headers: Dict[str, str]) -> None:
        """기본 헤더에 추가/업데이트"""
        self._headers.update(headers)

    def get_headers(self) -> Dict[str, str]:
        """현재 헤더 반환"""
        return self._headers.copy()

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
        sleep(self._request_delay)
        url = f"{self._base_url}{path}?{urllib.parse.urlencode(params)}"
        effective_headers = headers if headers is not None else self._headers
        try:
            resp = requests.get(url, headers=effective_headers)
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            logging.info(f"{error_log_prefix}. URL: {url}, 예외: {e}")
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
        sleep(self._request_delay)
        full_url = f"{self._base_url}{path}"
        effective_headers = headers if headers is not None else self._headers
        try:
            response = requests.post(full_url, json=payload, headers=effective_headers)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logging.error(f"{error_log_prefix}. 예외: {e}, URL: {full_url}")
            return None
