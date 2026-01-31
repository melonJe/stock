"""해외주식 계좌/잔고 조회 API"""
from datetime import datetime
from typing import List, Union, Optional

from clients.kis.base import KISBaseClient
from config.logging_config import get_logger
from config.country_config import COUNTRY_CONFIG_ORDER
from data.dto.account_dto import OverseesStockResponseDTO
from data.dto.stock_trade_dto import OverseasStockTradeListRequestDTO, OverseasStockTradeListResponseDTO

logger = get_logger(__name__)


class OverseasAccountClient(KISBaseClient):
    """해외주식 계좌/잔고 조회 클라이언트"""

    def get_owned_stocks(
            self,
            country: str,
            symbol: str = None
    ) -> Union[List[OverseesStockResponseDTO], OverseesStockResponseDTO, None]:
        """해외주식 보유 종목 조회"""
        result = list()
        country_code = country.upper()
        config = COUNTRY_CONFIG_ORDER.get(country_code)
        if not config:
            logger.error(f"지원하지 않는 국가 코드: {country_code}")
            return None

        params = {
            "CANO": self.account_number,
            "ACNT_PRDT_CD": self.account_code,
            "TR_CRCY_CD": config.get("tr_crcy_cd"),
            "CTX_AREA_FK200": '',
            "CTX_AREA_NK200": '',
        }

        ovrs_excg_cd = [x.strip() for x in config.get("ovrs_excg_cd").split(',')]

        for exchange in ovrs_excg_cd:
            params['OVRS_EXCG_CD'] = exchange
            response_data = self._get(
                '/uapi/overseas-stock/v1/trading/inquire-balance',
                params,
                self._get_headers_with_tr_id("TTS3012R", use_prefix=True)
            )
            if not response_data:
                continue
            try:
                stock_data = response_data.get("output1", [])
                if stock_data:
                    result.extend([OverseesStockResponseDTO(**item) for item in stock_data])
            except KeyError as e:
                logger.error(f"해외보유종목 파싱 오류 (KeyError): {e}")
                continue
            except Exception as e:
                logger.error(f"해외보유종목 예상치 못한 오류: {e}")
                continue

        if symbol:
            for item in result:
                if item.ovrs_pdno == symbol:
                    return item
            return None

        return result if result else None

    def get_order_list(
            self,
            symbol: Optional[str] = None,
            country: Optional[str] = None,
            start_date: Optional[str] = None,
            end_date: Optional[str] = None,
    ) -> List[OverseasStockTradeListResponseDTO]:
        """해외주식 주문 내역 조회"""
        today = datetime.now().strftime("%Y%m%d")
        start_date = start_date or today
        end_date = end_date or today

        tr_id = "TTS3035R"
        headers = self._get_headers_with_tr_id(tr_id, use_prefix=True)

        all_trades: List[OverseasStockTradeListResponseDTO] = []
        ctx_nk, ctx_fk = None, None

        while True:
            params = OverseasStockTradeListRequestDTO(
                cano=self.account_number,
                acnt_prdt_cd=self.account_code,
                pdno=symbol or '%',
                ord_strt_dt=start_date,
                ord_end_dt=end_date,
                sll_buy_dvsn='00',
                ccld_nccs_dvsn='01',
                ovrs_excg_cd=country or '%',
                sort_sqn="DS",
                ctx_area_nk200=ctx_nk or '',
                ctx_area_fk200=ctx_fk or '',
            ).__dict__

            resp = self._get_raw(
                "/uapi/overseas-stock/v1/trading/inquire-ccnl",
                params,
                headers
            )
            if not resp:
                logger.error("해외주문내역 HTTP 요청 실패")
                break

            try:
                data = resp.json().get("output1", [])
                all_trades.extend(OverseasStockTradeListResponseDTO(**item) for item in data)
            except Exception as e:
                logger.error(f"JSON 파싱 에러: {e}, 응답: {resp.text}")
                break

            tr_cont = resp.headers.get('tr_cont')
            if tr_cont in ['F', 'M']:
                ctx_nk = resp.headers.get('ctx_area_nk200')
                ctx_fk = resp.headers.get('ctx_area_fk200')
                continue
            break

        return all_trades
