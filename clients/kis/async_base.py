"""KIS API 비동기 클라이언트 베이스"""
from typing import Dict, Optional

from core.async_auth import AsyncKISAuth
from core.async_http_client import AsyncHttpClient


class AsyncKISBaseClient:
    """KIS API 비동기 클라이언트 베이스 클래스"""

    def __init__(
            self,
            app_key: str,
            app_secret: str,
            account_number: str,
            account_code: str,
            auth: Optional[AsyncKISAuth] = None,
            http_client: Optional[AsyncHttpClient] = None,
            headers: Optional[Dict[str, str]] = None
    ):
        """
        :param app_key: 앱 키
        :param app_secret: 앱 시크릿
        :param account_number: 계좌번호
        :param account_code: 계좌코드
        :param auth: 인증 인스턴스 (선택)
        :param http_client: HTTP 클라이언트 (선택)
        :param headers: 초기 헤더 (선택)
        """
        self._app_key = app_key
        self._app_secret = app_secret
        self._account_number = account_number
        self._account_code = account_code

        # 인증 및 HTTP 클라이언트 설정
        if http_client is not None:
            self._http_client = http_client
            self._own_http_client = False
        else:
            self._http_client = AsyncHttpClient()
            self._own_http_client = True

        if auth is not None:
            self._auth = auth
            self._own_auth = False
        else:
            self._auth = AsyncKISAuth(
                app_key=app_key,
                app_secret=app_secret,
                account_number=account_number,
                account_code=account_code,
                http_client=self._http_client
            )
            self._own_auth = True

        # 헤더 설정
        self._headers = headers or {}

    @property
    def account_number(self) -> str:
        return self._account_number

    @property
    def account_code(self) -> str:
        return self._account_code

    async def _get_headers_with_tr_id(self, tr_id_suffix: str, use_prefix: bool = True) -> Dict[str, str]:
        """
        TR ID가 포함된 헤더 반환

        :param tr_id_suffix: TR ID 접미사
        :param use_prefix: TR_ID 접두사 사용 여부
        :return: 헤더 딕셔너리
        """
        from config import setting_env

        base_headers = await self._auth.get_base_headers()
        base_headers.update(self._headers)

        tr_id = f"{setting_env.TR_ID}{tr_id_suffix}" if use_prefix else tr_id_suffix
        base_headers["tr_id"] = tr_id

        return base_headers

    async def _get(
            self,
            path: str,
            params: Dict,
            headers: Optional[Dict] = None,
            error_log_prefix: str = "GET 요청 실패"
    ) -> Optional[Dict]:
        """비동기 GET 요청"""
        return await self._http_client.get(path, params, headers, error_log_prefix)

    async def _post(
            self,
            path: str,
            payload: Dict,
            headers: Optional[Dict] = None,
            error_log_prefix: str = "POST 요청 실패"
    ) -> Optional[Dict]:
        """비동기 POST 요청"""
        return await self._http_client.post(path, payload, headers, error_log_prefix)

    async def close(self):
        """리소스 정리"""
        if self._own_auth:
            await self._auth.close()
        if self._own_http_client:
            await self._http_client.close()
