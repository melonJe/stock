"""KIS API 인증 관리"""
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional

from config import setting_env
from config.logging_config import get_logger
from core.http_client import HttpClient
from core.exceptions import AuthenticationError, APIError
from core.decorators import retry_on_error, log_execution

# 토큰 만료 전 갱신 여유 시간 (초)
TOKEN_REFRESH_BUFFER_SECONDS = 300

logger = get_logger(__name__)


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
        self._token_expires_at: Optional[datetime] = None

    @property
    def app_key(self) -> str:
        return self._app_key

    @property
    def account_number(self) -> str:
        return self._account_number

    @property
    def account_code(self) -> str:
        return self._account_code

    def is_token_valid(self) -> bool:
        """토큰이 유효한지 확인한다."""
        if not self._access_token or not self._token_expires_at:
            return False
        # 만료 시간 전 버퍼 시간을 두고 갱신
        return datetime.now() < (self._token_expires_at - timedelta(seconds=TOKEN_REFRESH_BUFFER_SECONDS))

    @retry_on_error(max_attempts=2, delay=2.0, exceptions=(APIError,))
    @log_execution(level=logging.INFO)
    def authenticate(self, force: bool = False) -> str:
        """
        API 인증을 수행하고 Authorization 헤더 값을 반환한다.

        :param force: 강제 재인증 여부
        :return: "Bearer {access_token}" 형식의 인증 헤더 값
        :raises AuthenticationError: 인증 실패 시
        """
        # 유효한 토큰이 있으면 재사용
        if not force and self.is_token_valid():
            return f"{self._token_type} {self._access_token}"

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
        
        try:
            response = self._http_client.post(
                "/oauth2/tokenP",
                auth_payload,
                auth_header,
                error_log_prefix="인증 실패"
            )
        except Exception as e:
            raise AuthenticationError("API 인증 요청 실패", original_error=e)

        if response and "access_token" in response and "token_type" in response:
            self._access_token = response["access_token"]
            self._token_type = response["token_type"]
            # 토큰 만료 시간 저장 (기본 24시간, API 응답에 expires_in이 있으면 사용)
            expires_in = response.get("expires_in", 86400)
            self._token_expires_at = datetime.now() + timedelta(seconds=expires_in)
            logger.info(f"토큰 발급 완료. 만료: {self._token_expires_at.strftime('%Y-%m-%d %H:%M:%S')}")
            return f"{self._token_type} {self._access_token}"
        else:
            raise AuthenticationError("인증 응답이 유효하지 않습니다.")

    def ensure_valid_token(self) -> str:
        """토큰이 유효한지 확인하고, 만료되었으면 갱신한다."""
        if not self.is_token_valid():
            return self.authenticate(force=True)
        return f"{self._token_type} {self._access_token}"

    def get_base_headers(self) -> Dict[str, str]:
        """
        API 요청에 필요한 기본 헤더를 반환한다.

        :return: 기본 헤더 딕셔너리
        """
        authorization = self.ensure_valid_token()
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
