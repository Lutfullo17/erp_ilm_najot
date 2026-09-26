"""Run the single long-lived scheduler process used in production."""

import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from django.conf import settings
from django.core.management.base import BaseCommand

from erp.scheduler import acquire_scheduler_lock, configure_scheduler


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Davomat nazorati schedulerini alohida jarayon sifatida ishga tushiradi."

    def handle(self, *args, **options):
        if not acquire_scheduler_lock():
            self.stderr.write("Scheduler allaqachon boshqa jarayonda ishlayapti — ikkinchi nusxa ishga tushirilmadi.")
            return
        scheduler = configure_scheduler(BlockingScheduler(timezone=settings.TIME_ZONE))
        self.stdout.write(self.style.SUCCESS("Scheduler ishga tushdi: davomat har 5 daqiqada, oylik balanslar har kuni 00:10 da."))
        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            logger.info("Scheduler to'xtatildi.")
            scheduler.shutdown(wait=False)
