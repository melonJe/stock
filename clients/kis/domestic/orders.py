"""국내주식 주문 API"""
import logging
from typing import Dict

from clients.kis.base import KISBaseClient


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

    def _send_order(self, path: str, headers: Dict, payload: Dict) -> bool:
        """주문 요청 전송"""
        if int(payload.get("ORD_QTY", '0')) == 0:
            logging.warning("주문 수량이 0입니다. 주문 미전송.")
            return False

        response = self._post(path, payload, headers)
        if response:
            if response.get("rt_cd") == "0":
                logging.info("주문 처리 성공")
                return True
            else:
                logging.error(f"주문 실패: {response}")
        else:
            logging.error("주문 처리 실패")
        return False

    def buy(self, symbol: str, price: int, volume: int, order_type: str = "00") -> bool:
        """매수 주문"""
        headers = self._get_headers_with_tr_id("TTC0012U")
        order_payload = self._create_order_payload(symbol, price, volume, order_type)
        return self._send_order("/uapi/domestic-stock/v1/trading/order-cash", headers, order_payload)

    def buy_reserve(self, symbol: str, price: int, volume: int, end_date: str, order_type: str = "00") -> bool:
        """예약 매수 주문"""
        headers = self._get_headers_with_tr_id("CTSC0008U", use_prefix=False)
        logging.info(f"예약 매수: {symbol}, {price}, {volume}, {end_date}")
        reserve_payload = self._create_reserve_payload(symbol, price, volume, end_date, order_type, "02")
        return self._send_order("/uapi/domestic-stock/v1/trading/order-resv", headers, reserve_payload)

    def sell(self, symbol: str, price: int, volume: int, order_type: str = "00") -> bool:
        """매도 주문"""
        headers = self._get_headers_with_tr_id("TTC0011U")
        order_payload = self._create_order_payload(symbol, price, volume, order_type)
        return self._send_order("/uapi/domestic-stock/v1/trading/order-cash", headers, order_payload)

    def sell_reserve(self, symbol: str, price: int, volume: int, end_date: str, order_type: str = "00") -> bool:
        """예약 매도 주문"""
        headers = self._get_headers_with_tr_id("CTSC0008U", use_prefix=False)
        logging.info(f"예약 매도: {symbol}, {price}, {volume}, {end_date}")
        reserve_payload = self._create_reserve_payload(symbol, price, volume, end_date, order_type, "01")
        return self._send_order("/uapi/domestic-stock/v1/trading/order-resv", headers, reserve_payload)
