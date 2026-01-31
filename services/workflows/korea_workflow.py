"""국내주식 트레이딩 워크플로우"""
import asyncio
import datetime
from datetime import datetime

from config import setting_env
from config.logging_config import get_logger

logger = get_logger(__name__)

from services.data_handler import add_stock_price
from services.workflows.base import select_buy_stocks, select_sell_stocks, trading_buy, trading_sell
from clients.kis import KISClient


class KoreaWorkflow:
    """국내주식 트레이딩 워크플로우"""

    @staticmethod
    async def run():
        """국내주식 일일 트레이딩 실행 (비동기)"""
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
            await asyncio.sleep(1 * 60)

        add_stock_price(
            country="KOR",
            start_date=datetime.datetime.now() - datetime.timedelta(days=5),
            end_date=datetime.datetime.now()
        )

        stocks_held = ki_api.get_owned_stock_info()
        sell_queue = select_sell_stocks(stocks_held)
        buy_stock = select_buy_stocks(country="KOR")

        # 비동기 병렬 실행 (threading 대신 asyncio.gather 사용)
        await asyncio.gather(
            asyncio.to_thread(trading_sell, ki_api, sell_queue),
            asyncio.to_thread(trading_buy, ki_api, buy_stock)
        )


# 기존 코드 호환을 위한 함수
def korea_trading():
    """동기 래퍼 함수 (스케줄러용)"""
    asyncio.run(KoreaWorkflow.run())
