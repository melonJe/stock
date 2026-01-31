"""비동기 KIS API 인증 관리"""
from datetime import datetime, timedelta
from typing import Dict, Optional

from config import setting_env
from config.logging_config import get_logger
from core.async_http_client import AsyncHttpClient
from core.exceptions import AuthenticationError, APIError
from core.decorators import retry_on_error, log_execution

# 토큰 만료 전 갱신 여유 시간 (초)
TOKEN_REFRESH_BUFFER_SECONDS = 300

logger = get_logger(__name__)


class AsyncKISAuth:
    """한국투자증권 API 비동기 인증 관리 클래스"""

    def __init__(
            self,
            app_key: str,
            app_secret: str,
            account_number: str,
            account_code: str,
            http_client: Optional[AsyncHttpClient] = None
    ):
        """
        :param app_key: 앱 키
        :param app_secret: 앱 시크릿
        :param account_number: 계좌번호
        :param account_code: 계좌코드
        :param http_client: HTTP 클라이언트 (None이면 자체 생성)
        """
        self._app_key = app_key
        self._app_secret = app_secret
        self._account_number = account_number
        self._account_code = account_code
        self._http_client = http_client or AsyncHttpClient()
        self._own_http_client = http_client is None

        self._access_token: Optional[str] = None
        self._token_type: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None

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

    def is_token_valid(self) -> bool:
        """토큰이 유효한지 확인"""
        if not self._access_token or not self._token_expires_at:
            return False
        return datetime.now() < (self._token_expires_at - timedelta(seconds=TOKEN_REFRESH_BUFFER_SECONDS))

    @retry_on_error(max_attempts=2, delay=2.0, exceptions=(APIError,))
    @log_execution(level=logging.INFO)
    async def authenticate(self, force: bool = False) -> str:
        """
        API 인증을 수행하고 Authorization 헤더 값을 반환

        :param force: 강제 재인증 여부
        :return: "Bearer {access_token}" 형식의 인증 헤더 값
        :raises AuthenticationError: 인증 실패 시
        """
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
            response = await self._http_client.post(
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
            expires_in = response.get("expires_in", 86400)
            self._token_expires_at = datetime.now() + timedelta(seconds=expires_in)
            logger.info(f"토큰 발급 완료. 만료: {self._token_expires_at.strftime('%Y-%m-%d %H:%M:%S')}")
            return f"{self._token_type} {self._access_token}"
        else:
            raise AuthenticationError("인증 응답이 유효하지 않습니다.")

    async def ensure_valid_token(self) -> str:
        """토큰이 유효한지 확인하고, 만료되었으면 갱신"""
        if not self.is_token_valid():
            return await self.authenticate(force=True)
        return f"{self._token_type} {self._access_token}"

    async def get_base_headers(self) -> Dict[str, str]:
        """
        API 요청에 필요한 기본 헤더를 반환

        :return: 기본 헤더 딕셔너리
        """
        authorization = await self.ensure_valid_token()
        return {
            "authorization": authorization,
            "content-Type": "application/json; charset=utf-8",
            "appkey": self._app_key,
            "appsecret": self._app_secret
        }

    async def close(self):
        """리소스 정리"""
        if self._own_http_client and self._http_client:
            await self._http_client.close()
