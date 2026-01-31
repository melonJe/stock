"""국내주식 트레이딩 워크플로우"""
import datetime
import logging
import threading
from datetime import datetime

from config import setting_env
from config.logging_config import get_logger

logger = get_logger(__name__)

from services.data_handler import add_stock_price
from services.workflows.base import select_buy_stocks, select_sell_stocks, trading_buy, trading_sell


class KoreaWorkflow:
    """국내주식 트레이딩 워크플로우"""

    @staticmethod
    def run():
        """국내주식 일일 트레이딩 실행"""
        ki_api = KISClient(
            app_key=setting_env.APP_KEY_KOR,
            app_secret=setting_env.APP_SECRET_KOR,
            account_number=setting_env.ACCOUNT_NUMBER_KOR,
            account_code=setting_env.ACCOUNT_CODE_KOR
        )

        if ki_api.check_holiday(datetime.datetime.now().strftime("%Y%m%d")):
            logger.info("국내 주식 일일 루틴 시작", workflow="korea") 
            logger.info(f'{datetime.datetime.now()} 휴장일')
            return

        while datetime.datetime.now().time() < datetime.time(18, 15, 00):
            sleep(1 * 60)

        add_stock_price(
            country="KOR",
            start_date=datetime.datetime.now() - datetime.timedelta(days=5),
            end_date=datetime.datetime.now()
        )

        stocks_held = ki_api.get_owned_stock_info()
        sell_queue = select_sell_stocks(stocks_held)
        sell = threading.Thread(target=trading_sell, args=(ki_api, sell_queue,))
        sell.start()

        buy_stock = select_buy_stocks(country="KOR")
        buy = threading.Thread(target=trading_buy, args=(ki_api, buy_stock,))
        buy.start()


# 기존 코드 호환을 위한 함수
def korea_trading():
    KoreaWorkflow.run()
