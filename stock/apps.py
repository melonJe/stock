from django.apps import AppConfig
from django.conf import settings


class SchedulerConfig(AppConfig):
    name = 'stock'

    def ready(self):
        if settings.SCHEDULER_ENABLED:
            from . import scheduler
            scheduler.start()
