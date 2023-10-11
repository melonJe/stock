from django.apps import AppConfig
from django.conf import settings

import setting_env
from stock.service.korea_investment import KoreaInvestment


class SchedulerConfig(AppConfig):
    name = 'scheduler'

    def ready(self):
        if settings.SCHEDULER_ENABLED:
            from . import background_scheduler
            # print(background_scheduler.bollinger_band(KoreaInvestment(app_key=setting_env.APP_KEY, app_secret=setting_env.APP_SECRET, account_number=setting_env.ACCOUNT_NUMBER, account_cord=setting_env.ACCOUNT_CORD)))
            # background_scheduler.update_subscription_aggressive_investor()
            # background_scheduler.add_stock_price_all()
            background_scheduler.start()
