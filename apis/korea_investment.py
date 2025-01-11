import logging
import urllib.parse
from datetime import datetime, timedelta
from typing import List, Union, Dict, Optional

import requests

from config import setting_env
from config.country_config import COUNTRY_CONFIG_ORDER
from data.dto.account_dto import InquireBalanceRequestDTO, AccountResponseDTO, StockResponseDTO, OverseesStockResponseDTO
from data.dto.holiday_dto import HolidayResponseDTO, HolidayRequestDTO
from data.dto.stock_trade_dto import StockTradeListRequestDTO, StockTradeListResponseDTO
from utils import discord
from utils.operations import find_nth_open_day


class KoreaInvestmentAPI:
    def __init__(self, app_key: str, app_secret: str, account_number: str, account_code: str):
        """
        Initialize the KoreaInvestmentAPI with necessary credentials.

        :param app_key: Application key issued by Korea Investment.
        :param app_secret: Application secret key issued by Korea Investment.
        :param account_number: User's account number.
        :param account_code: User's account product code.
        """
        self.app_key = app_key
        self.app_secret = app_secret
        self._account_number = account_number
        self._account_code = account_code
        authorization = self.authenticate()
        self._headers = {
            "Authorization": authorization,
            "Content-Type": "application/json",
            "appkey": app_key,
            "appsecret": app_secret
        }
        self.total_holidays = {}

    def get_account_number(self) -> str:
        """Get the account number."""
        return self._account_number

    def get_account_code(self) -> str:
        """Get the account product code."""
        return self._account_code

    def authenticate(self) -> str:
        """
        Authenticate with the API and obtain the authorization header.

        :return: Authorization header string.
        """
        auth_header = {
            "Content-Type": "application/json",
            "appkey": self.app_key,
            "appsecret": self.app_secret
        }
        auth_payload = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "appsecret": self.app_secret
        }
        response = self._post_request(
            "/oauth2/tokenP",
            auth_payload,
            auth_header,
            error_log_prefix="인증 실패"
        )
        if response and "access_token" in response and "token_type" in response:
            return f"{response['token_type']} {response['access_token']}"
        else:
            logging.error("Authentication failed: Invalid response.")
            raise Exception("Authentication failed.")

    def _get_request(
            self,
            path: str,
            params: Dict,
            headers: Optional[Dict] = None,
            error_log_prefix: str = "HTTP 요청 실패"
    ) -> Optional[Dict]:
        """
        Send a GET request to the specified API endpoint.

        :param path: API endpoint path.
        :param params: Query parameters.
        :param headers: Optional headers to override default headers.
        :param error_log_prefix: Prefix for error logging.
        :return: JSON response as a dictionary or None if failed.
        """
        full_url = f"{setting_env.DOMAIN}{path}?{urllib.parse.urlencode(params)}"
        effective_headers = self._headers if headers is None else headers
        try:
            response = requests.get(full_url, headers=effective_headers)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logging.error(f"{error_log_prefix}. 예외: {e}, URL: {full_url}")
            return None

    def _post_request(
            self,
            path: str,
            payload: Dict,
            headers: Optional[Dict] = None,
            error_log_prefix: str = "HTTP 요청 실패"
    ) -> Optional[Dict]:
        """
        Send a POST request to the specified API endpoint.

        :param path: API endpoint path.
        :param payload: JSON payload.
        :param headers: Optional headers to override default headers.
        :param error_log_prefix: Prefix for error logging.
        :return: JSON response as a dictionary or None if failed.
        """
        full_url = f"{setting_env.DOMAIN}{path}"
        effective_headers = self._headers if headers is None else headers
        try:
            response = requests.post(full_url, json=payload, headers=effective_headers)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logging.error(f"{error_log_prefix}. 예외: {e}, URL: {full_url}, Payload: {payload}")
            return None

    def _add_tr_id_to_headers(self, tr_id_suffix: str, use_prefix: bool = True) -> Dict:
        """
        Add a transaction ID to the headers.

        :param tr_id_suffix: Suffix for the transaction ID.
        :param use_prefix: Whether to use the prefix defined in settings.
        :return: Updated headers dictionary.
        """
        headers = self._headers.copy()
        tr_id = f"{setting_env.TR_ID}{tr_id_suffix}" if use_prefix else tr_id_suffix
        headers["tr_id"] = tr_id
        return headers

    def _create_order_payload(self, symbol: str, price: int, volume: int, order_type: str) -> Dict:
        """
        Create a payload for placing an order.

        :param symbol: Stock symbol.
        :param price: Order price.
        :param volume: Order volume.
        :param order_type: Order type code.
        :return: Dictionary representing the order payload.
        """
        return {
            "CANO": self._account_number,
            "ACNT_PRDT_CD": self._account_code,
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
        """
        Create a payload for placing a reserve order.

        :param symbol: Stock symbol.
        :param price: Order price.
        :param volume: Order volume.
        :param end_date: Reservation end date.
        :param order_type: Order type code.
        :param sll_buy_dvsn_cd: Sell/Buy division code.
        :return: Dictionary representing the reserve order payload.
        """
        return {
            "CANO": self._account_number,
            "ACNT_PRDT_CD": self._account_code,
            "PDNO": symbol,
            "ORD_QTY": str(volume),
            "ORD_UNPR": "0" if order_type in {"01", "05"} else str(price),
            "SLL_BUY_DVSN_CD": sll_buy_dvsn_cd,
            "ORD_DVSN_CD": order_type,
            "ORD_OBJT_CBLC_DVSN_CD": "10",
            "RSVN_ORD_END_DT": end_date if end_date else ''
        }

    def _send_order(self, path: str, headers: Dict, payload: Dict) -> bool:
        """
        Send an order request and handle the response.

        :param path: API endpoint path.
        :param headers: Request headers.
        :param payload: Request payload.
        :return: True if the order was successful, False otherwise.
        """
        if int(payload.get("ORD_QTY", '0')) == 0:
            logging.warning("Order quantity is zero. Order not sent.")
            return False

        response = self._post_request(path, payload, headers)
        if response:
            if response.get("rt_cd") == "0":
                logging.info("Order processed successfully.")
                return True
            else:
                logging.error(f"Order failed: {response}")
        else:
            logging.error(f"Order processing failed for payload: {payload}")
        return False

    def buy(self, symbol: str, price: int, volume: int, order_type: str = "00") -> bool:
        """
        Place a buy order.
        """
        headers = self._add_tr_id_to_headers("TTC0802U")
        order_payload = self._create_order_payload(symbol, price, volume, order_type)
        return self._send_order("/uapi/domestic-stock/v1/trading/order-cash", headers, order_payload)

    def buy_reserve(self, symbol: str, price: int, volume: int, end_date: str, order_type: str = "00") -> bool:
        """
        Place a reserve buy order.
        """
        headers = self._add_tr_id_to_headers("CTSC0008U", use_prefix=False)
        logging.info(f"예약 매수: {symbol}, {price}, {volume}, {end_date}")
        reserve_payload = self._create_reserve_payload(symbol, price, volume, end_date, order_type, "02")
        return self._send_order("/uapi/domestic-stock/v1/trading/order-resv", headers, reserve_payload)

    def sell(self, symbol: str, price: int, volume: int, order_type: str = "00") -> bool:
        """
        Place a sell order.
        """
        headers = self._add_tr_id_to_headers("TTC0801U")
        order_payload = self._create_order_payload(symbol, price, volume, order_type)
        return self._send_order("/uapi/domestic-stock/v1/trading/order-cash", headers, order_payload)

    def sell_reserve(self, symbol: str, price: int, volume: int, end_date: str, order_type: str = "00") -> bool:
        """
        Place a reserve sell order.
        """
        headers = self._add_tr_id_to_headers("CTSC0008U", use_prefix=False)
        logging.info(f"예약 매도: {symbol}, {price}, {volume}, {end_date}")
        reserve_payload = self._create_reserve_payload(symbol, price, volume, end_date, order_type, "01")
        return self._send_order("/uapi/domestic-stock/v1/trading/order-resv", headers, reserve_payload)

    def get_account_info(self) -> Union[AccountResponseDTO, None]:
        """
        Retrieve account information.
        """
        headers = self._add_tr_id_to_headers("TTC8434R")
        params = InquireBalanceRequestDTO(
            cano=self._account_number,
            acnt_prdt_cd=self._account_code,
            inqr_dvsn="02"
        ).__dict__
        response_data = self._get_request("/uapi/domestic-stock/v1/trading/inquire-balance", params, headers)

        if response_data:
            try:
                return AccountResponseDTO(**response_data.get("output2", [])[0])
            except (KeyError, IndexError) as e:
                logging.error(f"KeyError or IndexError: {e} - response data: {response_data}")
                discord.error_message(f"KeyError or IndexError: {e} - response data: {response_data}")
                return None
            except Exception as e:
                logging.error(f"Unexpected error: {e} - response data: {response_data}")
                discord.error_message(f"Unexpected error: {e} - response data: {response_data}")
                return None
        else:
            logging.warning("Null response received from API for account info.")
            discord.error_message("Null response received from API for account info.")
            return None

    def get_owned_stock_info(self, symbol: str = None) -> Union[List[StockResponseDTO], StockResponseDTO, None]:
        """
        국내/해외 주식 보유 정보를 조회하는 인터페이스.
        """
        if symbol:
            result = self.get_korea_owned_stock_info(symbol)
            if result:
                return result
            return self.get_oversea_owned_stock_info(country='USA', symbol=symbol)
        else:
            return self.get_korea_owned_stock_info() + self.get_oversea_owned_stock_info(country='USA')

    def get_korea_owned_stock_info(self, symbol: str = None) -> Union[List[StockResponseDTO], StockResponseDTO, None]:
        """
        Retrieve owned (domestic) stock information.
        """
        headers = self._add_tr_id_to_headers("TTC8434R")
        params = InquireBalanceRequestDTO(
            cano=self._account_number,
            acnt_prdt_cd=self._account_code,
            inqr_dvsn="02"
        ).__dict__
        response_data = self._get_request("/uapi/domestic-stock/v1/trading/inquire-balance", params, headers)

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
            logging.error(f"KeyError: {e} - response data: {response_data}")
            discord.error_message(f"KeyError: {e} - response data: {response_data}")
            return None
        except Exception as e:
            logging.error(f"Unexpected error: {e} - response data: {response_data}")
            discord.error_message(f"Unexpected error: {e} - response data: {response_data}")
            return None

    def get_oversea_owned_stock_info(self, country: str, symbol: str = None) -> Union[List[OverseesStockResponseDTO], OverseesStockResponseDTO, None]:
        """
        해외주식 잔고 조회 API를 호출하는 메서드.
        """
        country_code = country.upper()
        config = COUNTRY_CONFIG_ORDER.get(country_code)
        if not config:
            logging.error(f"Unsupported country code: {country_code}")
            return None

        # 조회에 필요한 GET 파라미터 구성
        params = {
            "CANO": self._account_number,
            "ACNT_PRDT_CD": self._account_number,
            "OVRS_EXCG_CD": config.get("ovrs_excg_cd"),
            "TR_CRCY_CD": config.get("tr_crcy_cd")
        }
        response_data = self._get_request('/uapi/overseas-stock/v1/trading/inquire-balance', params, self._add_tr_id_to_headers("TTS3012R", use_prefix=True))

        if not response_data:
            return None

        try:
            stock_data = response_data.get("output1", [])
            response_list = [OverseesStockResponseDTO(**item) for item in stock_data]

            if symbol:
                for item in response_list:
                    if item.ovrs_pdno == symbol:
                        return item
                return None
            else:
                return response_list
        except KeyError as e:
            logging.error(f"KeyError: {e} - response data: {response_data}")
            discord.error_message(f"KeyError: {e} - response data: {response_data}")
            return None
        except Exception as e:
            logging.error(f"Unexpected error: {e} - response data: {response_data}")
            discord.error_message(f"Unexpected error: {e} - response data: {response_data}")
            return None

    def get_domestic_market_holidays(self, date: str) -> Dict[str, HolidayResponseDTO]:
        """
        Retrieve domestic market holidays for a specific date.
        """
        headers = self._add_tr_id_to_headers("CTCA0903R", use_prefix=False)
        params = HolidayRequestDTO(bass_dt=date).__dict__
        response = self._get_request(
            "/uapi/domestic-stock/v1/quotations/chk-holiday",
            params,
            headers,
            error_log_prefix="Holiday API 요청 실패"
        )
        holidays = response.get("output", []) if response else []
        holiday_dtos = [HolidayResponseDTO(**item) for item in holidays]
        return {dto.bass_dt: dto for dto in holiday_dtos}

    def get_nth_open_day(self, nth_day: int) -> Optional[str]:
        """
        Retrieve the nth open day excluding today.
        """
        holiday_keys = sorted(self.total_holidays.keys())
        current_date = holiday_keys[-1] if holiday_keys else datetime.now().strftime("%Y%m%d")

        while True:
            nth_open_day = find_nth_open_day(self.total_holidays, nth_day + 1)
            if nth_open_day:
                return nth_open_day

            holidays = self.get_domestic_market_holidays(current_date)
            self.total_holidays.update(holidays)
            current_date = max(holidays.keys(), default=current_date)

    def check_holiday(self, date: str) -> bool:
        """
        Check if a specific date is a holiday.
        """
        holidays = self.get_domestic_market_holidays(date)
        holiday = holidays.get(date)
        return holiday.opnd_yn == "N" if holiday else False

    def get_stock_order_list(self, start_date: str = None, end_date: str = None) -> Union[List[StockTradeListResponseDTO], None]:
        """
        Retrieve the list of stock trades within a date range.
        """
        if not start_date:
            start_date = datetime.now().strftime("%Y%m%d")
        if not end_date:
            end_date = datetime.now().strftime("%Y%m%d")

        # 최근 90일 여부에 따른 tr_id 결정
        ninety_days_ago = datetime.now() - timedelta(days=90)
        if datetime.strptime(end_date, "%Y%m%d") >= ninety_days_ago:
            tr_id = "TTTC8001R"
        else:
            tr_id = "CTSC9115R"

        headers = self._add_tr_id_to_headers(tr_id, use_prefix=False)
        params = StockTradeListRequestDTO(
            CANO=self._account_number,
            ACNT_PRDT_CD=self._account_code,
            INQR_STRT_DT=start_date,
            INQR_END_DT=end_date,
            CCLD_DVSN='01'
        ).__dict__

        response_data = self._get_request(
            "/uapi/domestic-stock/v1/trading/inquire-daily-ccld",
            params,
            headers
        )

        if response_data:
            try:
                response_list = [StockTradeListResponseDTO(**item) for item in response_data.get("output1", [])]
                return response_list
            except KeyError as e:
                logging.error(f"KeyError: {e} - response data: {response_data}")
                discord.error_message(f"KeyError: {e} - response data: {response_data}")
                return None
            except Exception as e:
                logging.error(f"Unexpected error: {e} - response data: {response_data}")
                discord.error_message(f"Unexpected error: {e} - response data: {response_data}")
                return None
        else:
            discord.error_message("stock_trade_list HTTP 요청 실패.")
            return None

    def submit_overseas_reservation_order(self, country: str, action: str, symbol: str, volume: str, price: str, end_date: Optional[str] = None, ) -> Optional[Dict]:
        """
        Submit an overseas stock reservation order.
        """
        country_code = country.upper()
        config = COUNTRY_CONFIG_ORDER.get(country_code)
        if not config:
            logging.error(f"Unsupported country code: {country_code}")
            return None

        if action.lower() == 'buy':
            tr_id = config.get("tr_id_buy")
            sll_buy_dvsn_cd = config.get("sll_buy_dvsn_cd_buy")
            ord_dvsn = config.get("ord_dvsn_buy")
        elif action.lower() == 'sell':
            tr_id = config.get("tr_id_sell")
            sll_buy_dvsn_cd = config.get("sll_buy_dvsn_cd_sell")
            ord_dvsn = config.get("ord_dvsn_sell")
        else:
            logging.error(f"Invalid action: {action}. Must be 'buy' or 'sell'.")
            return None

        prdt_type_cd = config.get("prdt_type_cd")
        ovrs_excg_cd = config.get("ovrs_excg_cd")
        ord_dvsn = ord_dvsn if ord_dvsn else "00"
        ovrs_rsvn_odno = config.get("ovrs_rsvn_odno")

        payload = {
            "CANO": self._account_number,
            "ACNT_PRDT_CD": self._account_code,
            "PDNO": symbol,
            "OVRS_EXCG_CD": ovrs_excg_cd,
            "FT_ORD_QTY": volume,
            "FT_ORD_UNPR3": price,
            "ORD_DVSN": ord_dvsn,
            "SLL_BUY_DVSN_CD": sll_buy_dvsn_cd,
            "PRDT_TYPE_CD": prdt_type_cd,
            "RSVN_ORD_RCIT_DT": end_date,
            "OVRS_RSVN_ODNO": ovrs_rsvn_odno
        }

        headers = self._add_tr_id_to_headers(tr_id, use_prefix=False)
        path = "/uapi/overseas-stock/v1/trading/order-resv"
        response_data = self._post_request(
            path=path,
            payload=payload,
            headers=headers,
            error_log_prefix="해외 예약 주문 API 요청 실패"
        )

        if response_data:
            if response_data.get("rt_cd") == "0":
                logging.info("해외 예약 주문이 성공적으로 접수되었습니다.")
                return response_data
            else:
                logging.error(f"해외 예약 주문 실패: {response_data}")
                return response_data
        else:
            logging.error("해외 예약 주문 요청에 실패했습니다.")
            return None


# 사용 예시
if __name__ == "__main__":
    # KoreaInvestmentAPI 인스턴스 생성
    api = KoreaInvestmentAPI(
        app_key=setting_env.APP_KEY,
        app_secret=setting_env.APP_SECRET,
        account_number=setting_env.ACCOUNT_NUMBER,
        account_code=setting_env.ACCOUNT_CODE
    )
    print(api.get_korea_owned_stock_info() + api.get_oversea_owned_stock_info(country='USA'))
    # response = api.submit_overseas_reservation_order(
    #     country="USA",
    #     action="buy",
    #     symbol="AAPL",
    #     volume="1",
    #     price="148.00",
    #     end_date=api.get_nth_open_day(1)  # 예약 종료일자 (예시)
    # )
    # if response:
    #     print(json.dumps(response, indent=4, ensure_ascii=False))
    # else:
    #     print("해외 예약 주문 요청에 실패했습니다.")

    # response = api.get_oversea_owned_stock_info(country="USA")
    # print(json.dumps(response, indent=4, ensure_ascii=False))
