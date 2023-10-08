from django.apps import AppConfig
from django.conf import settings


class SchedulerConfig(AppConfig):
    name = 'scheduler'

    def ready(self):
        if settings.SCHEDULER_ENABLED:
            from . import background_scheduler
            # print(background_scheduler.initial_yield_growth_stock_investment())
            # background_scheduler.update_subscription_aggressive_investor()
            background_scheduler.start()
