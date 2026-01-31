"""국내주식 주문 API"""
from typing import Dict

from clients.kis.base import KISBaseClient
from config.logging_config import get_logger
from core.validators import validate_symbol, validate_price, validate_volume, validate_order_type, ValidationError
from core.exceptions import OrderError, InvalidOrderError
from core.decorators import retry_on_error
from core.error_handler import handle_error

logger = get_logger(__name__)


class DomesticOrderClient(KISBaseClient):
    """국내주식 주문 클라이언트"""

    def _create_order_payload(self, symbol: str, price: int, volume: int, order_type: str) -> Dict:
        """주문 페이로드 생성"""
        return {
            "CANO": self.account_number,
            "ACNT_PRDT_CD": self.account_code,
            "PDNO": symbol,
            "ORD_DVSN": order_type,
            "ORD_QTY": str(volume),
            "ORD_UNPR": "0" if order_type in {"01", "03", "04", "05", "06"} else str(price)
        }

    def _create_reserve_payload(
            self,
            symbol: str,
            price: int,
            volume: int,
            end_date: str,
            order_type: str,
            sll_buy_dvsn_cd: str
    ) -> Dict:
        """예약주문 페이로드 생성"""
        return {
            "CANO": self.account_number,
            "ACNT_PRDT_CD": self.account_code,
            "PDNO": symbol,
            "ORD_QTY": str(volume),
            "ORD_UNPR": "0" if order_type in {"01", "05"} else str(price),
            "SLL_BUY_DVSN_CD": sll_buy_dvsn_cd,
            "ORD_DVSN_CD": order_type,
            "ORD_OBJT_CBLC_DVSN_CD": "10",
            "RSVN_ORD_END_DT": end_date if end_date else ''
        }

    def _send_order(self, endpoint: str, headers: Dict, payload: Dict) -> bool:
        """주문 요청 전송"""
        response = self._post(endpoint, payload, headers)
        if response:
            if response.get("rt_cd") == "0":
                logger.info("주문 처리 성공", endpoint=endpoint)
                return True
            else:
                logger.error("주문 실패", response=response, endpoint=endpoint)
        else:
            logger.error("주문 처리 실패", endpoint=endpoint)
        return False

    def buy(self, symbol: str, price: int, volume: int, order_type: str = "00") -> bool:
        """매수 주문"""
        try:
            symbol = validate_symbol(symbol)
            price = int(validate_price(price, min_value=0))
            volume = validate_volume(volume, min_value=1)
            order_type = validate_order_type(order_type)
        except ValidationError as e:
            error = InvalidOrderError(f"매수 주문 입력값 검증 실패: {symbol}", original_error=e)
            handle_error(error, context="DomesticOrderClient.buy", should_raise=False)
            return False

        try:
            headers = self._get_headers_with_tr_id("TTC0012U")
            order_payload = self._create_order_payload(symbol, price, volume, order_type)
            return self._send_order("/uapi/domestic-stock/v1/trading/order-cash", headers, order_payload)
        except Exception as e:
            error = OrderError(f"매수 주문 실행 실패: {symbol}", original_error=e)
            handle_error(
                error,
                context="DomesticOrderClient.buy",
                metadata={"symbol": symbol, "price": price, "volume": volume},
                should_raise=False
            )
            return False

    def buy_reserve(self, symbol: str, price: int, volume: int, end_date: str, order_type: str = "00") -> bool:
        """예약 매수 주문"""
        try:
            symbol = validate_symbol(symbol)
            price = int(validate_price(price, min_value=0))
            volume = validate_volume(volume, min_value=1)
            order_type = validate_order_type(order_type)
        except ValidationError as e:
            logging.error(f"예약 매수 입력값 검증 실패: {e}")
            return False

        headers = self._get_headers_with_tr_id("CTSC0008U", use_prefix=False)
        logging.info(f"예약 매수: {symbol}, {price}, {volume}, {end_date}")
        reserve_payload = self._create_reserve_payload(symbol, price, volume, end_date, order_type, "02")
        return self._send_order("/uapi/domestic-stock/v1/trading/order-resv", headers, reserve_payload)

    def sell(self, symbol: str, price: int, volume: int, order_type: str = "00") -> bool:
        """매도 주문"""
        try:
            symbol = validate_symbol(symbol)
            price = int(validate_price(price, min_value=0))
            volume = validate_volume(volume, min_value=1)
            order_type = validate_order_type(order_type)
        except ValidationError as e:
            logging.error(f"매도 주문 입력값 검증 실패: {e}")
            return False

        headers = self._get_headers_with_tr_id("TTC0011U")
        order_payload = self._create_order_payload(symbol, price, volume, order_type)
        return self._send_order("/uapi/domestic-stock/v1/trading/order-cash", headers, order_payload)

    def sell_reserve(self, symbol: str, price: int, volume: int, end_date: str, order_type: str = "00") -> bool:
        """예약 매도 주문"""
        try:
            symbol = validate_symbol(symbol)
            price = int(validate_price(price, min_value=0))
            volume = validate_volume(volume, min_value=1)
            order_type = validate_order_type(order_type)
        except ValidationError as e:
            logging.error(f"예약 매도 입력값 검증 실패: {e}")
            return False

        headers = self._get_headers_with_tr_id("CTSC0008U", use_prefix=False)
        logging.info(f"예약 매도: {symbol}, {price}, {volume}, {end_date}")
        reserve_payload = self._create_reserve_payload(symbol, price, volume, end_date, order_type, "01")
        return self._send_order("/uapi/domestic-stock/v1/trading/order-resv", headers, reserve_payload)
