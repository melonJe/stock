from django.apps import AppConfig
from django.conf import settings


class SchedulerConfig(AppConfig):
    name = 'scheduler'

    def ready(self):
        if settings.SCHEDULER_ENABLED:
            from . import background_scheduler
            # background_scheduler.alert()
            background_scheduler.start()
