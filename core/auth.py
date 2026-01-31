"""KIS API 인증 관리"""
import logging
from typing import Dict, Optional

from config import setting_env
from core.http_client import HttpClient


class KISAuth:
    """한국투자증권 API 인증 관리 클래스"""

    def __init__(
            self,
            app_key: str,
            app_secret: str,
            account_number: str,
            account_code: str,
            http_client: Optional[HttpClient] = None
    ):
        self._app_key = app_key
        self._app_secret = app_secret
        self._account_number = account_number
        self._account_code = account_code
        self._http_client = http_client or HttpClient()
        self._access_token: Optional[str] = None
        self._token_type: Optional[str] = None

    @property
    def app_key(self) -> str:
        return self._app_key

    @property
    def app_secret(self) -> str:
        return self._app_secret

    @property
    def account_number(self) -> str:
        return self._account_number

    @property
    def account_code(self) -> str:
        return self._account_code

    def authenticate(self) -> str:
        """
        API 인증을 수행하고 Authorization 헤더 값을 반환한다.

        :return: "Bearer {access_token}" 형식의 인증 헤더 값
        :raises Exception: 인증 실패 시
        """
        auth_header = {
            "Content-Type": "application/json",
            "appkey": self._app_key,
            "appsecret": self._app_secret
        }
        auth_payload = {
            "grant_type": "client_credentials",
            "appkey": self._app_key,
            "appsecret": self._app_secret
        }
        response = self._http_client.post(
            "/oauth2/tokenP",
            auth_payload,
            auth_header,
            error_log_prefix="인증 실패"
        )
        if response and "access_token" in response and "token_type" in response:
            self._access_token = response["access_token"]
            self._token_type = response["token_type"]
            return f"{self._token_type} {self._access_token}"
        else:
            logging.error("인증 실패: 잘못된 응답")
            raise Exception("인증 실패")

    def get_base_headers(self) -> Dict[str, str]:
        """
        API 요청에 필요한 기본 헤더를 반환한다.

        :return: 기본 헤더 딕셔너리
        """
        authorization = self.authenticate()
        return {
            "authorization": authorization,
            "content-Type": "application/json; charset=utf-8",
            "appkey": self._app_key,
            "appsecret": self._app_secret
        }

    def add_tr_id(self, headers: Dict[str, str], tr_id: str, use_prefix: bool = True) -> Dict[str, str]:
        """
        헤더에 거래 ID를 추가한다.

        :param headers: 기존 헤더
        :param tr_id: 거래 ID (접미사)
        :param use_prefix: 접두사 사용 여부
        :return: 거래 ID가 추가된 헤더
        """
        new_headers = headers.copy()
        full_tr_id = f"{setting_env.TR_ID}{tr_id}" if use_prefix else tr_id
        new_headers["tr_id"] = full_tr_id
        return new_headers
