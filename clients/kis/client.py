"""KIS 통합 클라이언트"""
from typing import List, Union, Dict, Optional

from core.http_client import HttpClient
from core.auth import KISAuth
from clients.kis.domestic.orders import DomesticOrderClient
from clients.kis.domestic.accounts import DomesticAccountClient
from clients.kis.domestic.quotes import DomesticQuoteClient
from clients.kis.overseas.orders import OverseasOrderClient
from clients.kis.overseas.accounts import OverseasAccountClient
from clients.kis.market.holidays import HolidayClient
from clients.kis.market.watchlist import WatchlistClient

from data.dto.account_dto import AccountResponseDTO, StockResponseDTO, OverseesStockResponseDTO, convert_overseas_to_domestic
from data.dto.holiday_dto import HolidayResponseDTO
from data.dto.stock_trade_dto import StockTradeListResponseDTO, OverseasStockTradeListResponseDTO
from data.dto.interest_stock_dto import InterestGroupListResponseDTO, InterestGroupDetailResponseDTO


class KISClient:
    """KIS 통합 클라이언트 - 기능별 클라이언트를 통합 제공"""

    def __init__(
            self,
            app_key: str,
            app_secret: str,
            account_number: str,
            account_code: str
    ):
        # 공유 인증 및 HTTP 클라이언트 (1회만 인증)
        self._auth = KISAuth(app_key, app_secret, account_number, account_code)
        self._http = HttpClient()
        self._headers = self._auth.get_base_headers()
        self._http.set_headers(self._headers)

        # 공유 객체를 주입하여 기능별 클라이언트 초기화
        shared_deps = {
            "auth": self._auth,
            "http_client": self._http,
            "headers": self._headers
        }
        self._domestic_order = DomesticOrderClient(**shared_deps)
        self._domestic_account = DomesticAccountClient(**shared_deps)
        self._domestic_quote = DomesticQuoteClient(**shared_deps)
        self._overseas_order = OverseasOrderClient(**shared_deps)
        self._overseas_account = OverseasAccountClient(**shared_deps)
        self._holiday = HolidayClient(**shared_deps)
        self._watchlist = WatchlistClient(**shared_deps)

        self.total_holidays = self._holiday.total_holidays

    @property
    def account_number(self) -> str:
        return self._auth.account_number

    @property
    def account_code(self) -> str:
        return self._auth.account_code

    def buy(self, symbol: str, price: int, volume: int, order_type: str = "00") -> bool:
        return self._domestic_order.buy(symbol, price, volume, order_type)

    def buy_reserve(self, symbol: str, price: int, volume: int, end_date: str, order_type: str = "00") -> bool:
        return self._domestic_order.buy_reserve(symbol, price, volume, end_date, order_type)

    def sell(self, symbol: str, price: int, volume: int, order_type: str = "00") -> bool:
        return self._domestic_order.sell(symbol, price, volume, order_type)

    def sell_reserve(self, symbol: str, price: int, volume: int, end_date: str, order_type: str = "00") -> bool:
        return self._domestic_order.sell_reserve(symbol, price, volume, end_date, order_type)

    def get_current_price(self, symbol: str) -> Optional[int]:
        return self._domestic_quote.get_current_price(symbol)

    def get_account_info(self) -> Optional[AccountResponseDTO]:
        return self._domestic_account.get_account_info()

    def get_korea_owned_stock_info(self, symbol: str = None) -> Union[List[StockResponseDTO], StockResponseDTO, None]:
        return self._domestic_account.get_owned_stocks(symbol)

    def get_stock_order_list(
            self,
            start_date: str = None,
            end_date: str = None
    ) -> Optional[List[StockTradeListResponseDTO]]:
        return self._domestic_account.get_order_list(start_date, end_date)

    def submit_overseas_reservation_order(
            self,
            country: str,
            action: str,
            symbol: str,
            volume: str,
            price: str
    ) -> Optional[Dict]:
        return self._overseas_order.submit_reservation_order(country, action, symbol, volume, price)

    def get_oversea_owned_stock_info(
            self,
            country: str,
            symbol: str = None
    ) -> Union[List[OverseesStockResponseDTO], OverseesStockResponseDTO, None]:
        return self._overseas_account.get_owned_stocks(country, symbol)

    def get_overseas_stock_order_list(
            self,
            symbol: Optional[str] = None,
            country: Optional[str] = None,
            start_date: Optional[str] = None,
            end_date: Optional[str] = None,
    ) -> List[OverseasStockTradeListResponseDTO]:
        return self._overseas_account.get_order_list(symbol, country, start_date, end_date)

    def get_owned_stock_info(self, symbol: str = None) -> Union[List[StockResponseDTO], StockResponseDTO, None]:
        """국내/해외 주식 보유 정보를 조회하는 인터페이스"""
        if symbol:
            result = self.get_korea_owned_stock_info(symbol)
            if result:
                return result
            return self.get_oversea_owned_stock_info(country='USA', symbol=symbol)

        korea_list = self.get_korea_owned_stock_info()
        oversea_raw = self.get_oversea_owned_stock_info(country='USA')

        korea_list = korea_list or []
        oversea_list = convert_overseas_to_domestic(oversea_raw or [])

        return korea_list + oversea_list

    def get_domestic_market_holidays(self, date: str) -> Dict[str, HolidayResponseDTO]:
        result = self._holiday.get_holidays(date)
        self.total_holidays.update(result)
        return result

    def get_nth_open_day(self, nth_day: int) -> Optional[str]:
        return self._holiday.get_nth_open_day(nth_day)

    def check_holiday(self, date: str) -> bool:
        return self._holiday.check_holiday(date)

    def get_interest_group_list(
            self,
            user_id: str,
            group_type: str = "1",
            fid_etc_cls_code: str = "00",
            custtype: str = "P"
    ) -> Optional[InterestGroupListResponseDTO]:
        return self._watchlist.get_groups(user_id, group_type, fid_etc_cls_code, custtype)

    def get_interest_group_stocks(
            self,
            user_id: str,
            inter_grp_code: str,
            group_type: str = "1",
            data_rank: str = "",
            inter_grp_name: str = "",
            hts_kor_isnm: str = "",
            cntg_cls_code: str = "",
            fid_etc_cls_code: str = "4",
            custtype: str = "P"
    ) -> Optional[InterestGroupDetailResponseDTO]:
        return self._watchlist.get_stocks_by_group(
            user_id, inter_grp_code, group_type, data_rank,
            inter_grp_name, hts_kor_isnm, cntg_cls_code, fid_etc_cls_code, custtype
        )
