"""
APScheduler joblari — avtomatik davomat nazorati.

Bu fayl Django ishga tushganda avtomatik yuklanadi.
Har 5 daqiqada check_missed_attendance command ishga tushiriladi.
"""
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from django_apscheduler.jobstores import DjangoJobStore

logger = logging.getLogger(__name__)


def check_attendance_job():
    """Har 5 daqiqada davomat nazoratini tekshiradi."""
    try:
        from django.core.management import call_command
        from io import StringIO

        out = StringIO()
        call_command('check_missed_attendance', stdout=out)
        output = out.getvalue()
        logger.info(f"Davomat nazorati natijasi: {output.strip()}")
    except Exception as e:
        logger.error(f"Davomat nazorati xatoligi: {e}", exc_info=True)


def start():
    """Scheduler ni ishga tushiradi."""
    scheduler = BackgroundScheduler()
    scheduler.add_jobstore(DjangoJobStore(), "default")

    # Har 5 daqiqada davomat nazorati
    scheduler.add_job(
        check_attendance_job,
        trigger=CronTrigger(minute="*/5"),
        id="check_attendance_monitoring",
        name="Avtomatik davomat nazorati",
        replace_existing=True,
        max_instances=1,
    )

    scheduler.start()
    logger.info("APScheduler ishga tushirildi — davomat nazorati har 5 daqiqada.")
