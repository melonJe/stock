"""ETF 트레이딩 워크플로우"""
import datetime
import logging

from clients.kis import KISClient
from config.logging_config import get_logger
from config import setting_env
from utils import discord

logger = get_logger(__name__)


class ETFWorkflow:
    """ETF 트레이딩 워크플로우"""

    @staticmethod
    def run():
        """ETF 관심종목 그룹에 포함된 종목을 1주씩 매수"""
        ki_api = KISClient(
            app_key=setting_env.APP_KEY_ETF,
            app_secret=setting_env.APP_SECRET_ETF,
            account_number=setting_env.ACCOUNT_NUMBER_ETF,
            account_code=setting_env.ACCOUNT_CODE_ETF,
        )

        today = datetime.datetime.now().strftime("%Y%m%d")
        holidays = ki_api.get_domestic_market_holidays(today)
        holiday = holidays.get(today)
        if holiday and holiday.opnd_yn == "N":
            logger.info("ETF 그룹 매수 스킵: 휴장일")
            return

        group_list = ki_api.get_interest_group_list(user_id=setting_env.HTS_ID_ETF)
        if not group_list or not group_list.output2:
            logger.warning("ETF 그룹 매수 스킵: 관심종목 그룹 없음")
            return

        etf_groups = [
            item for item in group_list.output2
            if "ETF" in (item.inter_grp_name or "").upper()
        ]
        if not etf_groups:
            logger.warning("ETF 그룹 매수 스킵: ETF 그룹 미존재")
            return

        symbols = set()
        for group in etf_groups:
            detail = ki_api.get_interest_group_stocks(
                user_id=setting_env.HTS_ID_ETF,
                inter_grp_code=group.inter_grp_code,
            )
            if not detail or not detail.output2:
                continue
            for item in detail.output2:
                if item.jong_code:
                    symbols.add(item.jong_code)

        if not symbols:
            logger.warning("ETF 그룹 매수 스킵: 매수 대상 없음")
            return

        total_purchase_amount = 0
        purchased_symbols = []

        for symbol in sorted(symbols):
            try:
                ki_api.buy(symbol=symbol, price=0, volume=1, order_type="03")
                purchased_symbols.append(symbol)
            except Exception as e:
                logger.critical(f"ETF 그룹 매수 실패: {symbol} - {e}")

        # 구매 금액 계산 및 잔고 확인
        if purchased_symbols:
            for symbol in purchased_symbols:
                current_price = ki_api.get_current_price(symbol=symbol)
                if current_price:
                    total_purchase_amount += current_price

            account_info = ki_api.get_account_info()
            if account_info and total_purchase_amount > 0:
                balance = int(account_info.dnca_tot_amt)
                threshold = total_purchase_amount * 2
                if balance <= threshold:
                    discord.send_message(
                        f"[ETF 계좌 잔고 부족 알림]\n"
                        f"금일 구매 금액: {total_purchase_amount:,}원\n"
                        f"현재 잔고: {balance:,}원\n"
                        f"권장 잔고: {threshold:,}원 이상\n"
                        f"→ 금액 충전이 필요합니다."
                    )


# 기존 코드 호환을 위한 함수
def buy_etf_group_stocks():
    ETFWorkflow.run()
