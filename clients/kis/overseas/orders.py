"""해외주식 주문 API"""
import logging
from typing import Dict

from clients.kis.base import KISBaseClient
from dtos.kis.overseas_order_dtos import OverseasReservationOrderRequestDTO
from core.exceptions import OrderError, InvalidOrderError
from core.validators import validate_symbol, validate_price, validate_volume, ValidationError
from core.error_handler import handle_errorER
from config.country_config import COUNTRY_CONFIG_ORDER


class OverseasOrderClient(KISBaseClient):
    """해외주식 주문 클라이언트"""

    def submit_reservation_order(self, country_code: str, symbol: str, action: str, price: float, volume: int) -> bool:
        """
        해외주식 예약 주문을 제출한다.

        :param country_code: 국가코드
        :param symbol: 종목코드
        :param action: 매수/매도 (buy/sell)
        :param price: 가격
        :param volume: 수량
        :return: 성공 여부
        """
        try:
            symbol = validate_symbol(symbol)
            price = validate_price(price, min_value=0)
            volume = validate_volume(volume, min_value=1)
        except ValidationError as e:
            error = InvalidOrderError(f"해외 예약 주문 입력값 검증 실패: {symbol}", original_error=e)
            handle_error(error, context="OverseasOrderClient.submit_reservation_order", should_raise=False)
            return False

        config = COUNTRY_CONFIG_ORDER.get(country_code)
        if not config:
            error = InvalidOrderError(f"지원하지 않는 국가 코드: {country_code}")
            handle_error(error, context="OverseasOrderClient.submit_reservation_order", should_raise=False)
            return False

        if action.lower() == 'buy':
            tr_id = config.get("tr_id_buy")
            sll_buy_dvsn_cd = config.get("sll_buy_dvsn_cd_buy")
            ord_dvsn = config.get("ord_dvsn_buy")
        elif action.lower() == 'sell':
            tr_id = config.get("tr_id_sell")
            sll_buy_dvsn_cd = config.get("sll_buy_dvsn_cd_sell")
            ord_dvsn = config.get("ord_dvsn_sell")
        else:
            logging.error(f"잘못된 action: {action}. 'buy' 또는 'sell'이어야 합니다.")
            return None

        prdt_type_cd = config.get("prdt_type_cd")
        ovrs_excg_cd = [x.strip() for x in config.get("ovrs_excg_cd").split(',')]
        ord_dvsn = ord_dvsn if ord_dvsn else "00"
        ovrs_rsvn_odno = config.get("ovrs_rsvn_odno")
        rvse_cncl_dvsn_cd = config.get("RVSE_CNCL_DVSN_CD")

        for exchange in ovrs_excg_cd:
            payload = {
                "CANO": self.account_number,
                "ACNT_PRDT_CD": self.account_code,
                "RVSE_CNCL_DVSN_CD": rvse_cncl_dvsn_cd,
                "PDNO": symbol,
                "OVRS_EXCG_CD": exchange,
                "FT_ORD_QTY": volume,
                "FT_ORD_UNPR3": price,
                "ORD_DVSN": ord_dvsn,
                "SLL_BUY_DVSN_CD": sll_buy_dvsn_cd,
                "PRDT_TYPE_CD": prdt_type_cd,
                "ORD_SVR_DVSN_CD": "0",
                "OVRS_RSVN_ODNO": ovrs_rsvn_odno
            }
            payload = {k: v for k, v in payload.items() if v is not None}

            headers = self._get_headers_with_tr_id(tr_id, use_prefix=True)
            path = "/uapi/overseas-stock/v1/trading/order-resv"
            response_data = self._post(
                path=path,
                payload=payload,
                headers=headers,
                error_log_prefix="해외 예약 주문 API 요청 실패"
            )

            if not response_data:
                continue

            if response_data.get("rt_cd") == "0":
                logging.info("해외 예약 주문이 성공적으로 접수되었습니다.")
                return response_data
            else:
                if '해당종목정보가 없습니다' in response_data.get('msg1', ''):
                    continue
                logging.error(f"{symbol} 해외 예약 주문 실패: {response_data}")
                continue

        return None
