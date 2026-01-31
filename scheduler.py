from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import AsyncGenerator

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from apscheduler.triggers.cron import CronTrigger

from config import setting_env
from config.logging_config import get_logger
from services import data_handler
from services.data_handler import add_stock_price
from services.trading import usa_trading, korea_trading, buy_etf_group_stocks

logger = get_logger(__name__)


def start() -> None:
    """스케줄러 시작"""
    scheduler = BackgroundScheduler(misfire_grace_time=3600, coalesce=True, timezone='Asia/Seoul')

    if not setting_env.SIMULATE:
        scheduler.add_job(
            data_handler.update_subscription_stock,
            trigger=CronTrigger(day=1, hour=4),
            id="update_defensive_subscription_stock",
            max_instances=1,
            replace_existing=True,
        )

        scheduler.add_job(
            data_handler.update_stock_listings,
            trigger=CronTrigger(day=1, hour=0),
            id="update_stock_listings",
            max_instances=1,
            replace_existing=True,
        )

        scheduler.add_job(
            data_handler.update_blacklist,
            trigger=CronTrigger(hour=17, minute=30, second=0),
            id="update_blacklist",
            max_instances=1,
            replace_existing=True,
        )

        scheduler.add_job(
            add_stock_price,
            trigger=CronTrigger(day_of_week="tue-sat", hour=12, minute=00, second=0),
            kwargs={'country': 'USA', 'start_date': datetime.now() - timedelta(days=5)},
            id="add_usa_stock_price",
            max_instances=1,
            replace_existing=True,
        )

    scheduler.add_job(
        korea_trading,
        trigger=CronTrigger(day_of_week="mon-fri", hour=8, minute=50, second=0),
        id="korea_trading",
        max_instances=1,
        replace_existing=True,
    )

    scheduler.add_job(
        usa_trading,
        trigger=CronTrigger(day_of_week="tue-sat", hour=14, minute=0, second=0),
        id="usa_trading",
        max_instances=1,
        replace_existing=True,
    )

    scheduler.add_job(
        buy_etf_group_stocks,
        trigger=CronTrigger(day_of_week="mon-fri", hour=11, minute=0, second=0),
        id="buy_etf_group_stocks",
        max_instances=1,
        replace_existing=True,
    )

    logger.info("스케줄러 시작", simulate=setting_env.SIMULATE)
    try:
        scheduler.start()
    except KeyboardInterrupt:
        logger.info("스케줄러 종료 (사용자 중단)")
        scheduler.shutdown()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """FastAPI lifespan 이벤트 핸들러"""
    start()
    yield
    logger.info("lifespan finished")
