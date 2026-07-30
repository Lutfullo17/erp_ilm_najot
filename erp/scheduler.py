"""Avtomatik davomat nazorati uchun APScheduler sozlamalari."""

import logging
from io import StringIO

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from django.core.management import call_command
from django_apscheduler.jobstores import DjangoJobStore


logger = logging.getLogger(__name__)


def check_attendance_job():
    """Davomat nazoratini ishga tushiradi va natijani loglaydi."""
    try:
        output = StringIO()
        call_command('check_missed_attendance', stdout=output)
        logger.info("Davomat nazorati natijasi: %s", output.getvalue().strip())
    except Exception:
        logger.exception("Davomat nazoratida xatolik yuz berdi")


def configure_scheduler(scheduler):
    """Davomat tekshiruvini har besh daqiqada bajarish uchun job qo'shadi."""
    scheduler.add_jobstore(DjangoJobStore(), 'default')
    scheduler.add_job(
        check_attendance_job,
        trigger=CronTrigger(minute='*/5'),
        id='check_attendance_monitoring',
        name='Avtomatik davomat nazorati',
        replace_existing=True,
        max_instances=1,
    )
    return scheduler


def start():
    """Eski chaqiruvlar uchun background schedulerni ishga tushiradi."""
    scheduler = configure_scheduler(BackgroundScheduler())
    scheduler.start()
    logger.info("APScheduler ishga tushirildi.")
    return scheduler
