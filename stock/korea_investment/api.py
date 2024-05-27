import logging
import urllib.parse
from datetime import datetime, timedelta
from typing import List
from typing import Union

import requests

from stock import setting_env
from stock.discord import discord
from stock.dto.account_dto import InquireBalanceRequestDTO, AccountResponseDTO, StockResponseDTO
from stock.dto.holiday_dto import HolidayResponseDTO, HolidayRequestDTO
from stock.dto.stock_trade_dto import StockTradeListRequestDTO, StockTradeListResponseDTO
from stock.korea_investment.utils import find_nth_open_day


class KoreaInvestmentAPI:
    def __init__(self, app_key: str, app_secret: str, account_number: str, account_code: str):
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

    def get_account_number(self):
        return self._account_number

    def get_account_code(self):
        return self._account_code

    def authenticate(self):
        auth_header = {
            "Content-Type": "application/json",
            "appkey": self.app_key,
            "appsecret": self.app_secret}
        auth_payload = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "appsecret": self.app_secret
        }
        response = self._post_request("/oauth2/tokenP", auth_payload, auth_header, error_log_prefix="인증 실패")
        return f"{response['token_type']} {response['access_token']}"

    def _get_request(self, path, params, headers=None, error_log_prefix="HTTP 요청 실패"):
        full_url = f"{setting_env.DOMAIN}{path}?{urllib.parse.urlencode(params)}"
        effective_headers = self._headers if headers is None else headers
        try:
            response = requests.get(full_url, headers=effective_headers)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logging.error(f"{error_log_prefix}. 예외: {e}.")
            return None

    def _post_request(self, path, payload, headers=None, error_log_prefix="HTTP 요청 실패"):
        full_url = setting_env.DOMAIN + path
        effective_headers = self._headers if headers is None else headers
        try:
            response = requests.post(full_url, json=payload, headers=effective_headers)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logging.error(f"{error_log_prefix}. 예외: {e}.")
            return None

    def _add_tr_id_to_headers(self, tr_id_suffix: str, use_prefix: bool = True):
        headers = self._headers.copy()
        tr_id = setting_env.TR_ID + tr_id_suffix if use_prefix else tr_id_suffix
        headers["tr_id"] = tr_id
        return headers

    def _create_order_payload(self, symbol: str, price: int, volume: int, order_type: str):
        """주문 페이로드를 생성합니다."""
        order_payload = {
            "CANO": self._account_number,
            "ACNT_PRDT_CD": self._account_code,
            "PDNO": symbol,
            "ORD_DVSN": order_type,
            "ORD_QTY": str(volume),
            "ORD_UNPR": "0" if order_type in {"01", "03", "04", "05", "06"} else str(price)
        }
        return order_payload

    def _create_reserve_payload(self, symbol: str, price: int, volume: int, end_date: str, order_type: str, sll_buy_dvsn_cd: str):
        """예약 주문 페이로드를 생성합니다."""
        reserve_payload = {
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
        return reserve_payload

    def _send_order(self, path: str, headers, payload):
        """주문 요청을 보내고 응답을 처리합니다."""
        response = self._post_request(path, payload, headers)
        if response:
            if response["rt_cd"] == "0":
                return True
            else:
                logging.error(f"stock_db\n응답 코드 : {response['msg_cd']}\n응답 메세지 : {response['msg1']}")
                discord.error_message(f"stock_db\n응답 코드 : {response['msg_cd']}\n응답 메세지 : {response['msg1']}")
        else:
            logging.error("stock_db\nHTTP path 요청 실패.")
            discord.error_message("stock_db\nHTTP path 요청 실패.")
        return False

    def buy(self, symbol: str, price: int, volume: int, order_type: str = "00"):
        headers = self._add_tr_id_to_headers("TTC0802U")
        order_payload = self._create_order_payload(symbol, price, volume, order_type)
        return self._send_order("/uapi/domestic-stock/v1/trading/order-cash", headers, order_payload)

    def buy_reserve(self, symbol: str, price: int, volume: int, end_date: str, order_type: str = "00"):
        headers = self._add_tr_id_to_headers("CTSC0008U", False)
        reserve_payload = self._create_reserve_payload(symbol, price, volume, end_date, order_type, "02")
        return self._send_order("/uapi/domestic-stock/v1/trading/order-resv", headers, reserve_payload)

    def sell(self, symbol: str, price: int, volume: int, order_type: str = "00"):
        headers = self._add_tr_id_to_headers("TTC0801U")
        order_payload = self._create_order_payload(symbol, price, volume, order_type)
        return self._send_order("/uapi/domestic-stock/v1/trading/order-cash", headers, order_payload)

    def sell_reserve(self, symbol: str, price: int, volume: int, end_date: str, order_type: str = "00"):
        headers = self._add_tr_id_to_headers("CTSC0008U", False)
        reserve_payload = self._create_reserve_payload(symbol, price, volume, end_date, order_type, "01")
        return self._send_order("/uapi/domestic-stock/v1/trading/order-resv", headers, reserve_payload)

    def get_account_info(self) -> Union[AccountResponseDTO, None]:
        headers = self._add_tr_id_to_headers("TTC8434R")
        params = InquireBalanceRequestDTO(cano=self._account_number, acnt_prdt_cd=self._account_code, inqr_dvsn="02").__dict__
        response_data = self._get_request("/uapi/domestic-stock/v1/trading/inquire-balance", params, headers)

        if response_data:
            try:
                return AccountResponseDTO(**response_data.get("output2", [])[0])
            except KeyError as e:
                logging.error(f"KeyError: {e} - response data: {response_data}")
                discord.error_message(f"KeyError: {e} - response data: {response_data}")
                return None
            except Exception as e:
                logging.error(f"Unexpected error: {e} - response data: {response_data}")
                discord.error_message(f"Unexpected error: {e} - response data: {response_data}")
                return None
        else:
            logging.warning("Null response received from API")
            discord.error_message("Null response received from API")
            return None

    def get_owned_stock_info(self, stock: str = None) -> Union[List[StockResponseDTO], StockResponseDTO, None]:
        headers = self._add_tr_id_to_headers("TTC8434R")
        params = InquireBalanceRequestDTO(cano=self._account_number, acnt_prdt_cd=self._account_code, inqr_dvsn="02").__dict__
        response_data = self._get_request("/uapi/domestic-stock/v1/trading/inquire-balance", params, headers)

        if not response_data:
            logging.warning("Null response received from API")
            discord.error_message("Null response received from API")
            return None

        try:
            stock_data = response_data.get("output1", [])
            response_list = [StockResponseDTO(**item) for item in stock_data]

            if stock:
                for item in response_list:
                    if item.pdno == stock:
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

    def get_domestic_market_holidays(self, date: str):
        """국내 휴장일 데이터를 API를 통해 조회합니다."""
        headers = self._add_tr_id_to_headers("CTCA0903R", False)
        params = HolidayRequestDTO(bass_dt=date).__dict__
        response = requests.get("https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/chk-holiday", headers=headers, params=params)
        response_data = response.json()
        holidays = response_data.get("output", [])
        holiday_dtos = [HolidayResponseDTO(**item) for item in holidays]
        return {dto.bass_dt: dto for dto in holiday_dtos}

    def get_nth_open_day(self, nth_day: int) -> str:
        """오늘을 제외한 nth 개장일을 반환합니다."""
        holiday_keys = sorted(self.total_holidays.keys())
        current_date = holiday_keys[-1] if holiday_keys else datetime.now().strftime("%Y%m%d")

        while True:
            nth_open_day = find_nth_open_day(self.total_holidays, nth_day + 1)  # Pass the dictionary directly
            if nth_open_day:
                return nth_open_day

            holidays = self.get_domestic_market_holidays(current_date)
            self.total_holidays.update(holidays)

    def check_holiday(self, date: str) -> bool:
        """특정 날짜가 휴장일인지 확인합니다."""
        return self.get_domestic_market_holidays(date)[date].opnd_yn == "N"

    def get_stock_order_list(self, start_date: str = datetime.now().strftime("%Y%m%d"), end_date: str = datetime.now().strftime("%Y%m%d")) -> Union[List[StockTradeListResponseDTO], None]:
        """주식 주문 목록을 가져옵니다."""
        headers = self._add_tr_id_to_headers("TTTC8001R" if datetime.strptime(end_date, "%Y%m%d") >= datetime.now() - timedelta(days=90) else "CTSC9115R", use_prefix=False)
        params = StockTradeListRequestDTO(CANO=self._account_number, ACNT_PRDT_CD=self._account_code, INQR_STRT_DT=start_date, INQR_END_DT=end_date, CCLD_DVSN='01').__dict__

        response_data = self._get_request("/uapi/domestic-stock/v1/trading/inquire-daily-ccld", params, headers)

        if response_data:
            response_list = [StockTradeListResponseDTO(**item) for item in response_data.get("output1", [])]
            return response_list
        else:
            discord.error_message("stock_db\n stock_trade_list HTTP 요청 실패.")
            return None
