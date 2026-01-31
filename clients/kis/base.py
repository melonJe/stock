"""KIS API 기본 클라이언트"""
from typing import Dict, Optional, Any

from core.http_client import HttpClient
from core.auth import KISAuth


class KISBaseClient:
    """KIS API 기본 클라이언트 - 인증 및 HTTP 요청 처리"""

    def __init__(
            self,
            app_key: Optional[str] = None,
            app_secret: Optional[str] = None,
            account_number: Optional[str] = None,
            account_code: Optional[str] = None,
            *,
            auth: Optional[KISAuth] = None,
            http_client: Optional[HttpClient] = None,
            headers: Optional[Dict[str, str]] = None
    ):
        """
        KIS API 기본 클라이언트 초기화.

        직접 credentials를 전달하거나, 이미 생성된 auth/http_client를 주입받을 수 있다.

        :param app_key: 앱 키 (직접 생성 시)
        :param app_secret: 앱 시크릿 (직접 생성 시)
        :param account_number: 계좌번호 (직접 생성 시)
        :param account_code: 계좌코드 (직접 생성 시)
        :param auth: 공유할 KISAuth 인스턴스 (주입 시)
        :param http_client: 공유할 HttpClient 인스턴스 (주입 시)
        :param headers: 공유할 헤더 (주입 시)
        """
        if auth and http_client and headers:
            # 주입 모드: 공유 객체 사용
            self._auth = auth
            self._http = http_client
            self._headers = headers
        else:
            # 직접 생성 모드: 새 객체 생성
            self._auth = KISAuth(app_key, app_secret, account_number, account_code)
            self._http = HttpClient()
            self._headers = self._auth.get_base_headers()
            self._http.set_headers(self._headers)

        self.total_holidays: Dict[str, Any] = {}

    @property
    def account_number(self) -> str:
        return self._auth.account_number

    @property
    def account_code(self) -> str:
        return self._auth.account_code

    def _get_headers_with_tr_id(self, tr_id: str, use_prefix: bool = True) -> Dict[str, str]:
        """거래 ID가 추가된 헤더 반환"""
        return self._auth.add_tr_id(self._headers, tr_id, use_prefix)

    def _get(
            self,
            path: str,
            params: Dict,
            headers: Optional[Dict] = None,
            error_log_prefix: str = "HTTP GET 요청 실패"
    ) -> Optional[Dict]:
        """GET 요청"""
        return self._http.get(path, params, headers or self._headers, error_log_prefix)

    def _get_raw(
            self,
            path: str,
            params: Dict,
            headers: Optional[Dict] = None,
            error_log_prefix: str = "HTTP GET 요청 실패"
    ):
        """GET 요청 (Response 객체 반환)"""
        return self._http.get_raw(path, params, headers or self._headers, error_log_prefix)

    def _post(
            self,
            path: str,
            payload: Dict,
            headers: Optional[Dict] = None,
            error_log_prefix: str = "HTTP POST 요청 실패"
    ) -> Optional[Dict]:
        """POST 요청"""
        return self._http.post(path, payload, headers or self._headers, error_log_prefix)
