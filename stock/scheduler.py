from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from django.conf import settings

import stock.service.data_handler as data_handler
from stock.service.trading import korea_investment_trading


def start():
    scheduler = BackgroundScheduler(misfire_grace_time=3600, coalesce=True, timezone=settings.TIME_ZONE)

    scheduler.add_job(
        data_handler.update_defensive_subscription_stock,
        trigger=CronTrigger(day=1, hour=2),
        id="update_defensive_subscription_stock",
        max_instances=1,
        replace_existing=True,
    )

    scheduler.add_job(
        data_handler.update_aggressive_subscription_stock,
        trigger=CronTrigger(day=1, hour=4),
        id="update_aggressive_subscription_stock",
        max_instances=1,
        replace_existing=True,
    )

    scheduler.add_job(
        data_handler.add_stock,
        trigger=CronTrigger(day=1, hour=0),
        id="add_stock",
        max_instances=1,
        replace_existing=True,
    )

    scheduler.add_job(
        data_handler.add_stock_price,
        trigger=CronTrigger(day_of_week="sat"),
        kwargs={'start_date': (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d'), 'end_date': datetime.now().strftime('%Y-%m-%d')},
        id="add_stock_price_1week",
        max_instances=1,
        replace_existing=True,
    )

    scheduler.add_job(
        data_handler.add_stock_price,
        trigger=CronTrigger(day_of_week="mon-fri", hour=18, minute=0, second=0),
        kwargs={'start_date': datetime.now().strftime('%Y-%m-%d'), 'end_date': datetime.now().strftime('%Y-%m-%d')},
        id="add_stock_price_1day",
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
        korea_investment_trading,
        trigger=CronTrigger(day_of_week="mon-fri", hour=8, minute=50, second=0),
        id="korea_investment_trading",
        max_instances=1,
        replace_existing=True,
    )

    try:
        scheduler.start()
    except KeyboardInterrupt:
        scheduler.shutdown()
