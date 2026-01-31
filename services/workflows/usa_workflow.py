"""미국주식 트레이딩 워크플로우"""
import datetime
import logging
import threading

from clients.kis import KISClient
from config import setting_env
from services.workflows.base import select_buy_stocks, trading_buy


class USAWorkflow:
    """미국주식 트레이딩 워크플로우"""

    @staticmethod
    def run():
        """미국주식 트레이딩 실행"""
        ki_api = KISClient(
            app_key=setting_env.APP_KEY_USA,
            app_secret=setting_env.APP_SECRET_USA,
            account_number=setting_env.ACCOUNT_NUMBER_USA,
            account_code=setting_env.ACCOUNT_CODE_USA
        )

        usa_stock = select_buy_stocks(country="USA")
        buy = threading.Thread(target=trading_buy, args=(ki_api, usa_stock,))
        buy.start()


# 기존 코드 호환을 위한 함수
def usa_trading():
    USAWorkflow.run()
