from django.apps import AppConfig
from django.conf import settings


class SchedulerConfig(AppConfig):
    name = 'scheduler'

    def ready(self):
        if settings.SCHEDULER_ENABLED:
            from . import background_scheduler
            # background_scheduler.korea_investment_trading_initial_yield_growth_stock_investment()
            background_scheduler.start()
