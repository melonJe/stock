"""미국주식 트레이딩 워크플로우"""
import asyncio
import datetime
import logging

from config import setting_env
from config.logging_config import get_logger

logger = get_logger(__name__)

from clients.kis import KISClient
from services.workflows.base import select_buy_stocks, trading_buy


class USAWorkflow:
    """미국주식 트레이딩 워크플로우"""

    @staticmethod
    async def run():
        """미국주식 일일 트레이딩 실행 (비동기)"""
        logger.info("미국 주식 일일 루틴 시작", workflow="usa")
        ki_api = KISClient(
            app_key=setting_env.APP_KEY_USA,
            app_secret=setting_env.APP_SECRET_USA,
            account_number=setting_env.ACCOUNT_NUMBER_USA,
            account_code=setting_env.ACCOUNT_CODE_USA
        )

        usa_stock = select_buy_stocks(country="USA")
        
        # 비동기 실행 (threading 대신 asyncio 사용)
        await asyncio.to_thread(trading_buy, ki_api, usa_stock)


# 기존 코드 호환을 위한 함수
def usa_trading():
    """동기 래퍼 함수 (스케줄러용)"""
    asyncio.run(USAWorkflow.run())
