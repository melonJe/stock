import logging
import urllib.parse
from datetime import datetime, timedelta
from typing import List, Union

import requests

from stock import setting_env
from stock.discord import discord
from stock.dto.InquireDailyCcld import InquireDailyCcldRequestDTO, InquireDailyCcldResponseDTO
from stock.dto.accountDTO import InquireBalanceRequestDTO, AccountResponseDTO, StockResponseDTO
from stock.korea_investment.utils import find_nth_open_day


class KoreaInvestmentAPI:
    def __init__(self, app_key: str, app_secret: str, account_number: str, account_code: str, authorization: str = None):
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
        auth_payload = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "appsecret": self.app_secret
        }
        response = self._post_request("/oauth2/tokenP", auth_payload, {"Content-Type": "application/json", "appkey": self.app_key, "appsecret": self.app_secret}, error_log_prefix="인증 실패")
        return f"{response['token_type']} {response['access_token']}"

    def _post_request(self, path, payload, headers=None, error_log_prefix="HTTP 요청 실패"):
        full_url = setting_env.DOMAIN + path
        effective_headers = self._headers if headers is None else headers
        try:
            response = requests.post(full_url, json=payload, headers=effective_headers)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            print(f"{error_log_prefix}. 예외: {e}.")
            return None

    def _get_request(self, path, params, headers=None, error_log_prefix="HTTP 요청 실패"):
        full_url = f"{setting_env.DOMAIN}{path}?{urllib.parse.urlencode(params)}"
        effective_headers = self._headers if headers is None else headers
        try:
            response = requests.get(full_url, headers=effective_headers)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            print(f"{error_log_prefix}. 예외: {e}.")
            return None

    def _add_tr_id_to_headers(self, tr_id_suffix: str, use_prefix: bool = True):
        headers = self._headers.copy()
        tr_id = setting_env.TR_ID + tr_id_suffix if use_prefix else tr_id_suffix
        headers["tr_id"] = tr_id
        return headers

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
                discord.error_message("stock_db\n응답 데이터 처리 실패.")
                return None
            except Exception as e:
                logging.error(f"Unexpected error: {e} - response data: {response_data}")
                discord.error_message("stock_db\n예상치 못한 오류 발생.")
                return None
        else:
            logging.warning("Null response received from API")
            discord.error_message("stock_db\nHTTP 요청 실패.")
            return None

    def get_owned_stock_info(self, stock: str = None) -> Union[List[StockResponseDTO], StockResponseDTO, None]:
        headers = self._add_tr_id_to_headers("TTC8434R")
        params = InquireBalanceRequestDTO(cano=self._account_number, acnt_prdt_cd=self._account_code, inqr_dvsn="02").__dict__
        response_data = self._get_request("/uapi/domestic-stock/v1/trading/inquire-balance", params, headers)

        if not response_data:
            logging.warning("Null response received from API")
            discord.error_message("stock_db\nHTTP 요청 실패.")
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
            discord.error_message("stock_db\n응답 데이터 처리 실패.")
            return None
        except Exception as e:
            logging.error(f"Unexpected error: {e} - response data: {response_data}")
            discord.error_message("stock_db\n예상치 못한 오류 발생.")
            return None

    def get_cancellable_or_correctable_stock(self):
        if setting_env.SIMULATE:
            return None
        headers = self._add_tr_id_to_headers("TTTC8036R", False)
        params = {
            "CANO": self._account_number,
            "ACNT_PRDT_CD": self._account_code,
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
            "INQR_DVSN_1": "0",
            "INQR_DVSN_2": "0"
        }
        response_data = self._get_request("/uapi/domestic-stock/v1/trading/inquire-psbl-rvsecncl", params, headers)
        if response_data:
            return response_data["output"]
        else:
            discord.error_message(f"stock_db\nHTTP 요청 실패. 상태 코드 : {response_data.status_code}\n{response_data}")

    def modify_stock_order(self, order_no: str, volume: str, price: str = '0', order_type: str = '03', order_code: str = '01', all_or_none: str = 'Y'):
        headers = self._add_tr_id_to_headers("TTC0803U")
        modify_payload = {
            "CANO": self._account_number,
            "ACNT_PRDT_CD": self._account_code,
            "KRX_FWDG_ORD_ORGNO": "",
            "ORGN_ODNO": order_no,
            "ORD_DVSN": order_type,
            "RVSE_CNCL_DVSN_CD": order_code,
            "ORD_QTY": volume,
            "ORD_UNPR": price,
            "QTY_ALL_ORD_YN": all_or_none
        }
        response = self._post_request("/uapi/domestic-stock/v1/trading/order-rvsecncl", modify_payload, headers)
        if response:
            return True
        else:
            discord.error_message(f"stock_db\nHTTP 요청 실패. 상태 코드 : {response.status_code}\n{response}")

    def get_domestic_market_holidays(self, base_date: datetime):
        """API로부터 휴장일 데이터를 가져옵니다."""
        headers = self._add_tr_id_to_headers("CTCA0903R", False)
        params = {
            "BASS_DT": base_date.strftime("%Y%m%d"),
            "CTX_AREA_NK": "",
            "CTX_AREA_FK": ""
        }
        response_data = self._get_request("/uapi/domestic-stock/v1/quotations/chk-holiday", params, headers)
        if response_data:
            return response_data.get("output", [])
        else:
            discord.error_message(f"stock_db\nHTTP 요청 실패. 상태 코드 : {response_data.status_code}\n{response_data}")

    def get_nth_open_day(self, nth_day: int) -> str:
        """오늘을 제외한 nth 개장일을 반환합니다."""
        current_date = datetime.now()

        while True:
            holiday_dict = {item["bass_dt"]: item for item in self.get_domestic_market_holidays(current_date)}
            self.total_holidays.update(holiday_dict)

            nth_open_day = find_nth_open_day(self.total_holidays, nth_day)  # Pass the dictionary directly
            if nth_open_day:
                return nth_open_day

            current_date += timedelta(days=20)

    def check_holiday(self, date: datetime):
        """특정 날짜가 휴장일인지 확인합니다."""
        holidays = self.get_domestic_market_holidays(date)
        for item in holidays:
            if item['bass_dt'] == date.strftime("%Y%m%d"):
                return item['opnd_yn'] == "N"
        return False

    def _create_order_payload(self, symbol: str, price: int, volume: int, order_type: str):
        """주문 페이로드를 생성합니다."""
        order_payload = {
            "CANO": self._account_number,
            "ACNT_PRDT_CD": self._account_code,
            "PDNO": symbol,
            "ORD_DVSN": order_type,
            "ORD_QTY": str(volume),
            "ORD_UNPR": str(price)
        }
        if order_payload["ORD_DVSN"] in {"01", "03", "04", "05", "06"}:
            order_payload["ORD_UNPR"] = "0"
        return order_payload

    def _create_reserve_payload(self, symbol: str, price: int, volume: int, end_date: str, order_type: str, sll_buy_dvsn_cd: str):
        """예약 주문 페이로드를 생성합니다."""
        reserve_payload = {
            "CANO": self._account_number,
            "ACNT_PRDT_CD": self._account_code,
            "PDNO": symbol,
            "ORD_QTY": str(volume),
            "ORD_UNPR": str(price),
            "SLL_BUY_DVSN_CD": sll_buy_dvsn_cd,
            "ORD_DVSN_CD": order_type,
            "ORD_OBJT_CBLC_DVSN_CD": "10"
        }
        if reserve_payload["ORD_DVSN_CD"] in {"01", "05"}:
            reserve_payload["ORD_UNPR"] = "0"
        if end_date:
            reserve_payload["RSVN_ORD_END_DT"] = end_date
        return reserve_payload

    def _send_order(self, path: str, headers, payload):
        """주문 요청을 보내고 응답을 처리합니다."""
        response = self._post_request(path, payload, headers)
        if response:
            if response["rt_cd"] == "0":
                return True
            else:
                discord.error_message(f"stock_db\n응답 코드 : {response['msg_cd']}\n응답 메세지 : {response['msg1']}")
        else:
            discord.error_message("stock_db\nHTTP path 요청 실패.")
        return False

    def inquire_daily_ccld(self, request_dto: InquireDailyCcldRequestDTO) -> Union[List[InquireDailyCcldResponseDTO], None]:
        """
        주식일별주문체결조회 API 호출 함수.

        Args:
            request_dto (InquireDailyCcldRequestDTO): 조회 요청 데이터

        Returns:
            List[InquireDailyCcldResponseDTO]: API 응답 데이터 목록
        """
        headers = self._add_tr_id_to_headers("TTTC8001R" if datetime.strptime(request_dto.INQR_END_DT, "%Y%m%d") >= datetime.now() - timedelta(days=90) else "CTSC9115R", use_prefix=False)
        params = request_dto.__dict__

        response_data = self._get_request("/uapi/domestic-stock/v1/trading/inquire-daily-ccld", params, headers)

        if response_data:
            response_list = [InquireDailyCcldResponseDTO(**item) for item in response_data.get("output1", [])]
            return response_list
        else:
            discord.error_message("stock_db\n inquire_daily_ccld HTTP 요청 실패.")
            return None
