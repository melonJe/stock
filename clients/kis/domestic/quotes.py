"""국내주식 시세 조회 API"""
from typing import Optional

from clients.kis.base import KISBaseClient
from config.logging_config import get_logger
from dtos.kis.quote_dtos import CurrentPriceRequestDTO, CurrentPriceResponseDTO
from core.exceptions import APIError
from core.validators import validate_symbol, ValidationError
from core.decorators import retry_on_error
from core.error_handler import handle_error

logger = get_logger(__name__)


class DomesticQuoteClient(KISBaseClient):
    """국내주식 시세 조회 클라이언트"""

    @retry_on_error(max_attempts=2, delay=1.0, exceptions=(APIError,))
    def get_current_price(self, symbol: str) -> Optional[CurrentPriceResponseDTO]:
        """
        현재가를 조회한다.

        :param symbol: 종목코드
        :return: 현재가 정보 DTO 또는 None
        """
        try:
            symbol = validate_symbol(symbol)
        except ValidationError as e:
            handle_error(e, context="DomesticQuoteClient.get_current_price", should_raise=False)
            return None

        headers = self._get_headers_with_tr_id("FHKST01010100", use_prefix=False)
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": symbol
        }
        response_data = self._get("/uapi/domestic-stock/v1/quotations/inquire-price", params, headers)

        if response_data:
            try:
                output = response_data.get("output", {})
                return int(output.get("stck_prpr", 0))
            except (KeyError, ValueError) as e:
                logger.error(f"현재가 조회 파싱 오류: {symbol} - {e}")
                return None
        return None
