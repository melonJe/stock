"""국내주식 시세 조회 API"""
import logging
from typing import Optional

from clients.kis.base import KISBaseClient


class DomesticQuoteClient(KISBaseClient):
    """국내주식 시세 조회 클라이언트"""

    def get_current_price(self, symbol: str) -> Optional[int]:
        """
        현재가 조회

        :param symbol: 종목코드 (6자리)
        :return: 현재가 (정수) 또는 None
        """
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
                logging.error(f"현재가 조회 파싱 오류: {symbol} - {e}")
                return None
        return None
