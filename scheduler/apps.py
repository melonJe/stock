from django.apps import AppConfig
from django.conf import settings


class SchedulerConfig(AppConfig):
    name = 'scheduler'

    def ready(self):
        if settings.SCHEDULER_ENABLED:
            from . import background_scheduler
            # item = background_scheduler.initial_yield_growth_stock_investment()
            # print([x.symbol.name for x in item['buy']])
            # print([x.symbol.name for x in item['sell']])
            background_scheduler.start()
