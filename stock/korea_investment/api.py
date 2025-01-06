import json
import logging
import urllib.parse
import urllib.parse
from datetime import datetime
from datetime import timedelta
from typing import List, Union, Dict
from typing import Optional

import requests

from stock import setting_env
from stock.discord import discord
from stock.dto.account_dto import InquireBalanceRequestDTO, AccountResponseDTO, StockResponseDTO
from stock.dto.holiday_dto import HolidayResponseDTO, HolidayRequestDTO
from stock.dto.stock_trade_dto import StockTradeListRequestDTO, StockTradeListResponseDTO
from stock.korea_investment.country_config import COUNTRY_CONFIG_ORDER
from stock.korea_investment.operations import find_nth_open_day
from stock.service.data_handler import get_stock_symbol_type


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
        response = self._post_request("/oauth2/tokenP", auth_payload, auth_header, error_log_prefix="인증 실패")
        if response and "access_token" in response and "token_type" in response:
            return f"{response['token_type']} {response['access_token']}"
        else:
            logging.error("Authentication failed: Invalid response.")
            raise Exception("Authentication failed.")

    def _get_request(self, path: str, params: Dict, headers: Optional[Dict] = None, error_log_prefix: str = "HTTP 요청 실패") -> Optional[Dict]:
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
            logging.error(f"{error_log_prefix}. 예외: {e}. URL: {full_url}")
            return None

    def _post_request(self, path: str, payload: Dict, headers: Optional[Dict] = None, error_log_prefix: str = "HTTP 요청 실패") -> Optional[Dict]:
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
            logging.error(f"{error_log_prefix}. 예외: {e}. URL: {full_url}, Payload: {payload}")
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
        order_payload = {
            "CANO": self._account_number,
            "ACNT_PRDT_CD": self._account_code,
            "PDNO": symbol,
            "ORD_DVSN": order_type,
            "ORD_QTY": str(volume),
            "ORD_UNPR": "0" if order_type in {"01", "03", "04", "05", "06"} else str(price)
        }
        return order_payload

    def _create_reserve_payload(self, symbol: str, price: int, volume: int, end_date: str, order_type: str, sll_buy_dvsn_cd: str) -> Dict:
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
            logging.error(f"Order processing failed for payload: {payload}.")
        return False

    def buy(self, symbol: str, price: int, volume: int, order_type: str = "00") -> bool:
        """
        Place a buy order.

        :param symbol: Stock symbol.
        :param price: Order price.
        :param volume: Order volume.
        :param order_type: Order type code.
        :return: True if successful, False otherwise.
        """
        headers = self._add_tr_id_to_headers("TTC0802U")
        order_payload = self._create_order_payload(symbol, price, volume, order_type)
        return self._send_order("/uapi/domestic-stock/v1/trading/order-cash", headers, order_payload)

    def buy_reserve(self, symbol: str, price: int, volume: int, end_date: str, order_type: str = "00") -> bool:
        """
        Place a reserve buy order.

        :param symbol: Stock symbol.
        :param price: Order price.
        :param volume: Order volume.
        :param end_date: Reservation end date.
        :param order_type: Order type code.
        :return: True if successful, False otherwise.
        """
        headers = self._add_tr_id_to_headers("CTSC0008U", use_prefix=False)
        logging.info(f"예약 매수: {symbol}, {price}, {volume}, {end_date}")
        reserve_payload = self._create_reserve_payload(symbol, price, volume, end_date, order_type, "02")
        return self._send_order("/uapi/domestic-stock/v1/trading/order-resv", headers, reserve_payload)

    def sell(self, symbol: str, price: int, volume: int, order_type: str = "00") -> bool:
        """
        Place a sell order.

        :param symbol: Stock symbol.
        :param price: Order price.
        :param volume: Order volume.
        :param order_type: Order type code.
        :return: True if successful, False otherwise.
        """
        headers = self._add_tr_id_to_headers("TTC0801U")
        order_payload = self._create_order_payload(symbol, price, volume, order_type)
        return self._send_order("/uapi/domestic-stock/v1/trading/order-cash", headers, order_payload)

    def sell_reserve(self, symbol: str, price: int, volume: int, end_date: str, order_type: str = "00") -> bool:
        """
        Place a reserve sell order.

        :param symbol: Stock symbol.
        :param price: Order price.
        :param volume: Order volume.
        :param end_date: Reservation end date.
        :param order_type: Order type code.
        :return: True if successful, False otherwise.
        """
        headers = self._add_tr_id_to_headers("CTSC0008U", use_prefix=False)
        logging.info(f"예약 매도: {symbol}, {price}, {volume}, {end_date}")
        reserve_payload = self._create_reserve_payload(symbol, price, volume, end_date, order_type, "01")
        return self._send_order("/uapi/domestic-stock/v1/trading/order-resv", headers, reserve_payload)

    def get_account_info(self) -> Union[AccountResponseDTO, None]:
        """
        Retrieve account information.

        :return: AccountResponseDTO object or None if failed.
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
        Retrieve owned stock information.

        :param symbol: Specific stock symbol to filter. If None, return all.
        :return: List of StockResponseDTO objects, a single StockResponseDTO, or None if failed.
        """
        if not get_stock_symbol_type(symbol) == "KOR":
            return None

        # TODO 외국 주식 보유 량 return code 추가

        headers = self._add_tr_id_to_headers("TTC8434R")
        params = InquireBalanceRequestDTO(
            cano=self._account_number,
            acnt_prdt_cd=self._account_code,
            inqr_dvsn="02"
        ).__dict__
        response_data = self._get_request("/uapi/domestic-stock/v1/trading/inquire-balance", params, headers)

        if not response_data:
            logging.warning("Null response received from API for owned stock info.")
            discord.error_message("Null response received from API for owned stock info.")
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

    def get_domestic_market_holidays(self, date: str) -> Dict[str, HolidayResponseDTO]:
        """
        Retrieve domestic market holidays for a specific date.

        :param date: Date in YYYYMMDD format.
        :return: Dictionary mapping date to HolidayResponseDTO.
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

        :param nth_day: Number of open days to skip.
        :return: Date string in YYYYMMDD format or None if not found.
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

        :param date: Date in YYYYMMDD format.
        :return: True if it's a holiday, False otherwise.
        """
        holidays = self.get_domestic_market_holidays(date)
        holiday = holidays.get(date)
        return holiday.opnd_yn == "N" if holiday else False

    def get_stock_order_list(self, start_date: str = None, end_date: str = None) -> Union[List[StockTradeListResponseDTO], None]:
        """
        Retrieve the list of stock trades within a date range.

        :param start_date: Start date in YYYYMMDD format. Defaults to today.
        :param end_date: End date in YYYYMMDD format. Defaults to today.
        :return: List of StockTradeListResponseDTO objects or None if failed.
        """
        if not start_date:
            start_date = datetime.now().strftime("%Y%m%d")
        if not end_date:
            end_date = datetime.now().strftime("%Y%m%d")

        tr_id = "TTTC8001R" if datetime.strptime(end_date, "%Y%m%d") >= datetime.now() - timedelta(days=90) else "CTSC9115R"
        headers = self._add_tr_id_to_headers(tr_id, use_prefix=False)
        params = StockTradeListRequestDTO(
            CANO=self._account_number,
            ACNT_PRDT_CD=self._account_code,
            INQR_STRT_DT=start_date,
            INQR_END_DT=end_date,
            CCLD_DVSN='01'
        ).__dict__

        response_data = self._get_request("/uapi/domestic-stock/v1/trading/inquire-daily-ccld", params, headers)

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

    # 해외주식 예약 주문 메서드 추가
    def submit_overseas_reservation_order(
            self,
            country_code: str,
            action: str,  # 'buy' or 'sell'
            cano: str,
            acnt_prdt_cd: str,
            pdno: str,
            ft_ord_qty: str,
            ft_ord_unpr3: str,
            end_date: Optional[str] = None,
            tr_id: Optional[str] = None,
            rvse_cncl_dvsn_cd: Optional[str] = None,
            seq_no: Optional[str] = None,
            mac_address: Optional[str] = None,
            phone_number: Optional[str] = None,
            ip_addr: Optional[str] = None,
            gt_uid: Optional[str] = None
    ) -> Optional[Dict]:
        """
        Submit an overseas stock reservation order.

        :param country_code: 3-letter country code (e.g., 'USA', 'CHN', 'HKG', 'JPN', 'VNM').
        :param action: 'buy' or 'sell'.
        :param cano: 종합계좌번호.
        :param acnt_prdt_cd: 계좌상품코드.
        :param pdno: 상품번호.
        :param ft_ord_qty: 주문수량.
        :param ft_ord_unpr3: 주문단가3.
        :param end_date: 예약 주문 종료일자 (YYYYMMDD).
        :param tr_id: 거래ID. If not provided, it will be set based on country and action.
        :param rvse_cncl_dvsn_cd: 정정취소구분코드 (필요 시).
        :param seq_no: 일련번호 (법인 필수).
        :param mac_address: 맥주소 (법인 또는 개인 고객 필수).
        :param phone_number: 핸드폰번호 (법인 필수).
        :param ip_addr: 접속 단말 공인 IP (법인 필수).
        :param gt_uid: 거래고유번호 (법인 필수).
        :return: API 응답 데이터 또는 None.
        """
        # 국가 코드 대문자 변환
        country_code = country_code.upper()

        # 국가 설정 가져오기
        config = COUNTRY_CONFIG_ORDER.get(country_code)
        if not config:
            logging.error(f"Unsupported country code: {country_code}")
            return None

        # 행동에 따른 설정
        if action.lower() == 'buy':
            tr_id_default = config.get("tr_id_buy")
            sll_buy_dvsn_cd = config.get("sll_buy_dvsn_cd_buy")
            ord_dvsn = config.get("ord_dvsn_buy")
        elif action.lower() == 'sell':
            tr_id_default = config.get("tr_id_sell")
            sll_buy_dvsn_cd = config.get("sll_buy_dvsn_cd_sell")
            ord_dvsn = config.get("ord_dvsn_sell")
        else:
            logging.error(f"Invalid action: {action}. Must be 'buy' or 'sell'.")
            return None

        # tr_id 설정 (매개변수로 제공되지 않은 경우 기본값 사용)
        tr_id = tr_id if tr_id else tr_id_default

        # 예약 주문 접수 구분 코드 설정
        rvse_cncl_dvsn_cd = rvse_cncl_dvsn_cd if rvse_cncl_dvsn_cd else config.get("rvse_cncl_dvsn_cd")

        # PRDT_TYPE_CD 설정
        prdt_type_cd = config.get("prdt_type_cd")

        # OVRS_EXCG_CD 설정
        ovrs_excg_cd = config.get("ovrs_excg_cd")

        # ORD_DVSN 설정
        ord_dvsn = ord_dvsn if ord_dvsn else "00"

        # 기타 필드 설정
        rsvn_ord_rcit_dt = config.get("rsvn_ord_rcit_dt")
        ovrs_rsvn_odno = config.get("ovrs_rsvn_odno")

        # 요청 본문 구성
        payload = {
            "CANO": cano,
            "ACNT_PRDT_CD": acnt_prdt_cd,
            "PDNO": pdno,
            "OVRS_EXCG_CD": ovrs_excg_cd,
            "FT_ORD_QTY": ft_ord_qty,
            "FT_ORD_UNPR3": ft_ord_unpr3,
            "ORD_DVSN": ord_dvsn,
            "SLL_BUY_DVSN_CD": sll_buy_dvsn_cd,
            "RVSE_CNCL_DVSN_CD": rvse_cncl_dvsn_cd,
            "PRDT_TYPE_CD": prdt_type_cd,
            "RSVN_ORD_RCIT_DT": rsvn_ord_rcit_dt,
            "OVRS_RSVN_ODNO": ovrs_rsvn_odno
        }

        # 선택적 필드 추가
        optional_fields = {
            "seq_no": seq_no,
            "mac_address": mac_address,
            "phone_number": phone_number,
            "ip_addr": ip_addr,
            "gt_uid": gt_uid
        }
        for key, value in optional_fields.items():
            if value:
                payload[key] = value

        # 헤더 설정
        headers = self._add_tr_id_to_headers(tr_id, use_prefix=False)

        # API 경로 설정
        path = "/uapi/overseas-stock/v1/trading/order-resv"

        # POST 요청 전송
        response_data = self._post_request(
            path=path,
            payload=payload,
            headers=headers,
            error_log_prefix="해외 예약 주문 API 요청 실패"
        )

        # 응답 처리
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

    def example_submit_overseas_order(self):
        """
        예시: 해외주식 예약 주문 제출.
        """
        response = self.submit_overseas_reservation_order(
            country_code="USA",
            action="buy",
            cano=self._account_number,
            acnt_prdt_cd=self._account_code,
            pdno="AAPL",
            ft_ord_qty="1",
            ft_ord_unpr3="148.00",
            end_date="20250105"  # 예약 종료일자 (예시)
        )
        if response:
            print(json.dumps(response, indent=4, ensure_ascii=False))
        else:
            print("해외 예약 주문 요청에 실패했습니다.")


# 사용 예시
if __name__ == "__main__":
    # KoreaInvestmentAPI 인스턴스 생성
    api = KoreaInvestmentAPI(
        app_key=setting_env.APP_KEY,
        app_secret=setting_env.APP_SECRET,
        account_number=setting_env.ACCOUNT_NUMBER,
        account_code=setting_env.ACCOUNT_CODE
    )

    # 해외 예약 주문 예시
    api.check_holiday(datetime.now().strftime("%Y%m%d"))

    # 주식 가격 추가 예시
    # from your_app.models import PriceHistory  # 실제 모델 경로로 변경
    # insert_stock_price(table=PriceHistory, symbol=None, start_date='2025-01-01', end_date='2025-01-05')
