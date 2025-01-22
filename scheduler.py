from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from config import setting_env
from services import data_handler
from services.data_handler import add_stock_price
from services.trading import korea_trading, usa_trading


def start():
    scheduler = BackgroundScheduler(misfire_grace_time=3600, coalesce=True, timezone='Asia/Seoul')

    if not setting_env.SIMULATE:
        scheduler.add_job(
            data_handler.update_subscription_stock,
            trigger=CronTrigger(day=1, hour=2),
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
            trigger=CronTrigger(hour=15, minute=30, second=0),
            id="update_blacklist",
            max_instances=1,
            replace_existing=True,
        )

        scheduler.add_job(
            add_stock_price,
            trigger=CronTrigger(day_of_week="tue-sat", hour=16, minute=00, second=0),
            kwargs={'country': 'USA', 'start_date': datetime.now() - timedelta(days=5), 'end_date': datetime.now()},
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
        trigger=CronTrigger(day_of_week="tue-sat", hour=16, minute=30, second=0),
        id="usa_trading",
        max_instances=1,
        replace_existing=True,
    )

    try:
        scheduler.start()
    except KeyboardInterrupt:
        scheduler.shutdown()


if __name__ == "__main__":
    # start()
    # ki_api = KoreaInvestmentAPI(app_key=setting_env.APP_KEY, app_secret=setting_env.APP_SECRET, account_number=setting_env.ACCOUNT_NUMBER, account_code=setting_env.ACCOUNT_CODE)
    # data_handler.add_stock_price(start_date="2020-01-01", end_date=datetime.now())
    # trading_buy(ki_api=ki_api, buy_levels=select_buy_stocks(country="KOR"))
    # trading_sell(ki_api=ki_api)
    # print(select_buy_stocks(country="KOR"))
    # print(select_sell_stocks(ki_api))
    data_handler.add_stock_price(country='USA', start_date=datetime.now(), end_date=datetime.now())


@asynccontextmanager
async def lifespan(app):
    start()
    yield
    print("lifespan finished")
