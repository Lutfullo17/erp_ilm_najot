"""Avtomatik davomat nazorati uchun APScheduler sozlamalari."""

import logging
import os
import socket
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


def sync_balances_job():
    """Har kuni: muddati kelgan oylar uchun barcha faol o'quvchilarga balans yaratadi.

    Bu job bo'lmasa, to'lov qilmagan o'quvchilar moliyaviy hisobotda ko'rinmay qoladi.
    """
    try:
        from payments.billing import sync_all
        results = sync_all(active_only=True)
        logger.info("Balanslar sinxronlandi: %s juftlik, %s tasi o'zgardi",
                    len(results), sum(1 for r in results if r.changed))
    except Exception:
        logger.exception("Balanslarni sinxronlashda xatolik yuz berdi")


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
    scheduler.add_job(
        sync_balances_job,
        trigger=CronTrigger(hour=0, minute=10, timezone='Asia/Tashkent'),
        id='sync_month_balances',
        name="Oylik balanslarni yaratish",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=6 * 3600,
    )
    return scheduler


_lock_socket = None


def acquire_scheduler_lock():
    """Server bo'yicha bitta scheduler bo'lishini ta'minlaydi.

    Har bir gunicorn worker va `clock` jarayoni o'z schedulerini ishga tushirsa, davomat jarimalari va
    balans sinxronizatsiyasi bir necha marta bajariladi. Lokal portni band qilgan birinchi jarayon
    scheduler egasi bo'ladi; jarayon to'xtasa, port OS tomonidan avtomatik bo'shatiladi.
    """
    global _lock_socket
    if _lock_socket is not None:
        return True
    port = int(os.environ.get('SCHEDULER_LOCK_PORT', '47823'))
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):  # Windows: boshqa jarayon portni qayta ishlata olmasin
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    try:
        sock.bind(('127.0.0.1', port))
        sock.listen(1)
    except OSError:
        sock.close()
        return False
    _lock_socket = sock
    return True


def start():
    """Web jarayoni ichida background schedulerni ishga tushiradi (agar boshqa jarayonda ishlamayotgan bo'lsa)."""
    if not acquire_scheduler_lock():
        logger.info("Scheduler boshqa jarayonda ishlayapti — bu jarayonda ishga tushirilmadi.")
        return None
    scheduler = configure_scheduler(BackgroundScheduler(timezone='Asia/Tashkent'))
    scheduler.start()
    logger.info("APScheduler ishga tushirildi.")
    return scheduler
