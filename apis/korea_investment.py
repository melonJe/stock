import logging
import urllib.parse
from datetime import datetime, timedelta
from time import sleep
from typing import List, Union, Dict, Optional

import requests

from config import setting_env
from config.country_config import COUNTRY_CONFIG_ORDER
from data.dto.account_dto import InquireBalanceRequestDTO, AccountResponseDTO, StockResponseDTO, OverseesStockResponseDTO, convert_overseas_to_domestic
from data.dto.holiday_dto import HolidayResponseDTO, HolidayRequestDTO
from data.dto.stock_trade_dto import StockTradeListRequestDTO, StockTradeListResponseDTO, OverseasStockTradeListRequestDTO, OverseasStockTradeListResponseDTO
from data.dto.interest_stock_dto import (
    InterestGroupListRequestDTO,
    InterestGroupListItemDTO,
    InterestGroupListResponseDTO,
    InterestGroupDetailRequestDTO,
    InterestGroupDetailInfoDTO,
    InterestGroupDetailItemDTO,
    InterestGroupDetailResponseDTO,
)
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
            "authorization": authorization,
            "content-Type": "application/json; charset=utf-8",
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
            logging.error("인증 실패: 잘못된 응답")
            raise Exception("인증 실패")

    def _get_request_raw(
            self,
            path: str,
            params: Dict,
            headers: Optional[Dict] = None,
            error_log_prefix: str = "HTTP 요청 실패"
    ) -> Optional[requests.Response]:
        sleep(0.5)
        url = f"{setting_env.DOMAIN}{path}?{urllib.parse.urlencode(params)}"
        effective_headers = self._headers if headers is None else headers
        try:
            resp = requests.get(url, headers=effective_headers)
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            logging.info(f"{error_log_prefix}. URL: {url}, 예외: {e}")
            return None

    def _get_request(
            self,
            path: str,
            params: Dict,
            headers: Optional[Dict] = None,
            error_log_prefix: str = "HTTP 요청 실패"
    ) -> Optional[Dict]:
        raw = self._get_request_raw(path, params, headers, error_log_prefix)
        return raw.json() if raw else None

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
        sleep(0.5)
        full_url = f"{setting_env.DOMAIN}{path}"
        effective_headers = self._headers if headers is None else headers
        try:
            response = requests.post(full_url, json=payload, headers=effective_headers)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logging.error(f"{error_log_prefix}. 예외: {e}, URL: {full_url}")
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
            logging.warning("주문 수량이 0입니다. 주문 미전송.")
            return False

        response = self._post_request(path, payload, headers)
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
        """
        Place a buy order.
        """
        headers = self._add_tr_id_to_headers("TTC0012U")
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
        headers = self._add_tr_id_to_headers("TTC0011U")
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
                logging.critical(f"계좌정보 파싱 오류 (KeyError/IndexError): {e}")
                return None
            except Exception as e:
                logging.critical(f"계좌정보 예상치 못한 오류: {e}")
                return None
        else:
            logging.critical("계좌정보 API 응답 없음")
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

        korea_list = self.get_korea_owned_stock_info()
        oversea_raw = self.get_oversea_owned_stock_info(country='USA')

        korea_list = korea_list or []
        oversea_list = convert_overseas_to_domestic(oversea_raw or [])

        return korea_list + oversea_list

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
            logging.critical(f"보유종목 파싱 오류 (KeyError): {e}")
            return None
        except Exception as e:
            logging.critical(f"보유종목 예상치 못한 오류: {e}")
            return None

    def get_oversea_owned_stock_info(self, country: str, symbol: str = None) -> Union[List[OverseesStockResponseDTO], OverseesStockResponseDTO, None]:
        """
        해외주식 잔고 조회 API를 호출하는 메서드.
        """
        result = list()
        country_code = country.upper()
        config = COUNTRY_CONFIG_ORDER.get(country_code)
        if not config:
            logging.error(f"지원하지 않는 국가 코드: {country_code}")
            return None
        params = {
            "CANO": self._account_number,
            "ACNT_PRDT_CD": self._account_code,
            "TR_CRCY_CD": config.get("tr_crcy_cd"),
            "CTX_AREA_FK200": '',
            "CTX_AREA_NK200": '',
        }

        ovrs_excg_cd = [x.strip() for x in config.get("ovrs_excg_cd").split(',')]
        # 조회에 필요한 GET 파라미터 구성
        for exchange in ovrs_excg_cd:
            params['OVRS_EXCG_CD'] = exchange
            response_data = self._get_request('/uapi/overseas-stock/v1/trading/inquire-balance', params, self._add_tr_id_to_headers("TTS3012R", use_prefix=True))
            if not response_data:
                continue
            try:
                stock_data = response_data.get("output1", [])
                if stock_data:
                    result.extend([OverseesStockResponseDTO(**item) for item in stock_data])
            except KeyError as e:
                logging.error(f"해외보유종목 파싱 오류 (KeyError): {e}")
                continue
            except Exception as e:
                logging.error(f"해외보유종목 예상치 못한 오류: {e}")
                continue

        if symbol:
            for item in result:
                if item.ovrs_pdno == symbol:
                    return item
        else:
            return result

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

    def get_interest_group_list(
            self,
            user_id: str,
            group_type: str = "1",
            fid_etc_cls_code: str = "00",
            custtype: str = "P"
    ) -> Optional[InterestGroupListResponseDTO]:
        """
        관심종목 그룹조회 API 호출 (국내주식-204).
        """
        headers = self._add_tr_id_to_headers("HHKCM113004C7", use_prefix=False)
        headers["custtype"] = custtype
        params = InterestGroupListRequestDTO(
            TYPE=group_type,
            FID_ETC_CLS_CODE=fid_etc_cls_code,
            USER_ID=user_id
        ).__dict__
        response_data = self._get_request(
            "/uapi/domestic-stock/v1/quotations/intstock-grouplist",
            params,
            headers,
            error_log_prefix="관심종목 그룹조회 API 요청 실패"
        )

        if response_data:
            try:
                output2 = response_data.get("output2", []) or []
                if isinstance(output2, dict):
                    output2 = [output2]
                items = [InterestGroupListItemDTO(**item) for item in output2]
                return InterestGroupListResponseDTO(output2=items)
            except Exception as e:
                logging.critical(f"관심종목 그룹조회 파싱 오류: {e} - response data: {response_data}")
                return None

        logging.critical("관심종목 그룹조회 API 응답 없음")
        return None

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
        """
        관심종목 그룹별 종목조회 API 호출 (국내주식-203).
        """
        headers = self._add_tr_id_to_headers("HHKCM113004C6", use_prefix=False)
        headers["custtype"] = custtype
        params = InterestGroupDetailRequestDTO(
            TYPE=group_type,
            USER_ID=user_id,
            DATA_RANK=data_rank,
            INTER_GRP_CODE=inter_grp_code,
            INTER_GRP_NAME=inter_grp_name,
            HTS_KOR_ISNM=hts_kor_isnm,
            CNTG_CLS_CODE=cntg_cls_code,
            FID_ETC_CLS_CODE=fid_etc_cls_code
        ).__dict__
        response_data = self._get_request(
            "/uapi/domestic-stock/v1/quotations/intstock-stocklist-by-group",
            params,
            headers,
            error_log_prefix="관심종목 그룹별 종목조회 API 요청 실패"
        )

        if response_data:
            try:
                output1 = response_data.get("output1")
                info = InterestGroupDetailInfoDTO(**output1) if output1 else None
                output2 = response_data.get("output2", []) or []
                if isinstance(output2, dict):
                    output2 = [output2]
                items = [InterestGroupDetailItemDTO(**item) for item in output2]
                return InterestGroupDetailResponseDTO(output1=info, output2=items)
            except Exception as e:
                logging.critical(f"관심종목 그룹별 종목조회 파싱 오류: {e} - response data: {response_data}")
                return None

        logging.critical("관심종목 상세조회 API 응답 없음")
        return None

    def get_stock_order_list(
            self,
            start_date: str = None,
            end_date: str = None
    ) -> Union[List[StockTradeListResponseDTO], None]:
        """
        날짜 범위 내 국내주식 주문 목록 조회 (모든 페이지 통합 반환)
        """
        # 1) 기본 날짜 세팅
        today = datetime.now().strftime("%Y%m%d")
        start_date = start_date or today
        end_date = end_date or today

        # 2) tr_id 결정 (최근 90일 vs 그 이상)
        ninety_days_ago = datetime.now() - timedelta(days=90)
        if datetime.strptime(end_date, "%Y%m%d") >= ninety_days_ago:
            tr_id = "TTTC0081R"
        else:
            tr_id = "CTSC9215R"

        headers = self._add_tr_id_to_headers(tr_id, use_prefix=False)
        all_trades: List[StockTradeListResponseDTO] = []
        ctx_nk, ctx_fk = None, None

        # 3) 페이지네이션 루프
        while True:
            params = StockTradeListRequestDTO(
                CANO=self._account_number,
                ACNT_PRDT_CD=self._account_code,
                INQR_STRT_DT=start_date,
                INQR_END_DT=end_date,
                CCLD_DVSN='01',
                CTX_AREA_NK100=ctx_nk or '',
                CTX_AREA_FK100=ctx_fk or '',
            ).__dict__

            resp = self._get_request_raw(
                "/uapi/domestic-stock/v1/trading/inquire-daily-ccld",
                params,
                headers
            )
            if not resp:
                logging.critical("stock_order_list HTTP 요청 실패.")
                return None

            # 4) 데이터 파싱
            try:
                items = resp.json().get("output1", [])
                all_trades.extend(StockTradeListResponseDTO(**item) for item in items)
            except Exception as e:
                logging.critical(f"JSON 파싱 오류: {e} | 응답 본문: {resp.text}")
                return None

            # 5) 다음 페이지 계속 여부 확인
            tr_cont = resp.headers.get('tr_cont')
            if tr_cont in ['F', 'M']:
                ctx_nk = resp.headers.get('ctx_area_nk100')
                ctx_fk = resp.headers.get('ctx_area_fk100')
                continue

            # 'D','E' 등이 오면 종료
            break

        return all_trades

    def get_overseas_stock_order_list(
            self,
            symbol: Optional[str] = None,
            country: Optional[str] = None,
            start_date: Optional[str] = None,
            end_date: Optional[str] = None,
    ) -> List[OverseasStockTradeListResponseDTO]:
        """
        날짜 범위 내 해외주식 주문 목록 조회 (모든 페이지 통합 반환)
        """
        # 1) 기본 날짜 세팅
        today = datetime.now().strftime("%Y%m%d")
        start_date = start_date or today
        end_date = end_date or today

        tr_id = "TTS3035R"
        headers = self._add_tr_id_to_headers(tr_id, use_prefix=True)

        all_trades: List[OverseasStockTradeListResponseDTO] = []
        ctx_nk, ctx_fk = None, None

        while True:
            params = OverseasStockTradeListRequestDTO(
                cano=self._account_number,
                acnt_prdt_cd=self._account_code,
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

            resp = self._get_request_raw(
                "/uapi/overseas-stock/v1/trading/inquire-ccnl",
                params,
                headers
            )
            if not resp:
                logging.error("국내주문내역 HTTP 요청 실패")
                break

            # 2) 페이로드 추출
            try:
                data = resp.json().get("output1", [])
                all_trades.extend(OverseasStockTradeListResponseDTO(**item) for item in data)
            except Exception as e:
                logging.error(f"JSON 파싱 에러: {e}, 응답: {resp.text}")
                break

            # 3) 다음 페이지 여부
            tr_cont = resp.headers.get('tr_cont')
            if tr_cont in ['F', 'M']:
                ctx_nk = resp.headers.get('ctx_area_nk200')
                ctx_fk = resp.headers.get('ctx_area_fk200')
                continue
            # tr_cont in ['D','E'] 또는 기타 종료 조건
            break

        return all_trades

    def submit_overseas_reservation_order(self, country: str, action: str, symbol: str, volume: str, price: str) -> Optional[Dict]:
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
            logging.error(f"잘못된 action: {action}. 'buy' 또는 'sell'이어야 합니다.")
            return None

        prdt_type_cd = config.get("prdt_type_cd")
        ovrs_excg_cd = [x.strip() for x in config.get("ovrs_excg_cd").split(',')]
        ord_dvsn = ord_dvsn if ord_dvsn else "00"
        ovrs_rsvn_odno = config.get("ovrs_rsvn_odno")
        rvse_cncl_dvsn_cd = config.get("RVSE_CNCL_DVSN_CD")

        for exchange in ovrs_excg_cd:
            payload = {
                "CANO": self._account_number,
                "ACNT_PRDT_CD": self._account_code,
                "RVSE_CNCL_DVSN_CD": rvse_cncl_dvsn_cd,
                "PDNO": symbol,
                "OVRS_EXCG_CD": exchange,
                "FT_ORD_QTY": volume,
                "FT_ORD_UNPR3": price,
                "ORD_DVSN": ord_dvsn,
                "SLL_BUY_DVSN_CD": sll_buy_dvsn_cd,
                "PRDT_TYPE_CD": prdt_type_cd,
                # "RSVN_ORD_RCIT_DT": end_date,
                "ORD_SVR_DVSN_CD": "0",
                "OVRS_RSVN_ODNO": ovrs_rsvn_odno
            }
            payload = {k: v for k, v in payload.items() if v is not None}

            headers = self._add_tr_id_to_headers(tr_id, use_prefix=True)
            path = "/uapi/overseas-stock/v1/trading/order-resv"
            response_data = self._post_request(
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
                if '해당종목정보가 없습니다' in response_data['msg1']:
                    continue
                error_msg = f"{symbol} 해외 예약 주문 실패: {response_data}"
                logging.error(error_msg)
                continue


if __name__ == "__main__":
    ki_api = KoreaInvestmentAPI(app_key=setting_env.APP_KEY_KOR, app_secret=setting_env.APP_SECRET_KOR, account_number=setting_env.ACCOUNT_NUMBER_KOR, account_code=setting_env.ACCOUNT_CODE_KOR)
    print(ki_api.get_stock_order_list())
