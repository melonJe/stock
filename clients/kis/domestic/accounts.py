"""국내주식 계좌/잔고 조회 API"""
import logging
from datetime import datetime, timedelta
from typing import List, Union, Optional

from clients.kis.base import KISBaseClient
from data.dto.account_dto import (
    InquireBalanceRequestDTO,
    AccountResponseDTO,
    StockResponseDTO,
)
from data.dto.stock_trade_dto import StockTradeListRequestDTO, StockTradeListResponseDTO
from core.decorators import retry_on_error


class DomesticAccountClient(KISBaseClient):
    """국내주식 계좌/잔고 조회 클라이언트"""

    @retry_on_error(max_attempts=2, delay=1.0, exceptions=(APIError,))
    def _fetch_balance(self) -> Optional[dict]:
        """잔고 조회 API 호출 (공통)"""
        headers = self._get_headers_with_tr_id("TTC8434R")
        params = InquireBalanceRequestDTO(
            cano=self.account_number,
            acnt_prdt_cd=self.account_code,
            inqr_dvsn="02"
        ).__dict__
        return self._get("/uapi/domestic-stock/v1/trading/inquire-balance", params, headers)

    @retry_on_error(max_attempts=2, delay=1.0, exceptions=(APIError,))
    def get_account_info(self) -> Optional[AccountResponseDTO]:
        """계좌 정보 조회"""
        response_data = self._fetch_balance()

        if response_data:
            try:
                return AccountResponseDTO(**response_data.get("output2", [])[0])
            except (KeyError, IndexError) as e:
                logging.critical(f"계좌정보 파싱 오류 (KeyError/IndexError): {e}")
                return None
            except Exception as e:
                logging.critical(f"계좌정보 예상치 못한 오류: {e}")
                return None
        else:
            logging.critical("계좌정보 API 응답 없음")
            return None

    @retry_on_error(max_attempts=2, delay=1.0, exceptions=(APIError,))
    def get_owned_stocks(self, symbol: str = None) -> Union[List[StockResponseDTO], StockResponseDTO, None]:
        """국내주식 보유 종목 조회"""
        response_data = self._fetch_balance()

        if not response_data:
            return None

        try:
            stock_data = response_data.get("output1", [])
            response_list = [StockResponseDTO(**item) for item in stock_data]

            if symbol:
                for item in response_list:
                    if item.pdno == symbol:
                        return item
                return None
            else:
                return response_list
        except KeyError as e:
            logging.critical(f"보유종목 파싱 오류 (KeyError): {e}")
            return None
        except Exception as e:
            logging.critical(f"보유종목 예상치 못한 오류: {e}")
            return None

    @retry_on_error(max_attempts=2, delay=1.0, exceptions=(APIError,))
    def get_order_list(
            self,
            start_date: str = None,
            end_date: str = None
    ) -> Optional[List[StockTradeListResponseDTO]]:
        """국내주식 주문 내역 조회"""
        try:
            if not start_date:
                start_date = (datetime.now() - timedelta(days=30)).strftime("%Y%m%d")
            if not end_date:
                end_date = datetime.now().strftime("%Y%m%d")
        except Exception as e:
            error = DataError("날짜 형식 처리 실패", original_error=e)
            handle_error(error, context="DomesticAccountClient.get_order_list", should_raise=False)
            return []

        today = datetime.now().strftime("%Y%m%d")
        start_date = start_date or today
        end_date = end_date or today

        ninety_days_ago = datetime.now() - timedelta(days=90)
        if datetime.strptime(end_date, "%Y%m%d") >= ninety_days_ago:
            tr_id = "TTTC0081R"
        else:
            tr_id = "CTSC9215R"

        headers = self._get_headers_with_tr_id(tr_id, use_prefix=False)
        all_trades: List[StockTradeListResponseDTO] = []
        ctx_nk, ctx_fk = None, None

        while True:
            params = StockTradeListRequestDTO(
                CANO=self.account_number,
                ACNT_PRDT_CD=self.account_code,
                INQR_STRT_DT=start_date,
                INQR_END_DT=end_date,
                CCLD_DVSN='01',
                CTX_AREA_NK100=ctx_nk or '',
                CTX_AREA_FK100=ctx_fk or '',
            ).__dict__

            resp = self._get_raw(
                "/uapi/domestic-stock/v1/trading/inquire-daily-ccld",
                params,
                headers
            )
            if not resp:
                logging.critical("stock_order_list HTTP 요청 실패.")
                return None

            try:
                items = resp.json().get("output1", [])
                all_trades.extend(StockTradeListResponseDTO(**item) for item in items)
            except Exception as e:
                logging.critical(f"JSON 파싱 오류: {e} | 응답 본문: {resp.text}")
                return None

            tr_cont = resp.headers.get('tr_cont')
            if tr_cont in ['F', 'M']:
                ctx_nk = resp.headers.get('ctx_area_nk100')
                ctx_fk = resp.headers.get('ctx_area_fk100')
                continue

            break

        return all_trades
